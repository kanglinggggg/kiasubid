from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.enums import TaskStatus
from app.models import (
    ActivityEvent,
    ChangeEvent,
    Employee,
    Evidence,
    HumanApproval,
    Requirement,
    Task,
    TaskDependency,
    Tender,
)
from app.portfolio.demo import build_demo_portfolio_impact
from app.services.assessment import assess_requirement
from app.services.deadline import deadline_risk_trace
from app.services.metrics import (
    critical_gate_trace,
    current_requirements,
    latest_assessment,
    operational_feasibility_trace,
    submission_coverage_trace,
)


def _serialize_evidence(evidence: Evidence, employees: dict[str, Employee]) -> dict:
    employee = employees.get(evidence.subject_id)
    return {
        "id": evidence.id,
        "title": evidence.title,
        "type": evidence.type,
        "status": evidence.verification_status,
        "subject_name": employee.name if employee else None,
        "valid_until": evidence.valid_until,
    }


def serialize_bid(session: Session, tender_id: str) -> dict:
    tender = session.get(Tender, tender_id)
    if tender is None:
        raise LookupError(f"Unknown bid: {tender_id}")

    employees = {
        employee.id: employee
        for employee in session.scalars(
            select(Employee).where(Employee.company_id == tender.company_id)
        ).all()
    }
    all_evidence = session.scalars(
        select(Evidence).where(Evidence.company_id == tender.company_id)
    ).all()
    evidence_by_id = {item.id: item for item in all_evidence}
    evidence_by_subject: dict[str, list[Evidence]] = defaultdict(list)
    for item in all_evidence:
        evidence_by_subject[item.subject_id].append(item)

    all_requirements = session.scalars(
        select(Requirement).where(Requirement.tender_id == tender.id)
    ).all()
    history_by_key: dict[str, list[Requirement]] = defaultdict(list)
    for requirement in all_requirements:
        history_by_key[requirement.stable_key].append(requirement)

    requirement_rows = []
    for requirement in current_requirements(session, tender.id):
        assessment = latest_assessment(session, requirement.id)
        linked = [
            evidence_by_id[evidence_id]
            for evidence_id in (assessment.evidence_ids if assessment else [])
            if evidence_id in evidence_by_id
        ]
        verified_people = {item.subject_id for item in linked if item.subject_type == "EMPLOYEE"}
        history = []
        for version in sorted(
            history_by_key[requirement.stable_key], key=lambda item: item.version, reverse=True
        ):
            version_assessment = latest_assessment(session, version.id)
            history.append(
                {
                    "id": version.id,
                    "version": version.version,
                    "text": version.text,
                    "assessment": version_assessment.status if version_assessment else "UNCERTAIN",
                    "reason": version_assessment.reason_summary
                    if version_assessment
                    else "Not assessed.",
                    "assessed_at": version_assessment.assessed_at if version_assessment else None,
                }
            )
        requirement_rows.append(
            {
                "id": requirement.id,
                "stable_key": requirement.stable_key,
                "version": requirement.version,
                "text": requirement.text,
                "requirement_type": requirement.requirement_type,
                "gate_type": requirement.gate_type,
                "assessment": assessment.status if assessment else "UNCERTAIN",
                "assessment_reason": assessment.reason_summary if assessment else "Not assessed.",
                "assessment_method": assessment.assessment_method if assessment else None,
                "assessed_at": assessment.assessed_at if assessment else None,
                "evidence_count": len(verified_people) if verified_people else len(linked),
                "evidence": [_serialize_evidence(item, employees) for item in linked],
                "source": {
                    "document": requirement.source_document.filename,
                    "page": requirement.source_page,
                    "section": requirement.source_section,
                    "snippet": requirement.source_snippet,
                },
                "history": history,
            }
        )

    tasks = session.scalars(
        select(Task).where(Task.tender_id == tender.id).order_by(Task.due_at)
    ).all()
    dependencies: dict[str, list[str]] = defaultdict(list)
    for dependency in session.scalars(select(TaskDependency)).all():
        dependencies[dependency.task_id].append(dependency.depends_on_task_id)
    task_rows = [
        {
            "id": task.id,
            "requirement_id": task.requirement_id,
            "title": task.title,
            "description": task.description,
            "owner": task.owner,
            "status": task.status,
            "priority": task.priority,
            "due_at": task.due_at,
            "latest_safe_at": task.latest_safe_at,
            "estimated_duration_hours": task.estimated_duration_hours,
            "recovery_path": task.recovery_path,
            "depends_on": dependencies[task.id],
        }
        for task in tasks
    ]
    priority_rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    critical_actions = sorted(
        [row for row in task_rows if row["status"] != TaskStatus.DONE.value],
        key=lambda row: (priority_rank[row["priority"]], row["due_at"]),
    )[:5]

    latest_change = session.scalar(
        select(ChangeEvent)
        .where(ChangeEvent.tender_id == tender.id)
        .order_by(ChangeEvent.detected_at.desc())
    )
    change_payload = None
    recovery_candidate = None
    portfolio_impact = None
    impact_chain = []
    if latest_change:
        changed_requirements = [
            session.get(Requirement, requirement_id)
            for requirement_id in latest_change.affected_requirement_ids
        ]
        changed_requirements = [item for item in changed_requirements if item is not None]
        changed_requirements.sort(key=lambda item: item.version)
        if len(changed_requirements) >= 2:
            previous_requirement = changed_requirements[0]
            current_requirement = changed_requirements[-1]
            previous_assessment = latest_assessment(session, previous_requirement.id)
            current_assessment = latest_assessment(session, current_requirement.id)
            recovery_task_models = [
                task
                for task in tasks
                if task.recovery_path and task.requirement_id == current_requirement.id
            ]
            affected_recovery_requirements = {
                task.requirement_id for task in recovery_task_models if task.requirement_id
            }
            critical_gates_broken = int(
                previous_assessment is not None
                and previous_assessment.status == "SUPERSEDED"
                and current_assessment is not None
                and current_assessment.status != "SATISFIED"
                and current_requirement.gate_type == "MANDATORY"
            )
            superseded_count = sum(
                bool(assessment and assessment.status == "SUPERSEDED")
                for requirement in changed_requirements[:-1]
                if (assessment := latest_assessment(session, requirement.id)) is not None
            )
            result = assess_requirement(session, current_requirement)
            old_count = previous_requirement.rule_config.get("minimum_count")
            new_count = current_requirement.rule_config.get("minimum_count")
            has_count_diff = isinstance(old_count, int) and isinstance(new_count, int)
            is_generic = latest_change.event_type == "GENERIC_REQUIREMENT_MODIFIED"
            change_title = (
                f"Reviewed amendment · {current_requirement.source_document.filename}"
                if is_generic
                else f"Corrigendum #{current_requirement.source_document.version}"
            )
            change_payload = {
                "id": latest_change.id,
                "title": change_title,
                "summary": latest_change.summary,
                "stable_key": current_requirement.stable_key,
                "change_type": "MODIFIED",
                "display_kind": "COUNT" if has_count_diff else "TEXT",
                "subject_label": (
                    f"{current_requirement.rule_config.get('certification')}-certified personnel"
                    if current_requirement.rule_config.get("certification")
                    else "requirement wording"
                ),
                "old": previous_requirement.text,
                "new": current_requirement.text,
                "old_count": old_count,
                "new_count": new_count,
                "old_requirement_id": previous_requirement.id,
                "new_requirement_id": current_requirement.id,
                "old_version": previous_requirement.version,
                "new_version": current_requirement.version,
                "old_assessment": (
                    previous_assessment.status if previous_assessment else "UNCERTAIN"
                ),
                "new_assessment": (
                    current_assessment.status if current_assessment else "UNCERTAIN"
                ),
                "impact": {
                    "critical_gates_broken": critical_gates_broken,
                    "assessments_superseded": superseded_count,
                    "recovery_paths_found": len(affected_recovery_requirements),
                },
                "detected_at": latest_change.detected_at,
            }
            if is_generic:
                change_detail = (
                    f"Minimum changed from {old_count} to {new_count}"
                    if has_count_diff
                    else "Tracked wording and structured fields were versioned"
                )
                impact_chain = [
                    {"label": change_title, "detail": "Exact supplied source was confirmed"},
                    {
                        "label": f"{current_requirement.stable_key} v{current_requirement.version}",
                        "detail": change_detail,
                    },
                    {
                        "label": "Assessment recalculated",
                        "detail": (
                            f"{change_payload['old_assessment']} → "
                            f"{change_payload['new_assessment']}"
                        ),
                    },
                    {
                        "label": "Recovery plan",
                        "detail": f"{len(recovery_task_models)} dependent tasks created",
                    },
                    {
                        "label": "Human checkpoint",
                        "detail": "Final bid approval remains separate",
                    },
                ]
            else:
                impact_chain = [
                    {"label": change_title, "detail": "Procurement language changed"},
                    {
                        "label": f"{current_requirement.stable_key} v{current_requirement.version}",
                        "detail": f"Minimum increased from {old_count} to {new_count}",
                    },
                    {
                        "label": "Assessment stale",
                        "detail": (
                            f"{previous_requirement.stable_key} v"
                            f"{previous_requirement.version} superseded"
                        ),
                    },
                    {
                        "label": "Evidence shortfall",
                        "detail": f"Only {len(result.usable_employee_ids)} complete personnel sets",
                    },
                    {
                        "label": "Recovery actions",
                        "detail": f"{len(recovery_task_models)} dependent tasks created",
                    },
                ]
            employee = (
                employees.get(result.recovery_candidate_ids[0])
                if current_requirement.rule_config.get("kind") == "certified_staff"
                and result.recovery_candidate_ids
                else None
            )
            if employee:
                candidate_evidence = evidence_by_subject[employee.id]
                certificate = next(
                    (
                        item
                        for item in candidate_evidence
                        if item.type == "EMPLOYEE_CERTIFICATION"
                    ),
                    None,
                )
                cv = next((item for item in candidate_evidence if item.type == "CV"), None)
                recovery_candidate = {
                    "id": employee.id,
                    "name": employee.name,
                    "role": employee.role,
                    "certification_name": current_requirement.rule_config.get("certification"),
                    "certification": (
                        certificate.verification_status if certificate else "MISSING"
                    ),
                    "certification_valid_until": (
                        certificate.valid_until if certificate else None
                    ),
                    "cv": cv.verification_status if cv else "MISSING",
                    "availability": employee.availability_status,
                    "can_satisfy_now": employee.id in result.usable_employee_ids,
                }
        if len(changed_requirements) >= 2 and (
            tender.id == "BID-DEMO-001"
            and len(changed_requirements) == 2
            and previous_requirement.stable_key == "R17"
            and current_requirement.stable_key == "R17"
            and previous_requirement.version == 1
            and current_requirement.version == 2
            and previous_requirement.rule_config.get("kind") == "certified_staff"
            and current_requirement.rule_config.get("kind") == "certified_staff"
            and old_count == 3
            and current_requirement.rule_config.get("minimum_count") == 4
            and previous_assessment is not None
            and previous_assessment.status == "SUPERSEDED"
            and current_assessment is not None
            and current_assessment.status == "PARTIAL"
            and result.status.value == "PARTIAL"
            and len(result.usable_employee_ids) == 3
            and result.recovery_candidate_ids == ["EMP-D"]
        ):
            portfolio_impact = build_demo_portfolio_impact(
                tender,
                current_requirement,
                result,
            )

    activities = session.scalars(
        select(ActivityEvent)
        .where(ActivityEvent.tender_id == tender.id)
        .order_by(ActivityEvent.timestamp.desc(), ActivityEvent.id.desc())
    ).all()
    latest_interpretation = next(
        (activity for activity in activities if activity.event_type == "INTERPRETATION_COMPLETED"),
        None,
    )
    if latest_interpretation is not None:
        interpretation_mode = {
            "bedrock": "BEDROCK",
            "groq": "GROQ",
        }.get(latest_interpretation.actor, "DEMO_FALLBACK")
    else:
        interpretation_mode = "DEMO_FALLBACK"
    invalidated_approval_ids = {
        activity.entity_id
        for activity in activities
        if activity.event_type == "HUMAN_APPROVAL_INVALIDATED" and activity.entity_id
    }
    approval = next(
        (
            candidate
            for candidate in session.scalars(
                select(HumanApproval)
                .where(HumanApproval.tender_id == tender.id)
                .order_by(HumanApproval.approved_at.desc())
            ).all()
            if candidate.id not in invalidated_approval_ids
        ),
        None,
    )
    gates = critical_gate_trace(session, tender.id)
    coverage = submission_coverage_trace(session, tender)
    feasibility = operational_feasibility_trace(session, tender)
    deadline = deadline_risk_trace(session, tender)
    uncertain_fixture = any(item.stable_key == "R19" for item in all_requirements)
    fixture_id = (
        "uncertain-ambiguous-clause"
        if uncertain_fixture
        else "blocked-no-fourth-engineer"
        if feasibility["status"] == "BLOCKED" and latest_change
        else "main-corrigendum"
    )
    return {
        "bid": {
            "id": tender.id,
            "title": tender.title,
            "agency": tender.agency,
            "reference_number": tender.reference_number,
            "closing_at": tender.closing_at,
            "source_type": tender.source_type,
            "synthetic": True,
            "fixture_id": fixture_id,
        },
        "company": {
            "id": tender.company.id,
            "name": tender.company.name,
            "uen": tender.company.uen,
            "industry": tender.company.industry,
            "employee_count": tender.company.employee_count,
            "annual_revenue": tender.company.annual_revenue,
        },
        "interpretation": {
            "mode": interpretation_mode,
            "label": {
                "BEDROCK": "Bedrock",
                "GROQ": "Groq",
                "DEMO_FALLBACK": "Demo fallback",
            }[interpretation_mode],
            "model_id": (
                settings.bedrock_model_id
                if interpretation_mode == "BEDROCK"
                else settings.groq_model_id
                if interpretation_mode == "GROQ"
                else None
            ),
            "source": (
                "persisted_activity" if latest_interpretation else "no_persisted_interpretation"
            ),
            "event_id": latest_interpretation.id if latest_interpretation else None,
        },
        "metrics": {
            "operational_status": feasibility["status"],
            "previous_operational_status": tender.previous_operational_status,
            "critical_gates_verified": gates["verified"],
            "critical_gates_total": gates["total"],
            "submission_coverage": coverage["display_percent"],
            "deadline_risk": deadline["risk"],
        },
        "calculations": {
            "operational_feasibility": {
                **feasibility,
                "persisted_value": tender.operational_status,
                "matches_persisted_value": feasibility["status"] == tender.operational_status,
            },
            "critical_gates": gates,
            "submission_coverage": {
                **coverage,
                "persisted_value": round(tender.submission_coverage),
                "matches_persisted_value": coverage["display_percent"]
                == round(tender.submission_coverage),
            },
            "deadline_risk": {
                **deadline,
                "persisted_value": tender.deadline_risk,
                "matches_persisted_value": deadline["risk"] == tender.deadline_risk,
            },
        },
        "requirements": requirement_rows,
        "tasks": task_rows,
        "critical_actions": critical_actions,
        "latest_change": change_payload,
        "impact_chain": impact_chain,
        "recovery_candidate": recovery_candidate,
        "portfolio_impact": portfolio_impact,
        "activity_events": [
            {
                "id": activity.id,
                "event_type": activity.event_type,
                "actor": activity.actor,
                "entity_id": activity.entity_id,
                "summary": activity.summary,
                "timestamp": activity.timestamp,
            }
            for activity in activities
        ],
        "human_review": {
            "required": tender.human_action_required,
            "approved": approval is not None,
            "approved_by": approval.approved_by if approval else None,
            "approved_at": approval.approved_at if approval else None,
        },
        "disclaimer": "BidOps supports internal preparation and operational verification. Final tender interpretation and submission remain the responsibility of the supplier.",
    }
