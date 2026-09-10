from collections.abc import Callable
from datetime import datetime
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.database import SessionLocal
from app.enums import AssessmentStatus, TaskPriority, TaskStatus
from app.graph.state import BidState
from app.llm.interpreter import TenderInterpreter
from app.llm.schemas import (
    ChangeInterpretationRequest,
    RequirementSource,
    StructuredRequirement,
)
from app.models import (
    ActivityEvent,
    Assessment,
    ChangeEvent,
    Requirement,
    Task,
    TaskDependency,
    Tender,
    TenderDocument,
)
from app.services.assessment import assess_requirement
from app.services.clock import now
from app.services.deadline import calculate_deadline_risk
from app.services.metrics import (
    calculate_submission_coverage,
    critical_gate_summary,
    derive_operational_status,
    latest_assessment,
)


class CorrigendumAlreadyAppliedError(ValueError):
    pass


CORRIGENDUM_DOCUMENT = "DGA_ICT_2026_017_Corrigendum_2.pdf"
CORRIGENDUM_SECTION = "1. Amendment to Clause 4.3"
CORRIGENDUM_TEXT = (
    "Clause 4.3 is amended. Replace ‘not fewer than three personnel holding valid CISSP "
    "certification’ with ‘not fewer than four personnel holding valid CISSP certification’. "
    "All other clauses remain unchanged."
)


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


def build_corrigendum_graph(
    session_factory: sessionmaker[Session] = SessionLocal,
    interpretation_service: TenderInterpreter | None = None,
    corrigendum_text: str = CORRIGENDUM_TEXT,
) -> Callable[[BidState], BidState]:
    interpreter = interpretation_service or TenderInterpreter()
    def load_current_bid_state(state: BidState) -> BidState:
        with session_factory() as session:
            tender = session.get(Tender, state["tender_id"])
            if tender is None:
                raise ValueError(f"Unknown bid: {state['tender_id']}")
            duplicate = session.get(ChangeEvent, "CHANGE-CORR-2")
            if duplicate:
                raise CorrigendumAlreadyAppliedError("Corrigendum #2 has already been applied.")
            return {
                "previous_operational_status": tender.operational_status,
                "operational_status": tender.operational_status,
                "errors": [],
            }

    def detect_changes_and_version(state: BidState) -> BidState:
        with session_factory() as session:
            previous = session.scalar(
                select(Requirement)
                .where(
                    Requirement.tender_id == state["tender_id"],
                    Requirement.stable_key == "R17",
                )
                .order_by(Requirement.version.desc())
            )
            if previous is None:
                raise ValueError("R17 is missing; Corrigendum #2 cannot be matched safely.")

            existing = StructuredRequirement(
                stable_key=previous.stable_key,
                text=previous.text,
                requirement_type=previous.requirement_type,
                gate_type=previous.gate_type,
                deadline=previous.deadline,
                minimum_count=previous.rule_config.get("minimum_count"),
                certification=previous.rule_config.get("certification"),
                compulsory=previous.gate_type == "MANDATORY",
                interpretation_status="INTERPRETED",
                source=RequirementSource(
                    document=previous.source_document.filename,
                    page=previous.source_page,
                    section=previous.source_section,
                    snippet=previous.source_snippet,
                ),
            )
            interpretation = interpreter.interpret_change(
                ChangeInterpretationRequest(
                    existing_requirement=existing,
                    corrigendum_document=CORRIGENDUM_DOCUMENT,
                    page=2,
                    section=CORRIGENDUM_SECTION,
                    text=corrigendum_text,
                )
            )
            change = interpretation.result
            if change.interpretation_status != "INTERPRETED":
                raise ValueError(
                    "Corrigendum interpretation is UNCERTAIN; no requirement was superseded."
                )
            if change.change_type != "MODIFIED" or change.affected_stable_key != previous.stable_key:
                raise ValueError(
                    "Corrigendum does not confidently modify R17; no requirement was superseded."
                )
            interpreted = change.resulting_requirement
            if interpreted is None or interpreted.minimum_count != 4:
                raise ValueError(
                    "The canonical workflow requires a validated R17 minimum_count change to 4."
                )
            if (
                interpreted.certification != existing.certification
                or interpreted.requirement_type != existing.requirement_type
                or interpreted.gate_type != existing.gate_type
            ):
                raise ValueError(
                    "The interpretation changed fields outside the canonical R17 amendment."
                )

            document = TenderDocument(
                id="DOC-CORR-2",
                tender_id=state["tender_id"],
                filename=CORRIGENDUM_DOCUMENT,
                document_type="CORRIGENDUM",
                version=2,
                uploaded_at=now(),
                text_content_reference="demo://documents/DOC-CORR-2",
            )
            updated = Requirement(
                id="REQ-R17-V2",
                stable_key="R17",
                tender_id=state["tender_id"],
                version=2,
                text=interpreted.text,
                requirement_type=interpreted.requirement_type,
                gate_type=interpreted.gate_type,
                deadline=interpreted.deadline,
                source_document_id=document.id,
                source_page=interpreted.source.page,
                source_section=interpreted.source.section,
                source_snippet=interpreted.source.snippet,
                supersedes_requirement_id=previous.id,
                rule_config={
                    **previous.rule_config,
                    "certification": interpreted.certification,
                    "minimum_count": interpreted.minimum_count,
                },
                created_at=now(),
            )
            old_assessment = latest_assessment(session, previous.id)
            if old_assessment is None:
                raise ValueError("R17 v1 has no assessment to supersede.")
            old_assessment.status = "SUPERSEDED"

            event = ChangeEvent(
                id="CHANGE-CORR-2",
                tender_id=state["tender_id"],
                source_document_id=document.id,
                event_type="REQUIREMENT_CHANGED",
                detected_at=now(),
                summary=change.reason_summary,
                affected_requirement_ids=[previous.id, updated.id],
            )
            session.add_all([document, updated, event])
            _activity(
                session,
                state["tender_id"],
                "INTERPRETATION_COMPLETED",
                "R17",
                (
                    f"{interpretation.mode}: {change.change_type} matched to R17; "
                    f"changed fields: {', '.join(item.field for item in change.changed_fields)}."
                ),
                actor=interpretation.mode.lower(),
            )
            _activity(
                session,
                state["tender_id"],
                "DOCUMENT_PARSED",
                document.id,
                "Corrigendum #2 received and parsed.",
            )
            _activity(
                session,
                state["tender_id"],
                "CHANGE_DETECTED",
                "R17",
                change.reason_summary,
            )
            _activity(
                session,
                state["tender_id"],
                "REQUIREMENT_VERSION_CREATED",
                updated.id,
                "R17 v2 created; R17 v1 remains in the audit history.",
            )
            _activity(
                session,
                state["tender_id"],
                "ASSESSMENT_SUPERSEDED",
                previous.id,
                "R17 v1 assessment marked SUPERSEDED after Corrigendum #2.",
            )
            session.commit()
            return {
                "current_document_ids": [document.id],
                "previous_requirement_id": previous.id,
                "changed_requirement_id": updated.id,
                "change_events": [{"id": event.id, "event_type": event.event_type}],
                "interpretation_mode": interpretation.mode,
            }

    def reassess_affected_requirement(state: BidState) -> BidState:
        with session_factory() as session:
            requirement = session.get(Requirement, state["changed_requirement_id"])
            result = assess_requirement(session, requirement)
            assessment = Assessment(
                id="ASM-R17-V2",
                requirement_id=requirement.id,
                requirement_version=requirement.version,
                status=result.status.value,
                evidence_ids=result.evidence_ids,
                reason_summary=result.reason,
                assessed_at=now(),
                assessment_method="RULE",
            )
            session.add(assessment)
            _activity(
                session,
                state["tender_id"],
                "ASSESSMENT_UPDATED",
                requirement.id,
                f"R17 v2 reassessed as {result.status.value}: {result.reason}",
            )
            _activity(
                session,
                state["tender_id"],
                "EVIDENCE_SEARCHED",
                requirement.id,
                "Evidence Registry searched for an additional valid CISSP-certified employee.",
            )
            if result.recovery_candidate_ids:
                _activity(
                    session,
                    state["tender_id"],
                    "RECOVERY_FOUND",
                    result.recovery_candidate_ids[0],
                    "Engineer D identified as a recovery candidate; CV is stale and availability is unknown.",
                )
            session.commit()
            return {
                "assessments": [{"id": assessment.id, "status": assessment.status}],
                "recovery_candidate_ids": result.recovery_candidate_ids,
                "evidence": [{"id": evidence_id} for evidence_id in result.evidence_ids],
            }

    def create_recovery_tasks(state: BidState) -> BidState:
        assessment_status = state.get("assessments", [{}])[0].get("status")
        if (
            assessment_status != AssessmentStatus.PARTIAL.value
            or not state.get("recovery_candidate_ids")
        ):
            return {"tasks": []}
        requirement_id = state["changed_requirement_id"]
        tasks = [
            Task(
                id="TASK-REC-CV",
                tender_id=state["tender_id"],
                requirement_id=requirement_id,
                title="Request updated CV from Engineer D",
                description="Obtain and verify a current CV for the proposed fourth CISSP engineer.",
                owner="Bid Team",
                status=TaskStatus.OPEN.value,
                priority=TaskPriority.CRITICAL.value,
                due_at=datetime(2026, 8, 23, 5, 0),
                latest_safe_at=datetime(2026, 8, 23, 5, 0),
                estimated_duration_hours=2,
                recovery_path=True,
                created_at=now(),
                updated_at=now(),
            ),
            Task(
                id="TASK-REC-AVAIL",
                tender_id=state["tender_id"],
                requirement_id=requirement_id,
                title="Confirm Engineer D availability",
                description="Obtain delivery-manager confirmation that Engineer D is available for the proposed service period.",
                owner="Harish Nair",
                status=TaskStatus.OPEN.value,
                priority=TaskPriority.CRITICAL.value,
                due_at=datetime(2026, 8, 23, 5, 0),
                latest_safe_at=datetime(2026, 8, 23, 5, 0),
                estimated_duration_hours=1,
                recovery_path=True,
                created_at=now(),
                updated_at=now(),
            ),
            Task(
                id="TASK-REC-PLAN",
                tender_id=state["tender_id"],
                requirement_id=requirement_id,
                title="Update manpower schedule",
                description="Add Engineer D to the named personnel schedule after evidence checks complete.",
                owner="Aisha Rahman",
                status=TaskStatus.WAITING.value,
                priority=TaskPriority.HIGH.value,
                due_at=datetime(2026, 8, 26, 9, 0),
                latest_safe_at=datetime(2026, 8, 27, 6, 0),
                estimated_duration_hours=2,
                recovery_path=True,
                created_at=now(),
                updated_at=now(),
            ),
            Task(
                id="TASK-REC-RECHECK",
                tender_id=state["tender_id"],
                requirement_id=requirement_id,
                title="Re-run R17 verification",
                description="Reassess R17 only after the updated CV, availability, and manpower schedule are verified.",
                owner="Grace Lim",
                status=TaskStatus.WAITING.value,
                priority=TaskPriority.CRITICAL.value,
                due_at=datetime(2026, 8, 27, 4, 0),
                latest_safe_at=datetime(2026, 8, 27, 4, 0),
                estimated_duration_hours=1,
                recovery_path=True,
                created_at=now(),
                updated_at=now(),
            ),
        ]
        dependencies = [
            TaskDependency(task_id="TASK-REC-PLAN", depends_on_task_id="TASK-REC-CV"),
            TaskDependency(task_id="TASK-REC-PLAN", depends_on_task_id="TASK-REC-AVAIL"),
            TaskDependency(task_id="TASK-REC-RECHECK", depends_on_task_id="TASK-REC-PLAN"),
        ]
        with session_factory() as session:
            session.add_all([*tasks, *dependencies])
            for task in tasks:
                _activity(
                    session,
                    state["tender_id"],
                    "TASK_CREATED",
                    task.id,
                    f"Recovery task created: {task.title}.",
                )
            session.commit()
        return {"tasks": [{"id": task.id, "title": task.title} for task in tasks]}

    def recompute_bid_state(state: BidState) -> BidState:
        with session_factory() as session:
            tender = session.get(Tender, state["tender_id"])
            status = derive_operational_status(session, tender)
            tender.previous_operational_status = state["previous_operational_status"]
            tender.operational_status = status.value
            tender.submission_coverage = calculate_submission_coverage(session, tender)
            tender.deadline_risk = calculate_deadline_risk(session, tender).value
            tender.human_action_required = True
            _activity(
                session,
                tender.id,
                "DEADLINE_RISK_CHANGED",
                tender.id,
                f"Deadline risk recalculated as {tender.deadline_risk}; recovery confirmation remains possible before closing.",
            )
            _activity(
                session,
                tender.id,
                "OPERATIONAL_STATUS_CHANGED",
                tender.id,
                f"Operational feasibility changed: {state['previous_operational_status']} → {status.value}.",
            )
            _activity(
                session,
                tender.id,
                "HUMAN_ACTION_REQUIRED",
                tender.id,
                "Human review is required before the internal bid package can be approved.",
            )
            session.commit()
            return {
                "operational_status": status.value,
                "critical_gate_summary": critical_gate_summary(session, tender.id),
                "submission_coverage": tender.submission_coverage,
                "deadline_risk": tender.deadline_risk,
                "human_action_required": True,
            }

    graph = StateGraph(BidState)
    graph.add_node("load_current_bid_state", load_current_bid_state)
    graph.add_node("detect_changes_and_version", detect_changes_and_version)
    graph.add_node("reassess_affected_requirement", reassess_affected_requirement)
    graph.add_node("create_recovery_tasks", create_recovery_tasks)
    graph.add_node("recompute_bid_state", recompute_bid_state)
    graph.add_edge(START, "load_current_bid_state")
    graph.add_edge("load_current_bid_state", "detect_changes_and_version")
    graph.add_edge("detect_changes_and_version", "reassess_affected_requirement")
    graph.add_edge("reassess_affected_requirement", "create_recovery_tasks")
    graph.add_edge("create_recovery_tasks", "recompute_bid_state")
    graph.add_edge("recompute_bid_state", END)
    compiled = graph.compile()
    return compiled.invoke


run_corrigendum_workflow = build_corrigendum_graph()


def apply_corrigendum(
    tender_id: str,
    interpretation_service: TenderInterpreter | None = None,
    corrigendum_text: str = CORRIGENDUM_TEXT,
) -> BidState:
    workflow = (
        build_corrigendum_graph(
            interpretation_service=interpretation_service,
            corrigendum_text=corrigendum_text,
        )
        if interpretation_service is not None or corrigendum_text != CORRIGENDUM_TEXT
        else run_corrigendum_workflow
    )
    return workflow(
        {
            "session_id": f"corrigendum-{uuid4().hex[:8]}",
            "tender_id": tender_id,
            "errors": [],
        }
    )
