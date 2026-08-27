import re
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import AssessmentStatus, GateType, OperationalStatus, TaskStatus, VerificationStatus
from app.models import Assessment, Evidence, Requirement, Task, Tender


def current_requirements(session: Session, tender_id: str) -> list[Requirement]:
    requirements = session.scalars(
        select(Requirement).where(Requirement.tender_id == tender_id)
    ).all()
    latest: dict[str, Requirement] = {}
    for requirement in requirements:
        if (
            requirement.stable_key not in latest
            or requirement.version > latest[requirement.stable_key].version
        ):
            latest[requirement.stable_key] = requirement

    def stable_key_order(item: Requirement) -> tuple[str, int, str]:
        match = re.fullmatch(r"([A-Za-z_-]*?)(\d+)", item.stable_key)
        if match:
            return (match.group(1), int(match.group(2)), item.stable_key)
        return (item.stable_key, 0, item.stable_key)

    return sorted(latest.values(), key=stable_key_order)


def latest_assessment(session: Session, requirement_id: str) -> Assessment | None:
    return session.scalar(
        select(Assessment)
        .where(Assessment.requirement_id == requirement_id)
        .order_by(Assessment.assessed_at.desc(), Assessment.id.desc())
    )


def critical_gate_trace(session: Session, tender_id: str) -> dict[str, Any]:
    mandatory = [
        requirement
        for requirement in current_requirements(session, tender_id)
        if requirement.gate_type == GateType.MANDATORY.value
    ]
    gates = []
    for requirement in mandatory:
        assessment = latest_assessment(session, requirement.id)
        gates.append(
            {
                "requirement_id": requirement.id,
                "stable_key": requirement.stable_key,
                "requirement_version": requirement.version,
                "assessment_id": assessment.id if assessment else None,
                "assessment_status": assessment.status if assessment else "UNCERTAIN",
                "verified": bool(
                    assessment and assessment.status == AssessmentStatus.SATISFIED.value
                ),
            }
        )
    verified = sum(gate["verified"] for gate in gates)
    return {
        "verified": verified,
        "total": len(mandatory),
        "gates": gates,
        "rule": "Count the current version of each MANDATORY requirement as verified only when its latest assessment is SATISFIED.",
    }


def critical_gate_summary(session: Session, tender_id: str) -> dict[str, int]:
    trace = critical_gate_trace(session, tender_id)
    return {"verified": trace["verified"], "total": trace["total"]}


def submission_coverage_trace(session: Session, tender: Tender) -> dict[str, Any]:
    weights = {
        GateType.MANDATORY.value: 3,
        GateType.SCORED.value: 1,
        GateType.INFORMATIONAL.value: 0,
    }
    contributions = {
        AssessmentStatus.SATISFIED.value: 1.0,
        AssessmentStatus.PARTIAL.value: 0.5,
        AssessmentStatus.UNMET.value: 0.0,
        AssessmentStatus.UNCERTAIN.value: 0.0,
        AssessmentStatus.SUPERSEDED.value: 0.0,
    }
    weighted_total = 0.0
    weighted_complete = 0.0
    for requirement in current_requirements(session, tender.id):
        weight = weights[requirement.gate_type]
        weighted_total += weight
        assessment = latest_assessment(session, requirement.id)
        if assessment:
            weighted_complete += weight * contributions[assessment.status]
    requirement_coverage = weighted_complete / weighted_total if weighted_total else 1.0

    evidence = session.scalars(
        select(Evidence).where(Evidence.company_id == tender.company_id)
    ).all()
    evidence_coverage = (
        sum(item.verification_status == VerificationStatus.VERIFIED.value for item in evidence)
        / len(evidence)
        if evidence
        else 0.0
    )
    tasks = session.scalars(select(Task).where(Task.tender_id == tender.id)).all()
    task_coverage = (
        sum(item.status == TaskStatus.DONE.value for item in tasks) / len(tasks) if tasks else 1.0
    )
    requirement_percent = 100 * requirement_coverage
    evidence_percent = 100 * evidence_coverage
    task_percent = 100 * task_coverage
    requirement_points = 0.50 * requirement_percent
    evidence_points = 0.30 * evidence_percent
    task_points = 0.20 * task_percent
    raw_percent = requirement_points + evidence_points + task_points

    return {
        "display_percent": round(raw_percent),
        "raw_percent": round(raw_percent, 4),
        "formula": "0.50 × Requirement Coverage + 0.30 × Evidence Coverage + 0.20 × Task Coverage",
        "rounding": "The raw weighted percentage is rounded to the nearest whole percentage point for display.",
        "components": {
            "requirements": {
                "label": "Requirement Coverage",
                "weight": 0.50,
                "percent": round(requirement_percent, 2),
                "weighted_points": round(requirement_points, 2),
                "completed_units": round(weighted_complete, 2),
                "total_units": round(weighted_total, 2),
                "unit_label": "weighted units",
                "rule": "MANDATORY=3 units, SCORED=1, INFORMATIONAL=0; SATISFIED=100%, PARTIAL=50%, all other assessment states=0%.",
            },
            "evidence": {
                "label": "Evidence Coverage",
                "weight": 0.30,
                "percent": round(evidence_percent, 2),
                "weighted_points": round(evidence_points, 2),
                "completed_units": sum(
                    item.verification_status == VerificationStatus.VERIFIED.value
                    for item in evidence
                ),
                "total_units": len(evidence),
                "unit_label": "records",
                "rule": "Verified Evidence Registry records divided by all company evidence records in the fixture.",
            },
            "tasks": {
                "label": "Task Coverage",
                "weight": 0.20,
                "percent": round(task_percent, 2),
                "weighted_points": round(task_points, 2),
                "completed_units": sum(item.status == TaskStatus.DONE.value for item in tasks),
                "total_units": len(tasks),
                "unit_label": "tasks",
                "rule": "DONE tender tasks divided by all tender tasks.",
            },
        },
        "warning": "Submission Coverage measures preparation completeness. It is not a compliance score and never overrides a mandatory gate.",
    }


def calculate_submission_coverage(session: Session, tender: Tender) -> int:
    return int(submission_coverage_trace(session, tender)["display_percent"])


def operational_feasibility_trace(session: Session, tender: Tender) -> dict[str, Any]:
    assessments: list[tuple[Requirement, Assessment | None]] = []
    for requirement in current_requirements(session, tender.id):
        if requirement.gate_type == GateType.MANDATORY.value:
            assessments.append((requirement, latest_assessment(session, requirement.id)))

    unresolved = [
        (requirement, assessment)
        for requirement, assessment in assessments
        if assessment is None or assessment.status != AssessmentStatus.SATISFIED.value
    ]
    if not unresolved:
        return {
            "status": OperationalStatus.FEASIBLE.value,
            "reason": "Every current mandatory requirement has a SATISFIED latest assessment.",
            "precedence": ["BLOCKED", "UNCERTAIN", "RECOVERABLE", "FEASIBLE"],
            "mandatory_total": len(assessments),
            "unresolved": [],
        }

    recovery_by_requirement: dict[str, list[Task]] = defaultdict(list)
    tasks = session.scalars(
        select(Task).where(Task.tender_id == tender.id, Task.recovery_path.is_(True))
    ).all()
    for task in tasks:
        if task.requirement_id:
            recovery_by_requirement[task.requirement_id].append(task)

    unresolved_trace = []
    for requirement, assessment in unresolved:
        recovery_tasks = recovery_by_requirement.get(requirement.id, [])
        viable = bool(recovery_tasks) and all(
            task.status != TaskStatus.BLOCKED.value
            and (task.latest_safe_at or task.due_at) < tender.closing_at
            for task in recovery_tasks
        )
        unresolved_trace.append(
            {
                "requirement_id": requirement.id,
                "stable_key": requirement.stable_key,
                "assessment_status": assessment.status if assessment else "UNCERTAIN",
                "recovery_task_ids": [task.id for task in recovery_tasks],
                "recovery_viable": viable,
            }
        )

    blocked = [
        item
        for item in unresolved_trace
        if item["assessment_status"]
        in {AssessmentStatus.PARTIAL.value, AssessmentStatus.UNMET.value}
        and not item["recovery_viable"]
    ]
    if blocked:
        return {
            "status": OperationalStatus.BLOCKED.value,
            "reason": "At least one mandatory gap has no complete recovery task set that can finish before tender closing.",
            "precedence": ["BLOCKED", "UNCERTAIN", "RECOVERABLE", "FEASIBLE"],
            "mandatory_total": len(assessments),
            "unresolved": unresolved_trace,
        }

    uncertain = [
        item
        for item in unresolved_trace
        if item["assessment_status"] == AssessmentStatus.UNCERTAIN.value
    ]
    if uncertain:
        return {
            "status": OperationalStatus.UNCERTAIN.value,
            "reason": "No known blocker exists, but at least one mandatory requirement lacks a reliable assessment.",
            "precedence": ["BLOCKED", "UNCERTAIN", "RECOVERABLE", "FEASIBLE"],
            "mandatory_total": len(assessments),
            "unresolved": unresolved_trace,
        }

    return {
        "status": OperationalStatus.RECOVERABLE.value,
        "reason": "Every current mandatory gap has a complete, non-blocked recovery task set scheduled before tender closing.",
        "precedence": ["BLOCKED", "UNCERTAIN", "RECOVERABLE", "FEASIBLE"],
        "mandatory_total": len(assessments),
        "unresolved": unresolved_trace,
    }


def derive_operational_status(session: Session, tender: Tender) -> OperationalStatus:
    return OperationalStatus(operational_feasibility_trace(session, tender)["status"])
