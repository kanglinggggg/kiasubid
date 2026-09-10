import hashlib
import json
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.amendments.schemas import (
    AmendmentApplyRequest,
    AmendmentImpactPreview,
    AmendmentPreviewRequest,
    AmendmentPreviewResponse,
    ClarificationDraft,
    FieldDiff,
    PlannedTask,
    RequirementSnapshot,
    SourceProof,
    WorkflowStep,
)
from app.enums import AssessmentStatus, GateType, TaskStatus
from app.llm.interpreter import TenderInterpreter
from app.llm.schemas import (
    ChangeInterpretationEnvelope,
    ChangeInterpretationRequest,
    ChangeInterpretationResult,
    RequirementSource,
    StructuredField,
    StructuredRequirement,
)
from app.models import (
    ActivityEvent,
    Assessment,
    ChangeEvent,
    Employee,
    Evidence,
    HumanApproval,
    Requirement,
    Task,
    TaskDependency,
    Tender,
    TenderDocument,
)
from app.rules.schemas import (
    EventAttendanceRule,
    ParticipationRestrictionRule,
    ProcessingWindowRule,
    QualificationRule,
    RequiredDocumentRule,
    SourceFreshnessRule,
)
from app.services.assessment import AssessmentResult, assess_requirement
from app.services.clock import now
from app.services.deadline import calculate_deadline_risk, deadline_risk_trace
from app.services.metrics import (
    calculate_submission_coverage,
    critical_gate_trace,
    current_requirements,
    derive_operational_status,
    latest_assessment,
    submission_coverage_trace,
)


class AmendmentPreviewExpiredError(ValueError):
    pass


class AmendmentPreviewStaleError(ValueError):
    pass


class AmendmentApplyBlockedError(ValueError):
    pass


class AmendmentAlreadyAppliedError(ValueError):
    pass


class AmendmentSourceVersionConflictError(ValueError):
    pass


_PREVIEW_TTL_SECONDS = 30 * 60
_MAX_PREVIEWS = 100
_INTERPRETER = TenderInterpreter()
_PREVIEW_LOCK = threading.Lock()


@dataclass
class _StoredPreview:
    response: AmendmentPreviewResponse
    request: AmendmentPreviewRequest
    interpretation: ChangeInterpretationEnvelope
    base_fingerprint: str
    created_monotonic: float
    applied: bool = False
    applying: bool = False


_PREVIEWS: dict[str, _StoredPreview] = {}


_REQUIREMENT_TYPES = {
    "ELIGIBILITY",
    "MANPOWER",
    "TECHNICAL",
    "COMMERCIAL",
    "DOCUMENT",
    "DEADLINE",
    "COMPLIANCE",
    "OTHER",
}

_RULE_MODELS = {
    "EVENT_ATTENDANCE": EventAttendanceRule,
    "QUALIFICATION": QualificationRule,
    "REQUIRED_DOCUMENT": RequiredDocumentRule,
    "PROCESSING_WINDOW": ProcessingWindowRule,
    "PARTICIPATION_RESTRICTION": ParticipationRestrictionRule,
    "SOURCE_FRESHNESS": SourceFreshnessRule,
}

_APPLYABLE_CHANGED_FIELDS = {
    "text",
    "minimum_count",
    "certification",
    "deadline",
    "gate_type",
    "compulsory",
}

_NUMBER_WORDS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}


def _normalise_requirement_type(value: str) -> str:
    candidate = value.upper()
    if candidate in _REQUIREMENT_TYPES:
        return candidate
    aliases = {
        "REGISTRATION": "ELIGIBILITY",
        "FINANCIAL": "COMMERCIAL",
        "CERTIFICATION": "COMPLIANCE",
        "EXPERIENCE": "ELIGIBILITY",
        "BRIEFING": "ELIGIBILITY",
        "INSURANCE": "COMPLIANCE",
        "DECLARATION": "DOCUMENT",
        "PRICING": "COMMERCIAL",
        "CONTRACTUAL": "COMPLIANCE",
    }
    return aliases.get(candidate, "OTHER")


def _procurement_rule_from_config(config: dict[str, Any]) -> Any | None:
    model = _RULE_MODELS.get(str(config.get("kind", "")).upper())
    if model is None:
        return None
    candidate = {
        field_name: config[field_name]
        for field_name in model.model_fields
        if field_name in config
    }
    try:
        return model.model_validate(candidate)
    except (TypeError, ValueError):
        return None


def _structured_fields_from_config(
    config: dict[str, Any],
    procurement_rule: Any | None,
) -> list[StructuredField]:
    reserved = {
        "kind",
        "facts",
        "evaluation_as_of",
        "minimum_count",
        "certification",
        "compulsory",
    }
    if procurement_rule is not None:
        reserved.update(type(procurement_rule).model_fields)
    fields = []
    for name, value in sorted(config.items()):
        if name in reserved or not re.fullmatch(r"[a-z][a-z0-9_]{0,99}", name):
            continue
        if value is None or isinstance(value, (str, int, float, bool)):
            fields.append(StructuredField(name=name, value=value))
    return fields


def _structured_requirement(requirement: Requirement) -> StructuredRequirement:
    procurement_rule = _procurement_rule_from_config(requirement.rule_config)
    compulsory = requirement.rule_config.get("compulsory")
    if compulsory is None and procurement_rule is not None:
        compulsory = getattr(procurement_rule, "compulsory", None)
    if compulsory is None:
        compulsory = requirement.gate_type == GateType.MANDATORY.value
    return StructuredRequirement(
        stable_key=requirement.stable_key,
        text=requirement.text,
        requirement_type=_normalise_requirement_type(requirement.requirement_type),
        gate_type=requirement.gate_type,
        deadline=requirement.deadline,
        minimum_count=requirement.rule_config.get("minimum_count"),
        certification=requirement.rule_config.get("certification"),
        compulsory=compulsory,
        procurement_rule=procurement_rule,
        structured_fields=_structured_fields_from_config(
            requirement.rule_config,
            procurement_rule,
        ),
        interpretation_status="INTERPRETED",
        source=RequirementSource(
            document=requirement.source_document.filename,
            page=requirement.source_page,
            section=requirement.source_section,
            snippet=requirement.source_snippet,
        ),
    )


def _display(value: Any) -> str:
    if value is None:
        return "Not set"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    return str(value)


def _normalised_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _explicit_count_values(value: str) -> set[int]:
    token_pattern = r"\d+|" + "|".join(_NUMBER_WORDS)
    patterns = (
        rf"(?:not\s+fewer\s+than|at\s+least|minimum(?:\s+(?:count|of))?)\s+({token_pattern})\b",
        rf"(?:increase(?:d)?|change(?:d)?|revis(?:e|ed)|replace(?:d)?)"
        rf"[^.;\n]{{0,80}}?\b(?:to|with)\s+({token_pattern})\b",
    )
    tokens = []
    for pattern in patterns:
        tokens.extend(re.findall(pattern, value, flags=re.IGNORECASE))
    return {
        int(token) if token.isdigit() else _NUMBER_WORDS[token.casefold()]
        for token in tokens
    }


def _date_is_explicit(value: datetime, source_text: str) -> bool:
    day = str(value.day)
    year = str(value.year)
    month = value.strftime("%B")
    short_month = value.strftime("%b")
    candidates = {
        value.date().isoformat(),
        f"{day}/{value.month}/{year}",
        f"{value.month}/{day}/{year}",
        f"{day} {month} {year}",
        f"{day} {short_month} {year}",
        f"{month} {day}, {year}",
        f"{short_month} {day}, {year}",
    }
    normalised_source = _normalised_text(source_text)
    return any(_normalised_text(candidate) in normalised_source for candidate in candidates)


def _canonical_staff_text(minimum_count: int, certification: str) -> str:
    count_label = next(
        (word for word, value in _NUMBER_WORDS.items() if value == minimum_count),
        str(minimum_count),
    )
    return (
        f"The Tenderer shall propose not fewer than {count_label} personnel holding valid "
        f"{certification} certification."
    )


def _target_reference_failure(
    payload: AmendmentPreviewRequest,
    target: Requirement,
) -> str | None:
    """Require the source itself to anchor the human-selected target."""
    context = f"{payload.source.section}\n{payload.source.text}"
    key_match = re.fullmatch(r"([A-Za-z][A-Za-z_-]*)(\d+)", target.stable_key)
    if key_match:
        family_mentions = {
            match.group(0).casefold()
            for match in re.finditer(
                rf"(?<![A-Za-z0-9_-]){re.escape(key_match.group(1))}\d+(?![A-Za-z0-9_-])",
                context,
                flags=re.IGNORECASE,
            )
        }
        target_key = target.stable_key.casefold()
        if family_mentions:
            if family_mentions != {target_key}:
                return (
                    "The supplied source names a different or multiple requirement identifier; "
                    f"it does not unambiguously target {target.stable_key}."
                )
            return None
    elif re.search(
        rf"(?<![A-Za-z0-9_-]){re.escape(target.stable_key)}(?![A-Za-z0-9_-])",
        context,
        flags=re.IGNORECASE,
    ):
        return None

    clause_pattern = r"\b\d+(?:\.\d+)+\b"
    target_clauses = set(re.findall(clause_pattern, target.source_section))
    source_clauses = set(re.findall(clause_pattern, context))
    if source_clauses:
        if target_clauses.intersection(source_clauses):
            return None
        return (
            "The clause reference in the supplied source does not match the selected "
            f"requirement {target.stable_key}."
        )

    source_normalised = _normalised_text(payload.source.text)
    if _normalised_text(target.text) in source_normalised:
        return None
    quoted_segments = re.findall(r"[‘'\"]([^’'\"]{20,})[’'\"]", payload.source.text)
    target_normalised = _normalised_text(target.text)
    if any(_normalised_text(segment) in target_normalised for segment in quoted_segments):
        return None
    return (
        f"The supplied source does not explicitly identify {target.stable_key}, its source "
        "clause, or a quoted excerpt of the current requirement."
    )


def _directed_new_value_span(value: str) -> str:
    """Prefer the replacement/new-value segment over old and unrelated wording."""
    patterns = (
        r"\breplace\b[\s\S]*?\bwith\b\s*[‘'\"](?P<new>[^’'\"]+)[’'\"]",
        r"\breplace\b[\s\S]*?\bwith\b\s*(?P<new>[^.;\n]+)",
        r"\bfrom\b[\s\S]*?\bto\b\s*(?P<new>[^.;\n]+)",
        r"\b(?:amended|changed|revised|increased|decreased)\b[^.;\n]{0,120}?"
        r"\bto\b\s*(?P<new>[^.;\n]+)",
        r"\bnow\b\s*(?P<new>[^.;\n]+)",
    )
    for pattern in patterns:
        match = re.search(pattern, value, flags=re.IGNORECASE)
        if match:
            return match.group("new").strip()
    return value


def _change_grounding_failure(
    payload: AmendmentPreviewRequest,
    target: Requirement,
    resulting: StructuredRequirement,
    changed_fields: set[str],
) -> str | None:
    unsupported = sorted(changed_fields - _APPLYABLE_CHANGED_FIELDS)
    if unsupported:
        return (
            "This version cannot deterministically ground changes to "
            f"{', '.join(unsupported)}; elevated review is required."
        )

    if resulting.interpretation_status != "INTERPRETED":
        return "The proposed requirement is still uncertain and cannot update the workspace."

    gate_is_mandatory = resulting.gate_type == GateType.MANDATORY.value
    if resulting.compulsory is None or resulting.compulsory != gate_is_mandatory:
        return (
            "The proposed gate_type and compulsory value are inconsistent; elevated review "
            "is required."
        )

    source_text = payload.source.text
    source_normalised = _normalised_text(source_text)
    evidence_text = resulting.source.snippet
    directed_evidence = _directed_new_value_span(evidence_text)
    directed_normalised = _normalised_text(directed_evidence)
    semantic_fields = changed_fields - {"text"}
    if not semantic_fields:
        if _normalised_text(resulting.text) not in source_normalised:
            return (
                "A wording-only change is applyable only when the proposed wording is an exact "
                "contiguous part of the supplied source."
            )
        return None

    text_is_exact = _normalised_text(resulting.text) in source_normalised
    text_is_safe_canonical_staff = bool(
        target.rule_config.get("kind") == "certified_staff"
        and resulting.minimum_count is not None
        and resulting.certification
        and _normalised_text(resulting.text)
        == _normalised_text(
            _canonical_staff_text(resulting.minimum_count, resulting.certification)
        )
    )
    if not text_is_exact and not text_is_safe_canonical_staff:
        return (
            "The proposed requirement wording is neither an exact source excerpt nor a "
            "supported deterministic rendering of the grounded field changes."
        )

    if "minimum_count" in semantic_fields:
        if resulting.minimum_count is None:
            if target.rule_config.get("kind") == "certified_staff":
                return (
                    "Removing minimum_count would make the configured certified-staff rule "
                    "incomplete; elevated review is required."
                )
            removed = bool(
                re.search(
                    r"\b(?:minimum|minimum\s+count|personnel\s+count|staff\s+count)\b"
                    r"[^.;\n]{0,80}\b(?:removed|deleted|withdrawn|no\s+longer|required\s+number\s+is\s+not\s+specified)\b",
                    source_text,
                    flags=re.IGNORECASE,
                )
            )
            if not removed:
                return "Removal of minimum_count is not explicit in the supplied source."
        else:
            count_values = _explicit_count_values(directed_evidence)
            if len(count_values) > 1:
                return (
                    "The directed new-value wording contains multiple possible minimum counts; "
                    "elevated review is required."
                )
            if resulting.minimum_count not in count_values:
                return (
                    f"minimum_count={resulting.minimum_count} is not explicitly grounded in the "
                    "supplied source."
                )

    if "certification" in semantic_fields:
        if resulting.certification is None:
            if target.rule_config.get("kind") == "certified_staff":
                return (
                    "Removing certification would make the configured certified-staff rule "
                    "incomplete; elevated review is required."
                )
            prior = target.rule_config.get("certification")
            removed = bool(
                prior
                and str(prior).casefold() in source_normalised
                and re.search(
                    r"\b(?:certification|certificate|qualification)\b[^.;\n]{0,80}"
                    r"\b(?:removed|deleted|withdrawn|no\s+longer\s+required|not\s+required)\b",
                    source_text,
                    flags=re.IGNORECASE,
                )
            )
            if not removed:
                return "Removal of certification is not explicit in the supplied source."
        elif _normalised_text(resulting.certification) not in directed_normalised:
            return (
                f"certification={resulting.certification} is not explicitly grounded in the "
                "supplied source."
            )

    if "deadline" in semantic_fields:
        if resulting.deadline is None:
            removed = bool(
                re.search(
                    r"\b(?:deadline|closing|submission\s+date)\b[^.;\n]{0,80}"
                    r"\b(?:removed|deleted|withdrawn|no\s+longer\s+applies)\b",
                    source_text,
                    flags=re.IGNORECASE,
                )
            )
            if not removed:
                return "Removal of deadline is not explicit in the supplied source."
        elif not _date_is_explicit(resulting.deadline, directed_evidence):
            return "The proposed deadline is not explicitly grounded in the supplied source."

    if "gate_type" in semantic_fields:
        gate_patterns = {
            "MANDATORY": r"\b(?:mandatory|compulsory|required|shall|must)\b",
            "SCORED": r"\b(?:scored|evaluated|quality\s+points?)\b",
            "INFORMATIONAL": r"\b(?:informational|optional|not\s+required|no\s+longer\s+mandatory)\b",
        }
        if resulting.gate_type == "MANDATORY" and re.search(
            r"\b(?:not\s+required|no\s+longer\s+mandatory|optional)\b",
            directed_evidence,
            flags=re.IGNORECASE,
        ):
            return "The proposed mandatory gate contradicts the directed new-value wording."
        if not re.search(
            gate_patterns[resulting.gate_type], directed_evidence, flags=re.IGNORECASE
        ):
            return f"gate_type={resulting.gate_type} is not explicit in the supplied source."

    if "compulsory" in semantic_fields:
        if resulting.compulsory is None:
            return "An uncertain compulsory value cannot be applied automatically."
        pattern = (
            r"\b(?:mandatory|compulsory|required|shall|must)\b"
            if resulting.compulsory
            else r"\b(?:optional|not\s+required|no\s+longer\s+mandatory)\b"
        )
        if resulting.compulsory and re.search(
            r"\b(?:not\s+required|no\s+longer\s+mandatory|optional)\b",
            directed_evidence,
            flags=re.IGNORECASE,
        ):
            return "The proposed compulsory value contradicts the directed new-value wording."
        if not re.search(pattern, directed_evidence, flags=re.IGNORECASE):
            return f"compulsory={resulting.compulsory} is not explicit in the supplied source."

    return None


def _rule_config(
    previous: Requirement,
    resulting: StructuredRequirement,
    changed_fields: set[str],
) -> dict[str, Any]:
    config = dict(previous.rule_config)
    if "procurement_rule" in changed_fields:
        previous_rule = _procurement_rule_from_config(config)
        previous_kind = str(config.get("kind", "")).upper()
        if previous_rule is not None:
            for field_name in type(previous_rule).model_fields:
                config.pop(field_name, None)
        elif previous_kind in _RULE_MODELS:
            config.pop("kind", None)
        if resulting.procurement_rule is None:
            config.pop("facts", None)
            config.pop("evaluation_as_of", None)
        else:
            resulting_kind = str(resulting.procurement_rule.kind)
            if previous_kind != resulting_kind:
                config.pop("facts", None)
                config.pop("evaluation_as_of", None)
            config.update(resulting.procurement_rule.model_dump(mode="json"))

    for field_name, value in (
        ("minimum_count", resulting.minimum_count),
        ("certification", resulting.certification),
        ("compulsory", resulting.compulsory),
    ):
        if field_name not in changed_fields:
            continue
        if value is None:
            config.pop(field_name, None)
        else:
            config[field_name] = value

    if "deadline" in changed_fields:
        rule = _procurement_rule_from_config(config)
        if isinstance(rule, ProcessingWindowRule):
            config["deadline"] = (
                resulting.deadline.isoformat() if resulting.deadline is not None else None
            )

    if "structured_fields" in changed_fields:
        previous_rule = _procurement_rule_from_config(previous.rule_config)
        for item in _structured_fields_from_config(previous.rule_config, previous_rule):
            config.pop(item.name, None)
        for item in resulting.structured_fields:
            config[item.name] = item.value
    return config


def _persisted_requirement_type(
    previous: Requirement,
    resulting: StructuredRequirement,
    changed_fields: set[str],
) -> str:
    if "requirement_type" in changed_fields:
        return resulting.requirement_type
    return previous.requirement_type


def _snapshot(
    requirement: Requirement,
    assessment_status: str,
    *,
    requirement_id: str | None = None,
) -> RequirementSnapshot:
    return RequirementSnapshot(
        id=requirement_id or requirement.id,
        stable_key=requirement.stable_key,
        version=requirement.version,
        text=requirement.text,
        requirement_type=requirement.requirement_type,
        gate_type=requirement.gate_type,
        minimum_count=requirement.rule_config.get("minimum_count"),
        certification=requirement.rule_config.get("certification"),
        assessment=assessment_status,
    )


def _result_snapshot(
    previous: Requirement,
    resulting: StructuredRequirement,
    assessment_status: str,
    changed_fields: set[str],
) -> RequirementSnapshot:
    config = _rule_config(previous, resulting, changed_fields)
    return RequirementSnapshot(
        id="PROPOSED_NOT_PERSISTED",
        stable_key=previous.stable_key,
        version=previous.version + 1,
        text=resulting.text,
        requirement_type=_persisted_requirement_type(previous, resulting, changed_fields),
        gate_type=resulting.gate_type,
        minimum_count=config.get("minimum_count"),
        certification=config.get("certification"),
        assessment=assessment_status,
    )


def _source_hash(payload: AmendmentPreviewRequest) -> str:
    canonical = json.dumps(
        payload.source.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _source_document_reference(payload: AmendmentPreviewRequest) -> str:
    identity = json.dumps(
        {
            "document_name": payload.source.document_name,
            "document_version": payload.source.document_version,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return f"user-supplied-metadata://sha256:{digest}"


def _existing_source_document(
    session: Session,
    bid_id: str,
    payload: AmendmentPreviewRequest,
) -> TenderDocument | None:
    document = session.scalar(
        select(TenderDocument).where(
            TenderDocument.tender_id == bid_id,
            TenderDocument.filename == payload.source.document_name,
            TenderDocument.version == payload.source.document_version,
        )
    )
    if document is None:
        return None
    if document.document_type != "CORRIGENDUM":
        raise AmendmentSourceVersionConflictError(
            "That source filename and version already identify a different document type. "
            "Use the amendment's actual corrigendum filename and version."
        )
    return document


def _state_fingerprint(
    session: Session,
    tender: Tender,
    requirement: Requirement,
) -> str:
    requirements = current_requirements(session, tender.id)
    employees = session.scalars(
        select(Employee)
        .where(Employee.company_id == tender.company_id)
        .order_by(Employee.id)
    ).all()
    evidence = session.scalars(
        select(Evidence)
        .where(Evidence.company_id == tender.company_id)
        .order_by(Evidence.id)
    ).all()
    tasks = session.scalars(
        select(Task).where(Task.tender_id == tender.id).order_by(Task.id)
    ).all()
    task_ids = [item.id for item in tasks]
    dependencies = (
        session.execute(
            select(TaskDependency.task_id, TaskDependency.depends_on_task_id)
            .where(TaskDependency.task_id.in_(task_ids))
            .order_by(TaskDependency.task_id, TaskDependency.depends_on_task_id)
        ).all()
        if task_ids
        else []
    )
    payload = {
        "tender": {
            "id": tender.id,
            "closing_at": tender.closing_at.isoformat(),
            "operational_status": tender.operational_status,
            "previous_operational_status": tender.previous_operational_status,
            "submission_coverage": tender.submission_coverage,
            "deadline_risk": tender.deadline_risk,
        },
        "selected_requirement_id": requirement.id,
        "requirements": [
            {
                "id": item.id,
                "stable_key": item.stable_key,
                "version": item.version,
                "text": item.text,
                "requirement_type": item.requirement_type,
                "gate_type": item.gate_type,
                "deadline": item.deadline.isoformat() if item.deadline else None,
                "source_document_id": item.source_document_id,
                "source_document": item.source_document.filename,
                "source_document_version": item.source_document.version,
                "source_page": item.source_page,
                "source_section": item.source_section,
                "source_snippet": item.source_snippet,
                "supersedes_requirement_id": item.supersedes_requirement_id,
                "rule_config": item.rule_config,
                "assessment": (
                    {
                        "id": assessment.id,
                        "status": assessment.status,
                        "evidence_ids": assessment.evidence_ids,
                        "reason_summary": assessment.reason_summary,
                        "assessed_at": assessment.assessed_at.isoformat(),
                        "assessment_method": assessment.assessment_method,
                    }
                    if (assessment := latest_assessment(session, item.id)) is not None
                    else None
                ),
            }
            for item in requirements
        ],
        "employees": [
            {
                "id": item.id,
                "name": item.name,
                "role": item.role,
                "employment_status": item.employment_status,
                "availability_status": item.availability_status,
                "experience_years": item.experience_years,
            }
            for item in employees
        ],
        "evidence": [
            {
                "id": item.id,
                "type": item.type,
                "title": item.title,
                "subject_type": item.subject_type,
                "subject_id": item.subject_id,
                "source_file": item.source_file,
                "details": item.details,
                "valid_from": item.valid_from.isoformat() if item.valid_from else None,
                "verification_status": item.verification_status,
                "valid_until": item.valid_until.isoformat() if item.valid_until else None,
                "verified_at": item.verified_at.isoformat() if item.verified_at else None,
                "updated_at": item.updated_at.isoformat(),
            }
            for item in evidence
        ],
        "tasks": [
            {
                "id": item.id,
                "requirement_id": item.requirement_id,
                "title": item.title,
                "description": item.description,
                "owner": item.owner,
                "status": item.status,
                "priority": item.priority,
                "due_at": item.due_at.isoformat(),
                "latest_safe_at": (
                    item.latest_safe_at.isoformat() if item.latest_safe_at else None
                ),
                "estimated_duration_hours": item.estimated_duration_hours,
                "recovery_path": item.recovery_path,
                "updated_at": item.updated_at.isoformat(),
                "completed_at": item.completed_at.isoformat() if item.completed_at else None,
            }
            for item in tasks
        ],
        "task_dependencies": [list(item) for item in dependencies],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _transient_requirement(
    previous: Requirement,
    resulting: StructuredRequirement,
    changed_fields: set[str],
) -> Requirement:
    return Requirement(
        id="PREVIEW-NOT-PERSISTED",
        stable_key=previous.stable_key,
        tender_id=previous.tender_id,
        version=previous.version + 1,
        text=resulting.text,
        requirement_type=_persisted_requirement_type(previous, resulting, changed_fields),
        gate_type=resulting.gate_type,
        deadline=resulting.deadline,
        source_document_id=previous.source_document_id,
        source_page=resulting.source.page,
        source_section=resulting.source.section,
        source_snippet=resulting.source.snippet,
        supersedes_requirement_id=previous.id,
        rule_config=_rule_config(previous, resulting, changed_fields),
        created_at=now(),
    )


def _planned_tasks(
    session: Session,
    tender: Tender,
    target: Requirement,
    proposed: Requirement,
    result: AssessmentResult,
) -> list[PlannedTask]:
    if result.status != AssessmentStatus.PARTIAL or not result.recovery_candidate_ids:
        return []
    required_count = int(proposed.rule_config.get("minimum_count", 0))
    candidates_needed = max(1, required_count - len(result.usable_employee_ids))
    candidate_ids = result.recovery_candidate_ids[:candidates_needed]
    if len(candidate_ids) < candidates_needed:
        return []
    candidates = [session.get(Employee, candidate_id) for candidate_id in candidate_ids]
    anchor = now()
    verification_due = min(anchor + timedelta(days=2), tender.closing_at - timedelta(days=4))
    if verification_due <= anchor:
        verification_due = anchor + timedelta(hours=4)
    response_due = max(verification_due + timedelta(hours=4), tender.closing_at - timedelta(days=2))
    recheck_due = max(response_due + timedelta(hours=2), tender.closing_at - timedelta(hours=29))
    tasks: list[PlannedTask] = []
    prerequisite_keys: list[str] = []
    for index, candidate in enumerate(candidates, start=1):
        candidate_name = candidate.name if candidate else f"recovery candidate {index}"
        suffix = "" if len(candidates) == 1 else f"_{index}"
        evidence_key = f"VERIFY_EVIDENCE{suffix}"
        availability_key = f"CONFIRM_AVAILABILITY{suffix}"
        prerequisite_keys.extend([evidence_key, availability_key])
        tasks.extend(
            [
                PlannedTask(
                    key=evidence_key,
                    title=f"Verify current evidence for {candidate_name}",
                    description=(
                        f"Close the missing or stale evidence needed before {candidate_name} "
                        f"can count towards {target.stable_key}."
                    ),
                    owner="Bid Team",
                    status="OPEN",
                    priority="CRITICAL",
                    due_at=verification_due,
                    latest_safe_at=verification_due,
                    estimated_duration_hours=2,
                ),
                PlannedTask(
                    key=availability_key,
                    title=f"Confirm delivery availability for {candidate_name}",
                    description=(
                        "Record an accountable delivery-owner confirmation for the service "
                        "window."
                    ),
                    owner="Delivery Owner",
                    status="OPEN",
                    priority="CRITICAL",
                    due_at=verification_due,
                    latest_safe_at=verification_due,
                    estimated_duration_hours=1,
                ),
            ]
        )
    tasks.extend(
        [
        PlannedTask(
            key="UPDATE_RESPONSE",
            title=f"Update the {target.stable_key} response schedule",
            description="Update the internal response only after evidence and availability checks pass.",
            owner="Bid Team",
            status="WAITING",
            priority="HIGH",
            due_at=response_due,
            latest_safe_at=response_due,
            estimated_duration_hours=2,
            depends_on=prerequisite_keys,
        ),
        PlannedTask(
            key="REASSESS",
            title=f"Re-run {target.stable_key} verification",
            description="Recalculate the requirement only after the updated response is ready.",
            owner="Compliance Owner",
            status="WAITING",
            priority="CRITICAL",
            due_at=recheck_due,
            latest_safe_at=recheck_due,
            estimated_duration_hours=1,
            depends_on=["UPDATE_RESPONSE"],
        ),
        ]
    )
    return tasks


def _risk_from_slack(hours: float) -> str:
    if hours < 0:
        return "MISSED"
    if hours <= 12:
        return "HIGH"
    if hours <= 48:
        return "MEDIUM"
    return "LOW"


def _project_deadline_risk(
    session: Session,
    tender: Tender,
    planned_tasks: list[PlannedTask],
) -> tuple[str, str]:
    before_trace = deadline_risk_trace(session, tender)
    slacks = [item["slack_hours"] for item in before_trace["tasks"]]
    anchor = now()
    slacks.extend(
        (
            task.latest_safe_at - anchor - timedelta(hours=task.estimated_duration_hours)
        ).total_seconds()
        / 3600
        for task in planned_tasks
    )
    after = _risk_from_slack(min(slacks)) if slacks else "LOW"
    return before_trace["risk"], after


def _recovery_is_viable(tender: Tender, tasks: list[PlannedTask]) -> bool:
    anchor = now()
    return bool(tasks) and all(
        task.latest_safe_at < tender.closing_at
        and task.latest_safe_at - timedelta(hours=task.estimated_duration_hours) >= anchor
        for task in tasks
    )


def _project_operational_status(
    session: Session,
    tender: Tender,
    target: Requirement,
    proposed_gate_type: str,
    proposed_status: str,
    planned_tasks: list[PlannedTask],
) -> str:
    blocked = False
    uncertain = False
    recoverable = False
    for requirement in current_requirements(session, tender.id):
        gate_type = proposed_gate_type if requirement.id == target.id else requirement.gate_type
        if gate_type != GateType.MANDATORY.value:
            continue
        if requirement.id == target.id:
            status = proposed_status
            has_recovery = _recovery_is_viable(tender, planned_tasks)
        else:
            assessment = latest_assessment(session, requirement.id)
            status = assessment.status if assessment else AssessmentStatus.UNCERTAIN.value
            recovery = session.scalars(
                select(Task).where(
                    Task.tender_id == tender.id,
                    Task.requirement_id == requirement.id,
                    Task.recovery_path.is_(True),
                )
            ).all()
            has_recovery = bool(recovery) and all(
                task.status != TaskStatus.BLOCKED.value
                and (task.latest_safe_at or task.due_at) < tender.closing_at
                for task in recovery
            )
        if status == AssessmentStatus.SATISFIED.value:
            continue
        if status == AssessmentStatus.UNCERTAIN.value:
            uncertain = True
        elif status == AssessmentStatus.PARTIAL.value and has_recovery:
            recoverable = True
        else:
            blocked = True
    if blocked:
        return "BLOCKED"
    if uncertain:
        return "UNCERTAIN"
    if recoverable:
        return "RECOVERABLE"
    return "FEASIBLE"


def _project_coverage(
    session: Session,
    tender: Tender,
    target: Requirement,
    previous_status: str,
    proposed_gate_type: str,
    proposed_status: str,
    planned_task_count: int,
) -> tuple[int, int]:
    trace = submission_coverage_trace(session, tender)
    requirements = trace["components"]["requirements"]
    evidence = trace["components"]["evidence"]
    tasks = trace["components"]["tasks"]
    weights = {"MANDATORY": 3.0, "SCORED": 1.0, "INFORMATIONAL": 0.0}
    contributions = {
        "SATISFIED": 1.0,
        "PARTIAL": 0.5,
        "UNMET": 0.0,
        "UNCERTAIN": 0.0,
        "SUPERSEDED": 0.0,
    }
    old_weight = weights[target.gate_type]
    new_weight = weights[proposed_gate_type]
    complete = (
        requirements["completed_units"]
        - old_weight * contributions.get(previous_status, 0.0)
        + new_weight * contributions.get(proposed_status, 0.0)
    )
    total = requirements["total_units"] - old_weight + new_weight
    requirement_percent = 100 * complete / total if total else 100.0
    evidence_percent = evidence["percent"]
    task_total = tasks["total_units"] + planned_task_count
    task_percent = 100 * tasks["completed_units"] / task_total if task_total else 100.0
    after = round(
        0.50 * requirement_percent + 0.30 * evidence_percent + 0.20 * task_percent
    )
    return trace["display_percent"], after


def _impact_preview(
    session: Session,
    tender: Tender,
    target: Requirement,
    resulting: StructuredRequirement,
    assessment_result: AssessmentResult,
    planned_tasks: list[PlannedTask],
) -> AmendmentImpactPreview:
    old_assessment = latest_assessment(session, target.id)
    old_status = old_assessment.status if old_assessment else AssessmentStatus.UNCERTAIN.value
    gates = critical_gate_trace(session, tender.id)
    old_verified = gates["verified"]
    old_total = gates["total"]
    old_is_verified_gate = (
        target.gate_type == GateType.MANDATORY.value
        and old_status == AssessmentStatus.SATISFIED.value
    )
    new_is_verified_gate = (
        resulting.gate_type == GateType.MANDATORY.value
        and assessment_result.status == AssessmentStatus.SATISFIED
    )
    after_verified = old_verified - int(old_is_verified_gate) + int(new_is_verified_gate)
    after_total = (
        old_total
        - int(target.gate_type == GateType.MANDATORY.value)
        + int(resulting.gate_type == GateType.MANDATORY.value)
    )
    coverage_before, coverage_after = _project_coverage(
        session,
        tender,
        target,
        old_status,
        resulting.gate_type,
        assessment_result.status.value,
        len(planned_tasks),
    )
    deadline_before, deadline_after = _project_deadline_risk(session, tender, planned_tasks)
    return AmendmentImpactPreview(
        assessment_before=old_status,
        assessment_after=assessment_result.status.value,
        operational_status_before=derive_operational_status(session, tender).value,
        operational_status_after=_project_operational_status(
            session,
            tender,
            target,
            resulting.gate_type,
            assessment_result.status.value,
            planned_tasks,
        ),
        critical_gates_before=f"{old_verified} / {old_total}",
        critical_gates_after=f"{after_verified} / {after_total}",
        submission_coverage_before=coverage_before,
        submission_coverage_after=coverage_after,
        deadline_risk_before=deadline_before,
        deadline_risk_after=deadline_after,
        calculation_note=(
            "Dry-run only. Deterministic rules use the current Evidence Registry and count the "
            "proposed open recovery tasks; no bid record is changed during preview."
        ),
    )


def _clarification(
    payload: AmendmentPreviewRequest,
    reason: str,
) -> ClarificationDraft:
    reference = (
        f"{payload.source.document_name}, page {payload.source.page}, "
        f"section {payload.source.section}"
    )
    return ClarificationDraft(
        reason=reason,
        question=(
            f"Please clarify the intended change in {reference}. Which tracked obligation is "
            "affected, and what exact value, scope, qualification or deadline replaces the "
            "current wording?"
        ),
        source_reference=reference,
    )


def _prune_previews() -> None:
    cutoff = time.monotonic() - _PREVIEW_TTL_SECONDS
    expired = [key for key, item in _PREVIEWS.items() if item.created_monotonic < cutoff]
    for key in expired:
        _PREVIEWS.pop(key, None)
    if len(_PREVIEWS) > _MAX_PREVIEWS:
        oldest = sorted(_PREVIEWS.items(), key=lambda item: item[1].created_monotonic)
        for key, _ in oldest[: len(_PREVIEWS) - _MAX_PREVIEWS]:
            _PREVIEWS.pop(key, None)


def preview_amendment(
    session: Session,
    bid_id: str,
    payload: AmendmentPreviewRequest,
    *,
    interpretation_service: TenderInterpreter | None = None,
) -> AmendmentPreviewResponse:
    tender = session.get(Tender, bid_id)
    if tender is None:
        raise LookupError("Bid not found.")
    target = session.get(Requirement, payload.requirement_id)
    if target is None or target.tender_id != bid_id:
        raise LookupError("Tracked requirement not found for this bid.")
    current = {item.stable_key: item for item in current_requirements(session, bid_id)}
    if current.get(target.stable_key) is None or current[target.stable_key].id != target.id:
        raise AmendmentPreviewStaleError(
            "The selected requirement is historical. Preview the current version instead."
        )
    old_assessment = latest_assessment(session, target.id)
    old_status = old_assessment.status if old_assessment else AssessmentStatus.UNCERTAIN.value
    source_hash = _source_hash(payload)
    _existing_source_document(session, bid_id, payload)
    trace = [
        WorkflowStep(
            step=1,
            node="validate_source",
            status="DONE",
            detail=f"Exact user-supplied text locked to SHA-256 {source_hash[:12]}…",
        ),
        WorkflowStep(
            step=2,
            node="match_requirement",
            status="DONE",
            detail=f"Human-selected current target {target.stable_key} v{target.version} validated.",
        ),
    ]
    target_reference_failure = _target_reference_failure(payload, target)
    if target_reference_failure:
        interpretation = ChangeInterpretationEnvelope(
            mode="DEMO_FALLBACK",
            fallback_reason="Source-to-target validation failed before provider invocation.",
            attempts=0,
            result=ChangeInterpretationResult(
                change_type="UNCHANGED",
                affected_stable_key=None,
                changed_fields=[],
                resulting_requirement=None,
                interpretation_status="UNCERTAIN",
                uncertainty_reason=target_reference_failure,
                reason_summary="The supplied source does not identify the selected target.",
            ),
        )
    else:
        interpreter = interpretation_service or _INTERPRETER
        interpretation = interpreter.interpret_change(
            ChangeInterpretationRequest(
                existing_requirement=_structured_requirement(target),
                corrigendum_document=payload.source.document_name,
                page=payload.source.page,
                section=payload.source.section,
                text=payload.source.text,
            )
        )
    change = interpretation.result
    trace.append(
        WorkflowStep(
            step=3,
            node="interpret_change",
            status="DONE" if change.interpretation_status == "INTERPRETED" else "BLOCKED",
            detail=(
                f"{interpretation.mode} returned {change.interpretation_status}: "
                f"{change.reason_summary}"
            ),
        )
    )

    state: str
    apply_allowed = False
    block_reason: str | None = None
    proposed = None
    impact = None
    planned_tasks: list[PlannedTask] = []
    clarification = None
    resulting = change.resulting_requirement
    changed_field_names = {item.field for item in change.changed_fields}
    if target_reference_failure:
        state = "REVIEW_REQUIRED"
        block_reason = target_reference_failure
    elif change.interpretation_status != "INTERPRETED":
        state = "REVIEW_REQUIRED"
        block_reason = change.uncertainty_reason or "The change could not be interpreted safely."
    elif change.change_type == "UNCHANGED":
        state = "NO_TRACKED_CHANGE"
        block_reason = "No precise semantic change to the selected requirement was found."
    elif change.change_type != "MODIFIED":
        state = "REVIEW_REQUIRED"
        block_reason = (
            f"{change.change_type} lifecycle changes require a separate elevated review; "
            "this version only applies precise modifications."
        )
    elif change.affected_stable_key != target.stable_key or resulting is None:
        state = "REVIEW_REQUIRED"
        block_reason = "The interpreted target does not match the selected current requirement."
    elif resulting.interpretation_status != "INTERPRETED":
        state = "REVIEW_REQUIRED"
        block_reason = (
            resulting.uncertainty_reason
            or "The proposed requirement remains uncertain and cannot be applied."
        )
    elif resulting.source.snippet not in payload.source.text:
        state = "REVIEW_REQUIRED"
        block_reason = "The proposed change is not backed by an exact source excerpt."
    elif grounding_failure := _change_grounding_failure(
        payload,
        target,
        resulting,
        changed_field_names,
    ):
        state = "REVIEW_REQUIRED"
        block_reason = grounding_failure
    else:
        transient = _transient_requirement(target, resulting, changed_field_names)
        assessment_result = assess_requirement(session, transient)
        planned_tasks = _planned_tasks(
            session,
            tender,
            target,
            transient,
            assessment_result,
        )
        proposed = _result_snapshot(
            target,
            resulting,
            assessment_result.status.value,
            changed_field_names,
        )
        impact = _impact_preview(
            session,
            tender,
            target,
            resulting,
            assessment_result,
            planned_tasks,
        )
        state = "PREVIEW_READY"
        apply_allowed = True
        trace.extend(
            [
                WorkflowStep(
                    step=4,
                    node="dry_run_impact",
                    status="DONE",
                    detail=(
                        f"Assessment {old_status} → {assessment_result.status.value}; "
                        f"workspace status {impact.operational_status_before} → "
                        f"{impact.operational_status_after}."
                    ),
                ),
                WorkflowStep(
                    step=5,
                    node="plan_recovery",
                    status="DONE" if planned_tasks else "SKIPPED",
                    detail=(
                        f"{len(planned_tasks)} dependency-aware recovery tasks proposed."
                        if planned_tasks
                        else "No deterministic recovery task set is available or required."
                    ),
                ),
            ]
        )

    if not apply_allowed:
        clarification = _clarification(payload, block_reason or "Human review is required.")
        trace.append(
            WorkflowStep(
                step=4,
                node="clarification_checkpoint",
                status="BLOCKED",
                detail="Workspace update is locked; a copy-only clarification draft was prepared.",
            )
        )
    trace.append(
        WorkflowStep(
            step=max(item.step for item in trace) + 1,
            node="human_checkpoint",
            status="DONE" if apply_allowed else "BLOCKED",
            detail=(
                "A person must review the source, target and field changes before any write."
                if apply_allowed
                else "Confirmation remains disabled until the ambiguity is resolved."
            ),
        )
    )
    preview_id = uuid4().hex
    response = AmendmentPreviewResponse(
        preview_id=preview_id,
        state=state,  # type: ignore[arg-type]
        apply_allowed=apply_allowed,
        block_reason=block_reason,
        source=SourceProof(
            document_name=payload.source.document_name,
            document_version=payload.source.document_version,
            page=payload.source.page,
            section=payload.source.section,
            exact_excerpt=payload.source.text,
            sha256=source_hash,
        ),
        target=_snapshot(target, old_status),
        proposed=proposed,
        change_type=change.change_type,
        changed_fields=[
            FieldDiff(
                field=item.field,
                old_value=_display(item.old_value),
                new_value=_display(item.new_value),
            )
            for item in change.changed_fields
        ],
        reason_summary=change.reason_summary,
        interpretation_mode=interpretation.mode,
        model_id=interpretation.model_id,
        fallback_reason=interpretation.fallback_reason,
        impact=impact,
        planned_tasks=planned_tasks,
        clarification=clarification,
        workflow_trace=trace,
        human_checkpoint=(
            "BidOps proposes an update to the internal bid record. Confirm that the source "
            "excerpt, affected requirement and field changes match the amendment. Confirming "
            "will version the workspace and recalculate assessments. It will not accept terms, "
            "contact GeBIZ or submit a bid."
        ),
    )
    record = _StoredPreview(
        response=response,
        request=payload,
        interpretation=interpretation,
        base_fingerprint=_state_fingerprint(session, tender, target),
        created_monotonic=time.monotonic(),
    )
    with _PREVIEW_LOCK:
        _prune_previews()
        _PREVIEWS[preview_id] = record
    return response


def _activity(
    session: Session,
    tender_id: str,
    event_type: str,
    entity_id: str,
    summary: str,
    actor: str = "system",
) -> None:
    session.add(
        ActivityEvent(
            id=f"ACT-{uuid4().hex[:12]}",
            tender_id=tender_id,
            event_type=event_type,
            actor=actor,
            entity_id=entity_id,
            summary=summary,
            timestamp=now(),
        )
    )


def _record_for_apply(preview_id: str) -> _StoredPreview:
    with _PREVIEW_LOCK:
        _prune_previews()
        record = _PREVIEWS.get(preview_id)
    if record is None:
        raise AmendmentPreviewExpiredError(
            "This preview is missing or expired. Analyse the amendment again."
        )
    return record


def apply_amendment_preview(
    session: Session,
    bid_id: str,
    payload: AmendmentApplyRequest,
) -> str:
    record = _record_for_apply(payload.preview_id)
    if record.applied:
        raise AmendmentAlreadyAppliedError("This amendment preview has already been applied.")
    if not record.response.apply_allowed:
        raise AmendmentApplyBlockedError(
            record.response.block_reason or "This preview is not safe to apply."
        )
    target = session.get(Requirement, record.request.requirement_id)
    tender = session.get(Tender, bid_id)
    if target is None or tender is None or target.tender_id != bid_id:
        raise AmendmentPreviewStaleError("The bid or target requirement no longer matches.")
    current = {item.stable_key: item for item in current_requirements(session, bid_id)}
    if current.get(target.stable_key) is None or current[target.stable_key].id != target.id:
        raise AmendmentPreviewStaleError(
            "The target requirement changed after preview. Analyse the amendment again."
        )
    if _state_fingerprint(session, tender, target) != record.base_fingerprint:
        raise AmendmentPreviewStaleError(
            "Bid evidence or requirement state changed after preview. Analyse it again."
        )
    change = record.interpretation.result
    resulting = change.resulting_requirement
    if (
        change.interpretation_status != "INTERPRETED"
        or change.change_type != "MODIFIED"
        or resulting is None
        or resulting.interpretation_status != "INTERPRETED"
        or change.affected_stable_key != target.stable_key
    ):
        raise AmendmentApplyBlockedError("The stored interpretation is not a safe modification.")
    target_reference_failure = _target_reference_failure(record.request, target)
    if target_reference_failure:
        raise AmendmentApplyBlockedError(target_reference_failure)
    changed_field_names = {item.field for item in change.changed_fields}
    grounding_failure = _change_grounding_failure(
        record.request,
        target,
        resulting,
        changed_field_names,
    )
    if grounding_failure:
        raise AmendmentApplyBlockedError(grounding_failure)
    if record.response.impact is not None:
        current_deadline_risk = calculate_deadline_risk(session, tender).value
        if current_deadline_risk != record.response.impact.deadline_risk_before:
            raise AmendmentPreviewStaleError(
                "Deadline risk changed after preview. Analyse the amendment again."
            )
        if (
            record.response.impact.assessment_after == AssessmentStatus.PARTIAL.value
            and not _recovery_is_viable(tender, record.response.planned_tasks)
        ):
            raise AmendmentPreviewStaleError(
                "The recovery window changed after preview. Analyse the amendment again."
            )

    token = payload.preview_id[:12].upper()
    event_id = f"CHANGE-AMEND-{token}"
    if session.get(ChangeEvent, event_id) is not None:
        raise AmendmentAlreadyAppliedError("This amendment preview has already been applied.")
    previous_status = tender.operational_status
    previous_assessment = latest_assessment(session, target.id)
    if previous_assessment is None:
        raise AmendmentApplyBlockedError(
            "The current requirement has no assessment to supersede safely."
        )
    with _PREVIEW_LOCK:
        if record.applied or record.applying:
            raise AmendmentAlreadyAppliedError(
                "This amendment preview has already been applied or is being applied."
            )
        record.applying = True
    try:
        document = _existing_source_document(
            session,
            bid_id,
            record.request,
        )
        document_is_new = document is None
        if document is None:
            document = TenderDocument(
                id=f"DOC-AMEND-{token}",
                tender_id=bid_id,
                filename=record.request.source.document_name,
                document_type="CORRIGENDUM",
                version=record.request.source.document_version,
                uploaded_at=now(),
                text_content_reference=_source_document_reference(record.request),
            )
        safe_key = re.sub(r"[^A-Za-z0-9_-]", "-", target.stable_key)[:50]
        updated = Requirement(
            id=f"REQ-{safe_key}-V{target.version + 1}-{token}",
            stable_key=target.stable_key,
            tender_id=bid_id,
            version=target.version + 1,
            text=resulting.text,
            requirement_type=_persisted_requirement_type(
                target,
                resulting,
                changed_field_names,
            ),
            gate_type=resulting.gate_type,
            deadline=resulting.deadline,
            source_document_id=document.id,
            source_page=resulting.source.page,
            source_section=resulting.source.section,
            source_snippet=resulting.source.snippet,
            supersedes_requirement_id=target.id,
            rule_config=_rule_config(target, resulting, changed_field_names),
            created_at=now(),
        )
        previous_assessment.status = AssessmentStatus.SUPERSEDED.value
        if document_is_new:
            session.add(document)
        session.add(updated)
        session.flush()
        assessment_result = assess_requirement(session, updated)
        assessment = Assessment(
            id=f"ASM-{safe_key}-V{updated.version}-{token}",
            requirement_id=updated.id,
            requirement_version=updated.version,
            status=assessment_result.status.value,
            evidence_ids=assessment_result.evidence_ids,
            reason_summary=assessment_result.reason,
            assessed_at=now(),
            assessment_method=(
                "RULE" if assessment_result.status != AssessmentStatus.UNCERTAIN else "HYBRID"
            ),
        )
        event = ChangeEvent(
            id=event_id,
            tender_id=bid_id,
            source_document_id=document.id,
            event_type="GENERIC_REQUIREMENT_MODIFIED",
            detected_at=now(),
            summary=change.reason_summary,
            affected_requirement_ids=[target.id, updated.id],
        )
        session.add_all([assessment, event])

        approvals = session.scalars(
            select(HumanApproval).where(HumanApproval.tender_id == bid_id)
        ).all()
        for approval in approvals:
            _activity(
                session,
                bid_id,
                "HUMAN_APPROVAL_INVALIDATED",
                approval.id,
                "A later confirmed amendment invalidated this earlier internal approval.",
            )

        task_ids: dict[str, str] = {}
        for index, task_preview in enumerate(record.response.planned_tasks, start=1):
            task_id = f"TASK-AM-{token}-{index}"
            task_ids[task_preview.key] = task_id
            session.add(
                Task(
                    id=task_id,
                    tender_id=bid_id,
                    requirement_id=updated.id,
                    title=task_preview.title,
                    description=task_preview.description,
                    owner=task_preview.owner,
                    status=task_preview.status,
                    priority=task_preview.priority,
                    due_at=task_preview.due_at,
                    latest_safe_at=task_preview.latest_safe_at,
                    estimated_duration_hours=task_preview.estimated_duration_hours,
                    recovery_path=True,
                    created_at=now(),
                    updated_at=now(),
                )
            )
        session.flush()
        for task_preview in record.response.planned_tasks:
            for dependency in task_preview.depends_on:
                session.add(
                    TaskDependency(
                        task_id=task_ids[task_preview.key],
                        depends_on_task_id=task_ids[dependency],
                    )
                )

        _activity(
            session,
            bid_id,
            "INTERPRETATION_COMPLETED",
            target.stable_key,
            (
                f"{record.interpretation.mode}: MODIFIED matched to {target.stable_key}; "
                f"changed fields: {', '.join(item.field for item in change.changed_fields)}."
            ),
            actor=record.interpretation.mode.lower(),
        )
        _activity(
            session,
            bid_id,
            "AMENDMENT_CONFIRMED",
            event.id,
            (
                f"{payload.confirmed_by} confirmed the exact source and field diff for "
                f"{target.stable_key}."
            ),
            actor=payload.confirmed_by,
        )
        _activity(
            session,
            bid_id,
            "REQUIREMENT_VERSION_CREATED",
            updated.id,
            (
                f"{target.stable_key} v{updated.version} created; v{target.version} remains "
                "in the audit history."
            ),
        )
        _activity(
            session,
            bid_id,
            "ASSESSMENT_UPDATED",
            updated.id,
            (
                f"{target.stable_key} v{updated.version} reassessed as "
                f"{assessment_result.status.value}: {assessment_result.reason}"
            ),
        )
        for task_preview in record.response.planned_tasks:
            _activity(
                session,
                bid_id,
                "TASK_CREATED",
                task_ids[task_preview.key],
                f"Recovery task created: {task_preview.title}.",
            )
        session.flush()
        tender.previous_operational_status = previous_status
        tender.operational_status = derive_operational_status(session, tender).value
        tender.submission_coverage = calculate_submission_coverage(session, tender)
        tender.deadline_risk = calculate_deadline_risk(session, tender).value
        tender.human_action_required = True
        _activity(
            session,
            bid_id,
            "OPERATIONAL_STATUS_CHANGED",
            bid_id,
            (
                f"Operational feasibility recalculated: {previous_status} → "
                f"{tender.operational_status}."
            ),
        )
        _activity(
            session,
            bid_id,
            "HUMAN_ACTION_REQUIRED",
            bid_id,
            "A separate human approval is still required for the internal bid package.",
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        with _PREVIEW_LOCK:
            record.applying = False
        if session.get(ChangeEvent, event_id) is not None:
            with _PREVIEW_LOCK:
                record.applied = True
            raise AmendmentAlreadyAppliedError(
                "This amendment preview has already been applied."
            ) from exc
        raise AmendmentPreviewStaleError(
            "Another workspace update conflicted with this preview. Analyse it again."
        ) from exc
    except Exception:
        session.rollback()
        with _PREVIEW_LOCK:
            record.applying = False
        raise
    with _PREVIEW_LOCK:
        record.applying = False
        record.applied = True
    return updated.id
