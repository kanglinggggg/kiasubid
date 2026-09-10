import json
import re
from collections.abc import Callable
from time import perf_counter
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from app.config import Settings, settings
from app.llm.fallback import (
    contains_model_directive,
    interpret_change_fallback,
    interpret_requirement_fallback,
)
from app.llm.prompts import (
    SYSTEM_PROMPT,
    change_prompt,
    change_schema,
    repair_prompt,
    requirement_prompt,
    requirement_schema,
)
from app.llm.provider import JsonModelClient, ModelUnavailable, get_model_client
from app.llm.schemas import (
    ChangeInterpretationEnvelope,
    ChangeInterpretationRequest,
    ChangeInterpretationResult,
    RequirementInterpretationEnvelope,
    RequirementInterpretationRequest,
    RequirementInterpretationResult,
    RequirementSource,
    StructuredField,
    StructuredRequirement,
)
from app.rules.identity import display_qualification_code
from app.rules.schemas import (
    EventAttendanceRule,
    ParticipationRestrictionRule,
    ProcessingWindowRule,
    QualificationRule,
    RequiredDocumentRule,
    SourceFreshnessRule,
)

OutputModel = TypeVar("OutputModel", bound=BaseModel)
PayloadNormalizer = Callable[[dict[str, Any]], dict[str, Any]]

_RULE_REQUIREMENT_TYPE = {
    "EVENT_ATTENDANCE": "ELIGIBILITY",
    "QUALIFICATION": "COMPLIANCE",
    "REQUIRED_DOCUMENT": "DOCUMENT",
    "PROCESSING_WINDOW": "DOCUMENT",
    "PARTICIPATION_RESTRICTION": "ELIGIBILITY",
    "SOURCE_FRESHNESS": "DOCUMENT",
}


class InterpretationFailure(ValueError):
    pass


class InterpretationUnavailable(InterpretationFailure):
    """The selected live provider could not execute, so no accuracy claim is valid."""

    pass


def _json_object(raw: str) -> dict[str, Any]:
    candidate = raw.strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        candidate = "\n".join(lines[1:-1]).strip()
    if not candidate.startswith("{"):
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start >= 0 and end > start:
            candidate = candidate[start : end + 1]
    value = json.loads(candidate)
    if not isinstance(value, dict):
        raise ValueError("model output must be a JSON object")
    return value


def _scalar(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_scalar(item) for item in value]
    if isinstance(value, dict):
        return {key: _scalar(item) for key, item in value.items()}
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _normalize_requirement_json(payload: dict[str, Any]) -> dict[str, Any]:
    """Repair provider vocabulary aliases without inventing procurement facts."""
    requirements = payload.get("requirements")
    if not isinstance(requirements, list):
        return payload
    for requirement in requirements:
        if not isinstance(requirement, dict):
            continue
        rule = requirement.get("procurement_rule")
        kind = rule.get("kind") if isinstance(rule, dict) else None
        if isinstance(kind, str):
            kind = kind.upper()
            rule["kind"] = kind
        requirement_type = requirement.get("requirement_type")
        if isinstance(requirement_type, str):
            requirement_type = requirement_type.upper()
            requirement["requirement_type"] = _RULE_REQUIREMENT_TYPE.get(
                requirement_type, requirement_type
            )
        gate_type = requirement.get("gate_type")
        if isinstance(gate_type, str):
            aliases = {
                "CRITICAL": "MANDATORY",
                "REQUIRED": "MANDATORY",
                "OPTIONAL": "INFORMATIONAL",
                "INFO": "INFORMATIONAL",
            }
            gate_type = gate_type.upper()
            requirement["gate_type"] = aliases.get(gate_type, gate_type)
        fields = requirement.get("structured_fields")
        if isinstance(fields, dict):
            requirement["structured_fields"] = [
                {"name": str(name), "value": value} for name, value in fields.items()
            ]
    return payload


def _field_name_for_document(document: str) -> str:
    tokens = re.findall(r"[a-z0-9]+", document.casefold())
    if "attachment" in tokens and "envelope" in tokens:
        tokens.remove("envelope")
    stem = ("_".join(tokens[:8]) or "document")[:90].rstrip("_")
    return f"{stem}_required"


def _canonical_document_label(document: str, source_text: str) -> str:
    """Distinguish the required artifact from the envelope used to submit it."""
    label = " ".join(document.split())
    if "envelope" in label.casefold() and "attachment" in source_text.casefold():
        label = re.sub(r"\benvelopes?\b", "attachment", label, flags=re.IGNORECASE)
    return label


def _canonicalize_requirement(
    payload: RequirementInterpretationRequest,
    requirement: StructuredRequirement,
    *,
    stable_key: str | None,
) -> StructuredRequirement:
    """Project typed rule data into stable, deterministic requirement fields."""
    rule = requirement.procurement_rule
    requirement_type = requirement.requirement_type
    gate_type = requirement.gate_type
    compulsory = requirement.compulsory
    interpretation_status = requirement.interpretation_status
    uncertainty_reason = requirement.uncertainty_reason
    fields = {item.name: item.value for item in requirement.structured_fields}

    if rule is not None:
        requirement_type = _RULE_REQUIREMENT_TYPE[str(rule.kind)]
        rule_compulsory = getattr(rule, "compulsory", None)
        if hasattr(rule, "compulsory"):
            compulsory = rule_compulsory
            fields["compulsory"] = rule_compulsory
            gate_type = "MANDATORY" if rule_compulsory is True else "INFORMATIONAL"
            if rule_compulsory is None:
                interpretation_status = "UNCERTAIN"
                uncertainty_reason = uncertainty_reason or (
                    "The authoritative source does not establish whether this obligation is "
                    "compulsory."
                )

        if isinstance(rule, EventAttendanceRule):
            fields["attendance_required"] = rule.compulsory is True
        elif isinstance(rule, QualificationRule):
            rule = rule.model_copy(
                update={
                    "options": [
                        option.model_copy(update={"code": display_qualification_code(option.code)})
                        for option in rule.options
                    ]
                }
            )
            if len(rule.options) == 1:
                option = rule.options[0]
                fields["registration_code"] = option.code
                if option.minimum_grade is not None:
                    fields["minimum_financial_grade"] = option.minimum_grade
            else:
                fields["alternative_registration_allowed"] = rule.match == "ANY"
        elif isinstance(rule, RequiredDocumentRule):
            rule = rule.model_copy(
                update={
                    "documents": [
                        _canonical_document_label(document, payload.text)
                        for document in rule.documents
                    ]
                }
            )
            for document in rule.documents:
                fields[_field_name_for_document(document)] = True
        elif isinstance(rule, ProcessingWindowRule):
            fields["minimum_processing_hours"] = rule.minimum_processing_hours
            weeks = rule.minimum_processing_hours / 168
            if weeks.is_integer() and weeks > 0:
                fields["minimum_processing_weeks"] = int(weeks)
        elif isinstance(rule, ParticipationRestrictionRule):
            match = re.search(
                r"\b(?:under|reference(?:d)?(?:\s+as)?|exercise)\s+"
                r"([A-Za-z][A-Za-z0-9./-]*\d[A-Za-z0-9./-]*)\b",
                rule.restriction,
                flags=re.IGNORECASE,
            )
            if match:
                fields.setdefault("shortlist_reference", match.group(1))
        elif isinstance(rule, SourceFreshnessRule):
            fields["latest_version_required"] = rule.latest_version_required

    snippet = requirement.source.snippet
    source = RequirementSource(
        document=payload.document_name,
        page=payload.page,
        section=payload.section,
        snippet=snippet,
    )
    return requirement.model_copy(
        update={
            "stable_key": stable_key,
            "requirement_type": requirement_type,
            "gate_type": gate_type,
            "compulsory": compulsory,
            "procurement_rule": rule,
            "structured_fields": [
                StructuredField(name=name, value=value) for name, value in sorted(fields.items())
            ],
            "interpretation_status": interpretation_status,
            "uncertainty_reason": uncertainty_reason,
            "source": source,
        }
    )


class TenderInterpreter:
    def __init__(
        self,
        client: JsonModelClient | None = None,
        app_settings: Settings = settings,
    ):
        self._settings = app_settings
        self._client = client

    def _configured_client(self) -> JsonModelClient:
        if self._client is not None:
            return self._client
        return get_model_client(self._settings)

    def _invoke(
        self,
        *,
        prompt: str,
        schema: dict[str, Any],
        schema_name: str,
        output_model: type[OutputModel],
        validator: Callable[[OutputModel], None] | None = None,
        normalizer: PayloadNormalizer | None = None,
    ) -> tuple[
        OutputModel,
        int,
        str,
        str,
        float,
        int | None,
        int | None,
        int | None,
    ]:
        client = self._configured_client()
        current_prompt = prompt
        last_error = ""
        last_output = ""
        duration_ms = 0.0
        input_tokens = 0
        output_tokens = 0
        total_tokens = 0
        saw_input_tokens = False
        saw_output_tokens = False
        saw_total_tokens = False
        total_attempts = self._settings.llm_max_retries + 1
        for attempt in range(1, total_attempts + 1):
            started = perf_counter()
            last_output = client.generate_json(
                system=SYSTEM_PROMPT,
                prompt=current_prompt,
                schema=schema,
                schema_name=schema_name,
            )
            measured_duration = round((perf_counter() - started) * 1000, 2)
            invocation = getattr(client, "last_invocation", None)
            duration_ms += getattr(invocation, "duration_ms", measured_duration)
            for field, accumulator in (
                ("input_tokens", "input_tokens"),
                ("output_tokens", "output_tokens"),
                ("total_tokens", "total_tokens"),
            ):
                value = getattr(invocation, field, None)
                if isinstance(value, int):
                    if accumulator == "input_tokens":
                        input_tokens += value
                        saw_input_tokens = True
                    elif accumulator == "output_tokens":
                        output_tokens += value
                        saw_output_tokens = True
                    else:
                        total_tokens += value
                        saw_total_tokens = True
            try:
                raw_payload = _json_object(last_output)
                if normalizer is not None:
                    raw_payload = normalizer(raw_payload)
                result = output_model.model_validate(raw_payload)
                if validator is not None:
                    validator(result)
                return (
                    result,
                    attempt,
                    client.model_id,
                    getattr(client, "mode", "BEDROCK"),
                    round(duration_ms, 2),
                    input_tokens if saw_input_tokens else None,
                    output_tokens if saw_output_tokens else None,
                    total_tokens if saw_total_tokens else None,
                )
            except (ValidationError, ValueError, json.JSONDecodeError) as exc:
                last_error = str(exc)
                current_prompt = repair_prompt(prompt, last_output, last_error)
        raise InterpretationFailure(
            f"Model output failed validation after {total_attempts} attempts: {last_error}"
        )

    def interpret_requirements(
        self,
        payload: RequirementInterpretationRequest,
        *,
        allow_fallback: bool = True,
    ) -> RequirementInterpretationEnvelope:
        if not payload.text.strip():
            return RequirementInterpretationEnvelope(
                mode="DEMO_FALLBACK",
                fallback_reason="No source text supplied; deterministic safety result returned.",
                attempts=0,
                result=interpret_requirement_fallback(payload),
            )
        try:
            (
                result,
                attempts,
                model_id,
                mode,
                duration_ms,
                input_tokens,
                output_tokens,
                total_tokens,
            ) = self._invoke(
                prompt=requirement_prompt(payload),
                schema=requirement_schema(),
                schema_name="tender_requirements",
                output_model=RequirementInterpretationResult,
                normalizer=_normalize_requirement_json,
                validator=lambda result: self._validate_requirements_against_input(
                    payload, result
                ),
            )
            normalized = []
            used_keys: set[str] = set()
            for index, requirement in enumerate(result.requirements):
                candidate_key = requirement.stable_key
                if payload.stable_key_hint and index == 0:
                    candidate_key = payload.stable_key_hint
                elif payload.stable_key_hint and (
                    not candidate_key or candidate_key in used_keys
                ):
                    candidate_key = f"{payload.stable_key_hint}.{index + 1}"
                if candidate_key:
                    used_keys.add(candidate_key)
                normalized.append(
                    _canonicalize_requirement(
                        payload, requirement, stable_key=candidate_key
                    )
                )
            return RequirementInterpretationEnvelope(
                mode=mode,
                model_id=model_id,
                attempts=attempts,
                duration_ms=duration_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                result=RequirementInterpretationResult(requirements=normalized),
            )
        except ModelUnavailable as exc:
            if not allow_fallback:
                raise InterpretationUnavailable(str(exc)) from exc
            return RequirementInterpretationEnvelope(
                mode="DEMO_FALLBACK",
                fallback_reason=str(exc),
                attempts=0,
                result=interpret_requirement_fallback(payload),
            )
        except InterpretationFailure as exc:
            if not allow_fallback:
                raise InterpretationFailure(str(exc)) from exc
            return RequirementInterpretationEnvelope(
                mode="DEMO_FALLBACK",
                fallback_reason=str(exc),
                attempts=(
                    self._settings.llm_max_retries + 1
                ),
                result=interpret_requirement_fallback(payload),
            )

    def interpret_change(
        self,
        payload: ChangeInterpretationRequest,
        *,
        allow_fallback: bool = True,
    ) -> ChangeInterpretationEnvelope:
        if contains_model_directive(payload.text):
            return ChangeInterpretationEnvelope(
                mode="DEMO_FALLBACK",
                fallback_reason=(
                    "Model-directed source text was blocked before any provider invocation."
                ),
                attempts=0,
                result=interpret_change_fallback(payload),
            )
        if not payload.text.strip():
            return ChangeInterpretationEnvelope(
                mode="DEMO_FALLBACK",
                fallback_reason="No corrigendum text supplied; deterministic safety result returned.",
                attempts=0,
                result=interpret_change_fallback(payload),
            )
        try:
            (
                result,
                attempts,
                model_id,
                mode,
                duration_ms,
                input_tokens,
                output_tokens,
                total_tokens,
            ) = self._invoke(
                prompt=change_prompt(payload),
                schema=change_schema(),
                schema_name="corrigendum_change",
                output_model=ChangeInterpretationResult,
                validator=lambda result: self._validate_change_against_input(payload, result),
            )
            deterministic_adapters: list[str] = []
            if result.resulting_requirement is not None:
                candidate = result.resulting_requirement
                snippet = candidate.source.snippet
                if not snippet or snippet not in payload.text:
                    snippet = payload.text
                source = RequirementSource(
                    document=payload.corrigendum_document,
                    page=payload.page,
                    section=payload.section,
                    snippet=snippet,
                )
                rule = candidate.procurement_rule
                if (
                    rule is None
                    and candidate.requirement_type == "DEADLINE"
                    and candidate.deadline is not None
                    and candidate.compulsory is True
                ):
                    rule = ProcessingWindowRule(
                        kind="PROCESSING_WINDOW",
                        action=candidate.text,
                        deadline=candidate.deadline,
                        minimum_processing_hours=0,
                        compulsory=True,
                    )
                    deterministic_adapters.append("DEADLINE_TO_PROCESSING_WINDOW")
                result = result.model_copy(
                    update={
                        "resulting_requirement": candidate.model_copy(
                            update={
                                "source": source,
                                "stable_key": result.affected_stable_key,
                                "procurement_rule": rule,
                            }
                        )
                    }
                )
            return ChangeInterpretationEnvelope(
                mode=mode,
                model_id=model_id,
                attempts=attempts,
                duration_ms=duration_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                deterministic_adapters=deterministic_adapters,
                result=result,
            )
        except ModelUnavailable as exc:
            if not allow_fallback:
                raise InterpretationUnavailable(str(exc)) from exc
            return ChangeInterpretationEnvelope(
                mode="DEMO_FALLBACK",
                fallback_reason=str(exc),
                attempts=0,
                result=interpret_change_fallback(payload),
            )
        except (InterpretationFailure, ValueError) as exc:
            if not allow_fallback:
                raise InterpretationFailure(str(exc)) from exc
            return ChangeInterpretationEnvelope(
                mode="DEMO_FALLBACK",
                fallback_reason=str(exc),
                attempts=(
                    self._settings.llm_max_retries + 1
                ),
                result=interpret_change_fallback(payload),
            )

    @staticmethod
    def _validate_requirements_against_input(
        payload: RequirementInterpretationRequest,
        result: RequirementInterpretationResult,
    ) -> None:
        for index, requirement in enumerate(result.requirements):
            snippet = requirement.source.snippet
            if not snippet or snippet not in payload.text:
                raise ValueError(
                    f"requirements.{index}.source.snippet must be an exact source substring"
                )

    @staticmethod
    def _validate_change_against_input(
        payload: ChangeInterpretationRequest, result: ChangeInterpretationResult
    ) -> None:
        existing = payload.existing_requirement
        resulting = result.resulting_requirement
        if resulting is not None:
            snippet = resulting.source.snippet
            if not snippet or snippet not in payload.text:
                raise ValueError(
                    "resulting_requirement.source.snippet must be an exact corrigendum substring"
                )
        if result.interpretation_status == "UNCERTAIN" and result.change_type != "UNCHANGED":
            raise ValueError("UNCERTAIN output cannot assert a state-changing classification")
        if result.change_type in {"MODIFIED", "REMOVED"}:
            if result.affected_stable_key != existing.stable_key:
                raise ValueError("state-changing output must target the supplied stable requirement")
        for change in result.changed_fields:
            old_value = _scalar(getattr(existing, change.field))
            if _scalar(change.old_value) != old_value:
                raise ValueError(f"changed_fields.{change.field}.old_value does not match input")
            if resulting is not None:
                new_value = _scalar(getattr(resulting, change.field))
                if _scalar(change.new_value) != new_value:
                    raise ValueError(
                        f"changed_fields.{change.field}.new_value does not match result"
                    )
        if result.change_type == "MODIFIED" and resulting is not None:
            semantic_fields = {
                "text",
                "requirement_type",
                "gate_type",
                "deadline",
                "minimum_count",
                "certification",
                "compulsory",
                "structured_fields",
                "procurement_rule",
            }
            actual_fields = {
                field
                for field in semantic_fields
                if _scalar(getattr(existing, field)) != _scalar(getattr(resulting, field))
            }
            reported_fields = {change.field for change in result.changed_fields}
            if actual_fields != reported_fields:
                raise ValueError(
                    "changed_fields must exactly match all changed structured fields: "
                    f"expected {sorted(actual_fields)}, got {sorted(reported_fields)}"
                )
