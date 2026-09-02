from collections.abc import Iterable
from datetime import datetime, timedelta

from app.enums import AssessmentStatus, OperationalStatus
from app.rules.identity import document_name_key, qualification_code_key
from app.rules.schemas import (
    EventAttendanceFacts,
    EventAttendanceRule,
    ParticipationRestrictionFacts,
    ParticipationRestrictionRule,
    ProcessingWindowFacts,
    ProcessingWindowRule,
    QualificationFacts,
    QualificationRule,
    RequiredDocumentFacts,
    RequiredDocumentRule,
    RequirementEvaluationResult,
    RuleEvaluationInput,
    RuleEvaluationResult,
    RuleKind,
    SourceFreshnessFacts,
    SourceFreshnessRule,
)


def _result(
    kind: RuleKind,
    status: AssessmentStatus,
    recoverable: bool | None,
    reason: str,
    *,
    satisfied: list[str] | None = None,
    unresolved: list[str] | None = None,
    projected_completion_at: datetime | None = None,
) -> RuleEvaluationResult:
    return RuleEvaluationResult(
        rule_kind=kind,
        status=status,
        recoverable=recoverable,
        reason=reason,
        satisfied_items=satisfied or [],
        unresolved_items=unresolved or [],
        projected_completion_at=projected_completion_at,
    )


def _optional_rule(kind: RuleKind) -> RuleEvaluationResult:
    return _result(
        kind,
        AssessmentStatus.SATISFIED,
        False,
        "The source explicitly marks this rule as non-compulsory, so it is not an operational gate.",
    )


def evaluate_event_attendance(
    rule: EventAttendanceRule, facts: EventAttendanceFacts
) -> RuleEvaluationResult:
    kind = RuleKind.EVENT_ATTENDANCE
    if rule.compulsory is None:
        return _result(
            kind,
            AssessmentStatus.UNCERTAIN,
            None,
            "The source does not establish whether attendance is compulsory.",
            unresolved=[rule.event_name],
        )
    if not rule.compulsory:
        return _optional_rule(kind)
    if facts.attended is True:
        return _result(
            kind,
            AssessmentStatus.SATISFIED,
            False,
            "Compulsory attendance is evidenced.",
            satisfied=[rule.event_name],
        )
    if facts.attended is None:
        return _result(
            kind,
            AssessmentStatus.UNCERTAIN,
            None,
            "Attendance evidence is unavailable.",
            unresolved=[rule.event_name],
        )
    recovery_signals = (facts.attendance_opportunity_open, facts.makeup_available)
    if any(signal is True for signal in recovery_signals):
        recoverable = True
    elif all(signal is False for signal in recovery_signals):
        recoverable = False
    else:
        recoverable = None
    return _result(
        kind,
        AssessmentStatus.UNMET,
        recoverable,
        "The compulsory event has not been attended.",
        unresolved=[rule.event_name],
    )


def evaluate_qualification(
    rule: QualificationRule, facts: QualificationFacts
) -> RuleEvaluationResult:
    kind = RuleKind.QUALIFICATION
    if rule.compulsory is None:
        return _result(
            kind,
            AssessmentStatus.UNCERTAIN,
            None,
            "The available source does not establish whether this qualification is mandatory.",
            unresolved=[option.code for option in rule.options],
        )
    if not rule.compulsory:
        return _optional_rule(kind)

    evidence_by_code = {qualification_code_key(item.code): item for item in facts.evidence}
    option_states: list[bool | None] = []
    for option in rule.options:
        evidence = evidence_by_code.get(qualification_code_key(option.code))
        if evidence is None or evidence.verified is None or evidence.meets_minimum is None:
            option_states.append(None)
        else:
            option_states.append(evidence.verified and evidence.meets_minimum)

    satisfied = [
        option.code for option, state in zip(rule.options, option_states, strict=True) if state
    ]
    if (rule.match == "ANY" and satisfied) or (
        rule.match == "ALL" and option_states and all(state is True for state in option_states)
    ):
        return _result(
            kind,
            AssessmentStatus.SATISFIED,
            False,
            "Verified qualification evidence satisfies the configured option rule.",
            satisfied=satisfied,
        )
    if any(state is None for state in option_states):
        return _result(
            kind,
            AssessmentStatus.UNCERTAIN,
            None,
            "Qualification evidence is missing or cannot be deterministically compared.",
            satisfied=satisfied,
            unresolved=[
                option.code
                for option, state in zip(rule.options, option_states, strict=True)
                if state is not True
            ],
        )
    return _result(
        kind,
        AssessmentStatus.UNMET,
        facts.can_obtain_before_deadline,
        "No verified qualification option satisfies the mandatory rule.",
        unresolved=[option.code for option in rule.options],
    )


def evaluate_required_document(
    rule: RequiredDocumentRule, facts: RequiredDocumentFacts
) -> RuleEvaluationResult:
    kind = RuleKind.REQUIRED_DOCUMENT
    if rule.compulsory is None:
        return _result(
            kind,
            AssessmentStatus.UNCERTAIN,
            None,
            "The source does not establish whether these documents are compulsory.",
            unresolved=rule.documents,
        )
    if not rule.compulsory:
        return _optional_rule(kind)

    fact_by_name = {document_name_key(item.name): item for item in facts.documents}
    submitted: list[str] = []
    unresolved: list[str] = []
    unknown = False
    recoverability: list[bool | None] = []
    for document in rule.documents:
        fact = fact_by_name.get(document_name_key(document))
        if fact is not None and fact.state == "SUBMITTED":
            submitted.append(document)
            continue
        unresolved.append(document)
        if fact is None or fact.state == "UNKNOWN":
            unknown = True
            recoverability.append(None)
        elif facts.submission_open is False:
            recoverability.append(False)
        elif facts.submission_open is None:
            recoverability.append(None)
        elif fact.state == "READY":
            recoverability.append(True)
        else:
            recoverability.append(fact.can_complete_before_deadline)

    satisfied_rule = (
        bool(submitted) if rule.match == "ANY" else len(submitted) == len(rule.documents)
    )
    if satisfied_rule:
        return _result(
            kind,
            AssessmentStatus.SATISFIED,
            False,
            "The required document submission rule is satisfied.",
            satisfied=submitted,
        )
    if unknown and not submitted:
        return _result(
            kind,
            AssessmentStatus.UNCERTAIN,
            None,
            "Document submission state is unavailable.",
            unresolved=unresolved,
        )
    recoverable = (
        True
        if recoverability and all(value is True for value in recoverability)
        else False
        if any(value is False for value in recoverability)
        else None
    )
    status = AssessmentStatus.PARTIAL if submitted else AssessmentStatus.UNMET
    return _result(
        kind,
        status,
        recoverable,
        "Only part of the required document set is submitted."
        if submitted
        else "No required document is submitted.",
        satisfied=submitted,
        unresolved=unresolved,
    )


def evaluate_processing_window(
    rule: ProcessingWindowRule,
    facts: ProcessingWindowFacts,
    evaluation_as_of: datetime,
) -> RuleEvaluationResult:
    kind = RuleKind.PROCESSING_WINDOW
    if rule.compulsory is None:
        return _result(
            kind,
            AssessmentStatus.UNCERTAIN,
            None,
            "The source does not establish whether the timed action is compulsory.",
            unresolved=[rule.action],
        )
    if not rule.compulsory:
        return _optional_rule(kind)
    if facts.completed is True:
        return _result(
            kind,
            AssessmentStatus.SATISFIED,
            False,
            "The mandatory timed action is complete.",
            satisfied=[rule.action],
        )
    if facts.completed is None:
        return _result(
            kind,
            AssessmentStatus.UNCERTAIN,
            None,
            "Completion state for the timed action is unavailable.",
            unresolved=[rule.action],
        )
    if facts.can_complete is False:
        return _result(
            kind,
            AssessmentStatus.UNMET,
            False,
            "The action is incomplete and the supplied facts state it cannot be completed.",
            unresolved=[rule.action],
        )
    if facts.can_complete is None:
        return _result(
            kind,
            AssessmentStatus.UNMET,
            None,
            "The action is incomplete and recoverability cannot be established.",
            unresolved=[rule.action],
        )

    deadline = rule.deadline or facts.governing_deadline
    if deadline is None:
        return _result(
            kind,
            AssessmentStatus.UNCERTAIN,
            None,
            "The processing duration is known, but no authoritative governing deadline is "
            "available for comparison.",
            unresolved=[rule.action],
        )

    start_at = max(evaluation_as_of, facts.earliest_start_at or evaluation_as_of)
    duration = max(
        rule.minimum_processing_hours,
        facts.estimated_duration_hours or 0,
    )
    projected_completion = start_at + timedelta(hours=duration)
    recoverable = projected_completion <= deadline
    return _result(
        kind,
        AssessmentStatus.UNMET,
        recoverable,
        "The action is incomplete; recoverability is determined by projected completion versus "
        "the governing deadline.",
        unresolved=[rule.action],
        projected_completion_at=projected_completion,
    )


def evaluate_participation_restriction(
    rule: ParticipationRestrictionRule, facts: ParticipationRestrictionFacts
) -> RuleEvaluationResult:
    kind = RuleKind.PARTICIPATION_RESTRICTION
    if rule.compulsory is None:
        return _result(
            kind,
            AssessmentStatus.UNCERTAIN,
            None,
            "The source does not establish whether the participation restriction is mandatory.",
            unresolved=[rule.restriction],
        )
    if not rule.compulsory:
        return _optional_rule(kind)
    if facts.eligible is True:
        return _result(
            kind,
            AssessmentStatus.SATISFIED,
            False,
            "The bidder satisfies the participation restriction.",
            satisfied=[rule.restriction],
        )
    if facts.eligible is None:
        return _result(
            kind,
            AssessmentStatus.UNCERTAIN,
            None,
            "Eligibility under the participation restriction is unknown.",
            unresolved=[rule.restriction],
        )
    return _result(
        kind,
        AssessmentStatus.UNMET,
        facts.can_become_eligible_before_deadline,
        "The bidder does not satisfy the mandatory participation restriction.",
        unresolved=[rule.restriction],
    )


def evaluate_source_freshness(
    rule: SourceFreshnessRule, facts: SourceFreshnessFacts
) -> RuleEvaluationResult:
    kind = RuleKind.SOURCE_FRESHNESS
    if not rule.latest_version_required:
        return _optional_rule(kind)
    if facts.change_notice_present is True and facts.change_content_available is not True:
        return _result(
            kind,
            AssessmentStatus.UNCERTAIN,
            None,
            "A change notice exists but its authoritative contents are unavailable.",
            unresolved=[rule.source_name],
        )
    if facts.latest_version_ingested is True:
        return _result(
            kind,
            AssessmentStatus.SATISFIED,
            False,
            "The latest authoritative source version is ingested.",
            satisfied=[rule.source_name],
        )
    return _result(
        kind,
        AssessmentStatus.UNCERTAIN,
        None,
        "The requirement corpus cannot be proven current.",
        unresolved=[rule.source_name],
    )


def evaluate_rule(
    evaluation: RuleEvaluationInput, evaluation_as_of: datetime
) -> RuleEvaluationResult:
    rule = evaluation.rule
    facts = evaluation.facts
    if isinstance(rule, EventAttendanceRule) and isinstance(facts, EventAttendanceFacts):
        return evaluate_event_attendance(rule, facts)
    if isinstance(rule, QualificationRule) and isinstance(facts, QualificationFacts):
        return evaluate_qualification(rule, facts)
    if isinstance(rule, RequiredDocumentRule) and isinstance(facts, RequiredDocumentFacts):
        return evaluate_required_document(rule, facts)
    if isinstance(rule, ProcessingWindowRule) and isinstance(facts, ProcessingWindowFacts):
        return evaluate_processing_window(rule, facts, evaluation_as_of)
    if isinstance(rule, ParticipationRestrictionRule) and isinstance(
        facts, ParticipationRestrictionFacts
    ):
        return evaluate_participation_restriction(rule, facts)
    if isinstance(rule, SourceFreshnessRule) and isinstance(facts, SourceFreshnessFacts):
        return evaluate_source_freshness(rule, facts)
    raise TypeError(f"No deterministic evaluator for {rule.kind}")


def evaluate_requirement(
    evaluations: Iterable[RuleEvaluationInput], evaluation_as_of: datetime
) -> RequirementEvaluationResult:
    results = [evaluate_rule(item, evaluation_as_of) for item in evaluations]
    if not results:
        return RequirementEvaluationResult(
            requirement_status=AssessmentStatus.UNCERTAIN,
            operational_status=OperationalStatus.UNCERTAIN,
            reason="No supported deterministic rules were supplied.",
            rule_results=[],
        )

    statuses = {result.status for result in results}
    if AssessmentStatus.UNMET in statuses:
        requirement_status = AssessmentStatus.UNMET
    elif AssessmentStatus.UNCERTAIN in statuses:
        requirement_status = AssessmentStatus.UNCERTAIN
    elif AssessmentStatus.PARTIAL in statuses:
        requirement_status = AssessmentStatus.PARTIAL
    else:
        requirement_status = AssessmentStatus.SATISFIED

    gaps = [result for result in results if result.status != AssessmentStatus.SATISFIED]
    if not gaps:
        operational_status = OperationalStatus.FEASIBLE
        reason = "Every deterministic rule is satisfied."
    elif any(
        result.status in {AssessmentStatus.UNMET, AssessmentStatus.PARTIAL}
        and result.recoverable is False
        for result in gaps
    ):
        operational_status = OperationalStatus.BLOCKED
        reason = "At least one known mandatory gap is not recoverable before its deadline."
    elif any(
        result.status == AssessmentStatus.UNCERTAIN or result.recoverable is None
        for result in gaps
    ):
        operational_status = OperationalStatus.UNCERTAIN
        reason = "No known blocker takes precedence, but at least one material fact is uncertain."
    else:
        operational_status = OperationalStatus.RECOVERABLE
        reason = "Every known mandatory gap has a deterministic recovery path before its deadline."

    return RequirementEvaluationResult(
        requirement_status=requirement_status,
        operational_status=operational_status,
        reason=reason,
        rule_results=results,
    )
