from dataclasses import dataclass
from datetime import datetime

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import AssessmentStatus, AvailabilityStatus, VerificationStatus
from app.models import Employee, Evidence, Requirement, Tender
from app.rules import RuleEvaluationInput, RuleKind, evaluate_rule


@dataclass(frozen=True)
class AssessmentResult:
    status: AssessmentStatus
    evidence_ids: list[str]
    reason: str
    usable_employee_ids: list[str]
    recovery_candidate_ids: list[str]


def assess_requirement(session: Session, requirement: Requirement) -> AssessmentResult:
    kind = requirement.rule_config.get("kind")
    if kind == "certified_staff":
        tender = session.get(Tender, requirement.tender_id)
        return _assess_certified_staff(session, requirement, tender)
    if kind in RuleKind:
        return _assess_procurement_rule(requirement)
    return AssessmentResult(
        status=AssessmentStatus.UNCERTAIN,
        evidence_ids=[],
        reason="No deterministic verification rule is configured; human interpretation is required.",
        usable_employee_ids=[],
        recovery_candidate_ids=[],
    )


def _assess_procurement_rule(requirement: Requirement) -> AssessmentResult:
    config = dict(requirement.rule_config)
    facts = config.pop("facts", None)
    evaluation_as_of = config.pop("evaluation_as_of", None)
    if not isinstance(facts, dict) or not isinstance(evaluation_as_of, str):
        return AssessmentResult(
            status=AssessmentStatus.UNCERTAIN,
            evidence_ids=[],
            reason=(
                "The generic rule requires typed facts and an explicit evaluation_as_of timestamp; "
                "no ambient time or missing fact was guessed."
            ),
            usable_employee_ids=[],
            recovery_candidate_ids=[],
        )
    try:
        evaluation = RuleEvaluationInput.model_validate(
            {"rule": config, "facts": {"kind": config["kind"], **facts}}
        )
        assessed_at = datetime.fromisoformat(evaluation_as_of)
        result = evaluate_rule(evaluation, assessed_at)
    except (KeyError, TypeError, ValueError, ValidationError) as exc:
        return AssessmentResult(
            status=AssessmentStatus.UNCERTAIN,
            evidence_ids=[],
            reason=f"The generic deterministic rule configuration is invalid: {exc}",
            usable_employee_ids=[],
            recovery_candidate_ids=[],
        )
    return AssessmentResult(
        status=AssessmentStatus(result.status),
        evidence_ids=[],
        reason=result.reason,
        usable_employee_ids=[],
        recovery_candidate_ids=[],
    )


def _assess_certified_staff(
    session: Session, requirement: Requirement, tender: Tender
) -> AssessmentResult:
    certification = str(requirement.rule_config["certification"]).upper()
    minimum_count = int(requirement.rule_config["minimum_count"])
    employees = session.scalars(
        select(Employee).where(Employee.company_id == tender.company_id)
    ).all()
    evidence = session.scalars(
        select(Evidence).where(Evidence.company_id == tender.company_id)
    ).all()

    by_employee: dict[str, list[Evidence]] = {}
    for item in evidence:
        if item.subject_type == "EMPLOYEE":
            by_employee.setdefault(item.subject_id, []).append(item)

    usable: list[str] = []
    candidates: list[str] = []
    used_evidence: list[str] = []
    for employee in employees:
        employee_evidence = by_employee.get(employee.id, [])
        valid_certificates = [
            item
            for item in employee_evidence
            if item.type == "EMPLOYEE_CERTIFICATION"
            and str(item.details.get("certification", "")).upper() == certification
            and item.verification_status == VerificationStatus.VERIFIED.value
            and (item.valid_until is None or item.valid_until >= tender.closing_at)
        ]
        if not valid_certificates:
            continue
        current_cvs = [
            item
            for item in employee_evidence
            if item.type == "CV" and item.verification_status == VerificationStatus.VERIFIED.value
        ]
        if current_cvs and employee.availability_status == AvailabilityStatus.AVAILABLE.value:
            usable.append(employee.id)
            used_evidence.extend([valid_certificates[0].id, current_cvs[0].id])
        else:
            candidates.append(employee.id)

    if len(usable) >= minimum_count:
        status = AssessmentStatus.SATISFIED
        reason = (
            f"{len(usable)} available employees have valid {certification} certificates "
            "and current CV evidence."
        )
    elif len(usable) + len(candidates) >= minimum_count:
        status = AssessmentStatus.PARTIAL
        reason = (
            f"The tender now requires {minimum_count} valid {certification}-certified engineers. "
            f"Only {len(usable)} currently have complete verified evidence; "
            f"{len(candidates)} recovery candidate has evidence gaps."
        )
    else:
        status = AssessmentStatus.UNMET
        reason = (
            f"Only {len(usable)} eligible {certification}-certified engineers are proven and no "
            "sufficient recovery candidate exists."
        )

    return AssessmentResult(status, used_evidence, reason, usable, candidates)
