import re
from typing import Literal

from pydantic import Field

from app.tender_lab.engine import (
    draft_clarifications,
    extract_milestones,
    scan_policy_checks,
)
from app.tender_lab.schemas import (
    ClarificationQuestion,
    FindingStatus,
    Milestone,
    PolicyCheck,
    RouteStatus,
    SourceReference,
    StrictModel,
    TenderLabRequest,
    TraceStep,
)
from app.tender_lab.workflow import run_tender_lab


class ChangeSimulationRequest(StrictModel):
    tender: TenderLabRequest
    source_label: str = Field(min_length=2, max_length=200)
    amendment_text: str = Field(min_length=20, max_length=60_000)


class DecisionSnapshot(StrictModel):
    mandatory_gap_count: int = Field(ge=0)
    review_item_count: int = Field(ge=0)
    next_milestone: str | None
    direct_route_status: RouteStatus


class ControlChange(StrictModel):
    id: str
    title: str
    change_type: Literal["NEW_CONTROL", "RESTATED_CONTROL"]
    before_status: FindingStatus | None
    simulated_status: FindingStatus
    source: SourceReference
    check: PolicyCheck


class MilestoneChange(StrictModel):
    id: str
    label: str
    change_type: Literal["ADDED", "REPLACED", "RESTATED"]
    previous_starts_at: str | None
    simulated_starts_at: str
    confidence: Literal["HIGH", "REVIEW"]
    source: SourceReference


class CommercialRecheck(StrictModel):
    status: Literal["REVALIDATE", "NO_AUTOMATIC_CHANGE"]
    triggers: list[str]
    impact: str
    source: SourceReference


class ChangeSimulationResponse(StrictModel):
    source_label: str
    before: DecisionSnapshot
    simulated_after: DecisionSnapshot
    control_changes: list[ControlChange]
    milestone_changes: list[MilestoneChange]
    clarification_questions: list[ClarificationQuestion]
    commercial_recheck: CommercialRecheck
    invalidated_outputs: list[str]
    recovery_actions: list[str]
    trace: list[TraceStep]
    boundaries: list[str]


COMMERCIAL_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "delivery scope",
        (
            r"\b(?:additional|new|revised|expanded|reduced)\s+(?:delivery\s+)?scope\b",
            r"\b(?:scope|deliverables?)\s+(?:increases?|decreases?|expands?|reduces?|changes?)\b",
            r"\b(?:adds?|added|removes?|removed)\s+(?!no\b)(?:up\s+to\s+)?(?:\w+[\s-]+){0,4}"
            r"(?:locations?|sites?|deliverables?|modules?|services?)\b",
        ),
    ),
    (
        "demand volume",
        (
            r"\b(?:(?:expected|estimated|baseline|peak|revised)\s+)?"
            r"(?:(?:event|transaction|user|device|location|site)\s+)?(?:volume|capacity)\b",
            r"\b(?:users?|devices?|locations?|sites?)\s+"
            r"(?:increases?|decreases?|changes?|expands?|reduces?)\b",
        ),
    ),
    (
        "service level",
        (r"\bservice[\s-]+level\b", r"\bsla\b", r"\bresponse\s+time\b", r"\bresolution\s+time\b", r"\bavailability\b"),
    ),
    (
        "delivery period",
        (
            r"\b(?:contract|service|delivery|implementation)\s+(?:term|period|duration)\b",
            r"\b(?:extend|extended|shorten|shortened|increase|increased|decrease|decreased)"
            r"\b.{0,24}\b(?:months?|years?|term|period|duration)\b",
        ),
    ),
    ("staffing", (r"\bpersonnel\b", r"\bstaff(?:ing)?\b", r"\bengineers?\b", r"\bheadcount\b", r"\bmanpower\b")),
    (
        "partner route",
        (r"\bsubcontract(?:or|ing)?s?\b", r"\bconsortium\b", r"\bjoint\s+venture\b", r"\bprime\s+contractor\b"),
    ),
)

MILESTONE_IDENTITIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "mobilisation",
        (
            "mobilisation",
            "mobilization",
            "commencement",
            "kick-off",
            "kickoff",
            "go-live",
            "project start",
            "contract start",
            "service start",
        ),
    ),
    ("warranty", ("warranty", "defect liability")),
    ("payment", ("payment", "invoice")),
    ("delivery", ("delivery date", "deliverable")),
    ("contract-end", ("contract end", "expiry", "expiration", "end date")),
    ("award", ("award date", "letter of award")),
)

REPLACEMENT_WORDING = re.compile(
    r"\b(?:revised|updated|extended|postponed|rescheduled|changed|replaces?|supersedes?)\b",
    re.I,
)


def _source(request: ChangeSimulationRequest) -> SourceReference:
    cleaned = re.sub(r"\s+", " ", request.amendment_text).strip()
    page_match = re.search(r"\[Page\s+(\d+)\]", request.amendment_text, re.I)
    return SourceReference(
        source_label=request.source_label,
        location=f"Page {page_match.group(1)}" if page_match else "Supplied amendment text",
        excerpt=cleaned[:260],
    )


def _snapshot(
    *,
    payload: TenderLabRequest,
    checks: list[PolicyCheck],
    milestones: list[Milestone],
    extra_review_ids: set[str] | None = None,
) -> DecisionSnapshot:
    gap_count = len(
        {
            item.id
            for item in checks
            if item.status == "GAP" and item.risk == "MANDATORY"
        }
    )
    review_ids = {
        item.id
        for item in checks
        if item.status == "REVIEW" or (item.status == "GAP" and item.risk == "REVIEW")
    }
    review_ids.update(extra_review_ids or set())
    route_status: RouteStatus
    if (
        payload.contract_value_sgd is not None
        and payload.company.max_delivery_value_sgd is not None
        and payload.contract_value_sgd > payload.company.max_delivery_value_sgd
    ):
        route_status = "BLOCKED"
    elif gap_count:
        route_status = "RECOVERABLE"
    elif not payload.proposal_text.strip() or payload.company.max_delivery_value_sgd is None:
        route_status = "UNCERTAIN"
    else:
        route_status = "FEASIBLE"
    ordered = sorted(milestones, key=lambda item: item.starts_at)
    return DecisionSnapshot(
        mandatory_gap_count=gap_count,
        review_item_count=len(review_ids),
        next_milestone=ordered[0].starts_at if ordered else None,
        direct_route_status=route_status,
    )


def _control_changes(
    baseline: list[PolicyCheck], amendment: list[PolicyCheck]
) -> list[ControlChange]:
    baseline_by_id = {item.id: item for item in baseline}
    changes: list[ControlChange] = []
    for check in amendment:
        if check.id == "CTRL-SOURCE-REVIEW":
            continue
        previous = baseline_by_id.get(check.id)
        changes.append(
            ControlChange(
                id=check.id,
                title=check.title,
                change_type="NEW_CONTROL" if previous is None else "RESTATED_CONTROL",
                before_status=previous.status if previous else None,
                simulated_status=(
                    "REVIEW"
                    if previous is not None and check.status == "SUPPORTED"
                    else check.status
                ),
                source=check.tender_source,
                check=check,
            )
        )
    return changes


def _merge_checks(
    baseline: list[PolicyCheck], control_changes: list[ControlChange]
) -> list[PolicyCheck]:
    merged = {item.id: item for item in baseline}
    for change in control_changes:
        merged[change.id] = change.check
    return list(merged.values())


def _milestone_identity(milestone: Milestone) -> str | None:
    lowered = milestone.tender_source.excerpt.casefold()
    if milestone.label == "Clarification deadline":
        return "clarification"
    if milestone.label == "Tender submission":
        return "submission"
    if milestone.label == "Tender briefing":
        return "site-visit" if "site visit" in lowered else "briefing"
    if milestone.label == "Presentation or evaluation":
        for topic in ("presentation", "demo", "interview"):
            if topic in lowered:
                return f"evaluation:{topic}"
        return "evaluation"
    if milestone.label == "Financial instrument deadline":
        for topic in ("bond", "guarantee", "deposit"):
            if topic in lowered:
                return f"financial-instrument:{topic}"
        return "financial-instrument"
    for identity, terms in MILESTONE_IDENTITIES:
        if any(term in lowered for term in terms):
            return f"generic:{identity}"
    return None


def _matching_baseline_milestone(
    milestone: Milestone,
    baseline: list[Milestone],
    used_indexes: set[int],
) -> tuple[int, Milestone] | None:
    identity = _milestone_identity(milestone)
    candidates = [
        (index, item)
        for index, item in enumerate(baseline)
        if index not in used_indexes
        and identity is not None
        and _milestone_identity(item) == identity
    ]
    if identity is not None and identity.startswith("generic:"):
        exact_matches = [
            candidate
            for candidate in candidates
            if candidate[1].starts_at == milestone.starts_at
        ]
        if exact_matches:
            return exact_matches[0]
        if not REPLACEMENT_WORDING.search(milestone.tender_source.excerpt):
            candidates = []
    if not candidates and milestone.label != "Tender milestone" and REPLACEMENT_WORDING.search(
        milestone.tender_source.excerpt
    ):
        candidates = [
            (index, item)
            for index, item in enumerate(baseline)
            if index not in used_indexes and item.label == milestone.label
        ]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda candidate: (
            candidate[1].starts_at == milestone.starts_at,
            candidate[1].starts_at,
        ),
    )


def _milestone_changes(
    baseline: list[Milestone], amendment: list[Milestone]
) -> list[MilestoneChange]:
    changes: list[MilestoneChange] = []
    used_indexes: set[int] = set()
    for milestone in amendment:
        matched = _matching_baseline_milestone(milestone, baseline, used_indexes)
        previous = matched[1] if matched else None
        if matched:
            used_indexes.add(matched[0])
        change_type: Literal["ADDED", "REPLACED", "RESTATED"]
        if previous is None:
            change_type = "ADDED"
        elif previous.starts_at == milestone.starts_at:
            change_type = "RESTATED"
        else:
            change_type = "REPLACED"
        changes.append(
            MilestoneChange(
                id=milestone.id,
                label=milestone.label,
                change_type=change_type,
                previous_starts_at=previous.starts_at if previous else None,
                simulated_starts_at=milestone.starts_at,
                confidence=milestone.confidence,
                source=milestone.tender_source,
            )
        )
    return changes


def _merge_milestones(
    baseline: list[Milestone],
    amendment: list[Milestone],
    changes: list[MilestoneChange],
) -> list[Milestone]:
    merged = list(baseline)
    for item, change in zip(amendment, changes, strict=True):
        replaced = False
        if change.change_type != "ADDED" and change.previous_starts_at is not None:
            identity = _milestone_identity(item)
            for index, current in enumerate(merged):
                if (
                    current.starts_at == change.previous_starts_at
                    and identity is not None
                    and _milestone_identity(current) == identity
                ):
                    merged[index] = item
                    replaced = True
                    break
        if not replaced:
            merged.append(item)
    return sorted(merged, key=lambda item: item.starts_at)


def _positive_commercial_signal(sentence: str, pattern: str) -> bool:
    for match in re.finditer(pattern, sentence, re.I):
        prefix = sentence[max(0, match.start() - 48) : match.start()]
        suffix = sentence[match.end() : min(len(sentence), match.end() + 48)]
        if re.search(r"\bno\s+(?:(?:material|additional|new|revised)\s+){0,2}$", prefix):
            continue
        if re.search(r"\bwithout\s+(?:any\s+)?$", prefix):
            continue
        if re.match(r"\s+(?:remain|remains|is|are|stays?)\s+unchanged\b", suffix):
            continue
        if re.match(
            r"\s+(?:(?:is|are|was|were|has|have)\s+not\s+"
            r"(?:materially\s+)?(?:changed|affected|altered))\b",
            suffix,
        ):
            continue
        if re.search(r"\bno\s+(?:material\s+)?changes?\s+(?:to|in)\b", sentence):
            continue
        if re.search(
            r"\b(?:does|do|will)\s+not\s+(?:materially\s+)?(?:change|affect|alter)\b",
            sentence,
        ):
            continue
        return True
    return False


def _commercial_recheck(request: ChangeSimulationRequest) -> CommercialRecheck:
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?;])\s+|[\r\n]+", request.amendment_text)
        if sentence.strip()
    ]
    triggers = [
        label
        for label, patterns in COMMERCIAL_PATTERNS
        if any(
            _positive_commercial_signal(sentence, pattern)
            for sentence in sentences
            for pattern in patterns
        )
    ]
    if triggers:
        impact_parts = [
            "Commercial change signals were detected. Revalidate the affected delivery inputs before reusing downstream outputs."
        ]
        if request.tender.pricing is not None:
            impact_parts.append("The current pricing scenarios should be rerun with reviewed cost and capacity inputs.")
            if request.tender.pricing.comparable_awards_sgd:
                impact_parts.append("Reconfirm that the attached award values remain scope-comparable.")
        else:
            impact_parts.append("No baseline pricing output was supplied, so this rehearsal does not claim that one was invalidated.")
        if "partner route" in triggers:
            impact_parts.append(
                "Rerun the Tender Lab participation-route simulation; no partner availability or partner package was assessed."
            )
        impact = " ".join(impact_parts)
    else:
        impact = (
            "No configured positive commercial change signal was detected. Existing figures are not automatically changed, "
            "and the amendment still requires human review."
        )
    return CommercialRecheck(
        status="REVALIDATE" if triggers else "NO_AUTOMATIC_CHANGE",
        triggers=triggers,
        impact=impact,
        source=_source(request),
    )


def _trace(
    control_changes: list[ControlChange],
    milestone_changes: list[MilestoneChange],
    clarifications: list[ClarificationQuestion],
    commercial: CommercialRecheck,
) -> list[TraceStep]:
    return [
        TraceStep(
            id="CHANGE-INGEST",
            label="Read the supplied amendment",
            status="COMPLETED",
            detail="Kept the amendment separate from the baseline tender and retained its source label.",
        ),
        TraceStep(
            id="CHANGE-CONTROLS",
            label="Re-run control coverage",
            status="COMPLETED" if control_changes else "SKIPPED",
            detail=f"Found {len(control_changes)} new or restated control signal(s).",
        ),
        TraceStep(
            id="CHANGE-MILESTONES",
            label="Rebuild dated milestones",
            status="COMPLETED" if milestone_changes else "SKIPPED",
            detail=f"Found {len(milestone_changes)} added, replaced or restated milestone(s).",
        ),
        TraceStep(
            id="CHANGE-COMMERCIAL",
            label="Invalidate affected assumptions",
            status="COMPLETED" if commercial.status == "REVALIDATE" else "SKIPPED",
            detail=commercial.impact,
        ),
        TraceStep(
            id="CHANGE-CLARIFY",
            label="Draft clarification questions",
            status="COMPLETED" if clarifications else "SKIPPED",
            detail=f"Prepared {len(clarifications)} amendment-linked clarification draft(s).",
        ),
        TraceStep(
            id="CHANGE-REPLAN",
            label="Rebuild the recovery plan",
            status="COMPLETED",
            detail="Ordered review actions without changing a bid record or making a commercial decision.",
        ),
    ]


def simulate_tender_change(request: ChangeSimulationRequest) -> ChangeSimulationResponse:
    baseline = run_tender_lab(request.tender)
    amendment_payload = request.tender.model_copy(
        update={
            "source_label": request.source_label,
            "source_type": "USER_SUPPLIED",
            "tender_text": request.amendment_text,
        }
    )
    amendment_checks = scan_policy_checks(amendment_payload)
    controls = _control_changes(baseline.policy_checks, amendment_checks)
    amendment_milestones = extract_milestones(amendment_payload)
    milestone_changes = _milestone_changes(baseline.milestones, amendment_milestones)
    merged_checks = _merge_checks(baseline.policy_checks, controls)
    merged_milestones = _merge_milestones(
        baseline.milestones,
        amendment_milestones,
        milestone_changes,
    )
    clarifications = draft_clarifications(amendment_payload)
    commercial = _commercial_recheck(request)
    restated_review_ids = {
        item.id for item in controls if item.simulated_status == "REVIEW"
    }

    invalidated_outputs: list[str] = []
    if controls:
        invalidated_outputs.append("Proposal coverage scan")
    if milestone_changes:
        invalidated_outputs.append("Milestone plan and calendar export")
    if commercial.status == "REVALIDATE":
        if baseline.pricing is not None:
            invalidated_outputs.append("Pricing scenarios built from the current cost and price inputs")
            if baseline.pricing.comparable_count:
                invalidated_outputs.append("Scope comparability of the attached award values")
    if clarifications:
        invalidated_outputs.append("Tender Lab clarification set")
    if any("partner route" == trigger for trigger in commercial.triggers):
        invalidated_outputs.append("Tender Lab participation-route simulation")

    recovery_actions: list[str] = []
    for item in controls:
        action = item.check.next_step
        recovery_actions.append(f"{item.title}: {action}")
    for item in milestone_changes:
        recovery_actions.append(
            f"{item.label}: confirm {item.simulated_starts_at} against the signed amendment and refresh dependent task dates."
        )
    for item in clarifications:
        recovery_actions.append(f"{item.issue}: review and, if approved, send the drafted clarification before the deadline.")
    if commercial.status == "REVALIDATE":
        if baseline.pricing is not None:
            recovery_actions.append("Update affected cost and capacity inputs, then rerun the pricing simulation.")
        else:
            recovery_actions.append(
                "Assess whether the change introduces new cost or capacity inputs; no baseline pricing output was supplied."
            )
        if "partner route" in commercial.triggers:
            recovery_actions.append(
                "Rerun the participation-route simulation; partner availability and outreach remain outside this rehearsal."
            )
    recovery_actions.append("A bid owner reviews the source, deltas and evidence before accepting any revised decision state.")

    return ChangeSimulationResponse(
        source_label=request.source_label,
        before=_snapshot(
            payload=request.tender,
            checks=baseline.policy_checks,
            milestones=baseline.milestones,
        ),
        simulated_after=_snapshot(
            payload=request.tender,
            checks=merged_checks,
            milestones=merged_milestones,
            extra_review_ids=restated_review_ids,
        ),
        control_changes=controls,
        milestone_changes=milestone_changes,
        clarification_questions=clarifications,
        commercial_recheck=commercial,
        invalidated_outputs=invalidated_outputs,
        recovery_actions=recovery_actions,
        trace=_trace(controls, milestone_changes, clarifications, commercial),
        boundaries=[
            "This is a stateless rehearsal. The baseline tender, proposal and operational bid record are unchanged.",
            "The amendment is treated as new or restated wording; deletions and legal supersession require a human comparison with the signed documents.",
            "Keyword coverage and generated scaffolds are review aids, not compliance certification.",
            "Pricing inputs are never changed automatically and no bid, partner or submission decision is made.",
        ],
    )
