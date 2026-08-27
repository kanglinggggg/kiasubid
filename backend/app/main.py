from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import create_schema, get_session
from app.demo.fixtures import list_demo_fixtures, load_demo_fixture
from app.demo.seed import DEMO_BID_ID, reset_demo, seed_demo
from app.enums import OperationalStatus, TaskStatus, VerificationStatus
from app.graph.workflow import CorrigendumAlreadyAppliedError, apply_corrigendum
from app.llm.interpreter import TenderInterpreter
from app.llm.schemas import (
    ChangeInterpretationEnvelope,
    ChangeInterpretationRequest,
    RequirementInterpretationEnvelope,
    RequirementInterpretationRequest,
)
from app.models import Evidence, HumanApproval, Task, TaskDependency, Tender
from app.schemas import EvidenceVerificationRequest, HumanApprovalRequest
from app.serializers import serialize_bid
from app.services.clock import now
from app.services.deadline import calculate_deadline_risk
from app.services.metrics import calculate_submission_coverage, derive_operational_status


@asynccontextmanager
async def lifespan(_: FastAPI):
    create_schema()
    from app.database import SessionLocal

    with SessionLocal() as session:
        seed_demo(session)
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Persistent, evidence-backed operational bid control.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
interpreter = TenderInterpreter()


def _get_bid_or_404(session: Session, bid_id: str) -> Tender:
    tender = session.get(Tender, bid_id)
    if tender is None:
        raise HTTPException(status_code=404, detail="Bid not found.")
    return tender


@app.get("/api/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "mode": "demo" if settings.demo_mode else "live",
        "interpretation_provider": settings.llm_provider,
        "interpretation_configuration": (
            "live_configured" if settings.interpretation_configured else "demo_fallback_only"
        ),
    }


@app.post(
    "/api/tenders/interpret-requirements",
    response_model=RequirementInterpretationEnvelope,
)
def interpret_tender_requirements(
    payload: RequirementInterpretationRequest,
) -> RequirementInterpretationEnvelope:
    """Interpret supplied page/section text without persisting or assessing it."""
    return interpreter.interpret_requirements(payload)


@app.post(
    "/api/corrigenda/interpret-change",
    response_model=ChangeInterpretationEnvelope,
)
def interpret_corrigendum_change(
    payload: ChangeInterpretationRequest,
) -> ChangeInterpretationEnvelope:
    """Interpret a semantic change without changing bid or assessment state."""
    return interpreter.interpret_change(payload)


@app.get("/api/bids/{bid_id}")
def get_bid(bid_id: str, session: Session = Depends(get_session)) -> dict:
    _get_bid_or_404(session, bid_id)
    return serialize_bid(session, bid_id)


@app.post("/api/demo/reset")
def reset(session: Session = Depends(get_session)) -> dict:
    reset_demo(session)
    return serialize_bid(session, DEMO_BID_ID)


@app.get("/api/demo/fixtures")
def demo_fixtures() -> list[dict[str, str]]:
    return list_demo_fixtures()


@app.post("/api/demo/fixtures/{fixture_id}")
def select_demo_fixture(fixture_id: str, session: Session = Depends(get_session)) -> dict:
    try:
        tender = load_demo_fixture(session, fixture_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    session.expire_all()
    return serialize_bid(session, tender.id)


@app.post("/api/companies/load-demo")
def load_demo(session: Session = Depends(get_session)) -> dict:
    tender = seed_demo(session)
    return serialize_bid(session, tender.id)


@app.post("/api/demo/bids/{bid_id}/apply-corrigendum")
def apply_demo_corrigendum(bid_id: str, session: Session = Depends(get_session)) -> dict:
    _get_bid_or_404(session, bid_id)
    try:
        apply_corrigendum(bid_id)
    except CorrigendumAlreadyAppliedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    session.expire_all()
    return serialize_bid(session, bid_id)


@app.post("/api/bids/{bid_id}/corrigenda")
def apply_corrigendum_alias(bid_id: str, session: Session = Depends(get_session)) -> dict:
    return apply_demo_corrigendum(bid_id, session)


@app.post("/api/tasks/{task_id}/complete")
def complete_task(task_id: str, session: Session = Depends(get_session)) -> dict:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    dependencies = session.scalars(
        select(TaskDependency).where(TaskDependency.task_id == task_id)
    ).all()
    waiting_on = [
        dependency.depends_on_task_id
        for dependency in dependencies
        if (dependency_task := session.get(Task, dependency.depends_on_task_id))
        and dependency_task.status != TaskStatus.DONE.value
    ]
    if waiting_on:
        raise HTTPException(
            status_code=409,
            detail=f"Complete dependencies first: {', '.join(waiting_on)}.",
        )
    task.status = TaskStatus.DONE.value
    task.completed_at = now()
    task.updated_at = now()
    tender = session.get(Tender, task.tender_id)
    tender.submission_coverage = calculate_submission_coverage(session, tender)
    tender.deadline_risk = calculate_deadline_risk(session, tender).value
    session.commit()
    return serialize_bid(session, task.tender_id)


@app.post("/api/evidence/{evidence_id}/verify")
def verify_evidence(
    evidence_id: str,
    payload: EvidenceVerificationRequest,
    session: Session = Depends(get_session),
) -> dict:
    evidence = session.get(Evidence, evidence_id)
    if evidence is None:
        raise HTTPException(status_code=404, detail="Evidence not found.")
    evidence.verification_status = VerificationStatus.VERIFIED.value
    evidence.verified_at = now()
    evidence.updated_at = now()
    session.commit()
    tender = session.scalar(select(Tender).where(Tender.company_id == evidence.company_id))
    return {
        "id": evidence.id,
        "verification_status": evidence.verification_status,
        "verified_by": payload.verified_by,
        "bid_id": tender.id if tender else None,
    }


@app.post("/api/bids/{bid_id}/human-approve")
def human_approve(
    bid_id: str,
    payload: HumanApprovalRequest,
    session: Session = Depends(get_session),
) -> dict:
    tender = _get_bid_or_404(session, bid_id)
    current = derive_operational_status(session, tender)
    if current != OperationalStatus.FEASIBLE:
        raise HTTPException(
            status_code=409,
            detail="The internal package cannot be approved while a mandatory gate is unresolved.",
        )
    approval = HumanApproval(
        id=f"APPROVAL-{uuid4().hex[:12]}",
        tender_id=bid_id,
        approved_by=payload.approved_by,
        note=payload.note,
        approved_at=now(),
    )
    session.add(approval)
    session.commit()
    return serialize_bid(session, bid_id)
