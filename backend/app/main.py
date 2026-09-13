from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.amendments import (
    AmendmentAlreadyAppliedError,
    AmendmentApplyBlockedError,
    AmendmentApplyRequest,
    AmendmentPreviewExpiredError,
    AmendmentPreviewRequest,
    AmendmentPreviewResponse,
    AmendmentPreviewStaleError,
    AmendmentSourceVersionConflictError,
    apply_amendment_preview,
    preview_amendment,
)
from app.company_profile import (
    BusinessProfileIngestionError,
    BusinessProfileIngestionResult,
    ingest_business_profile,
)
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
from app.portfolio import (
    PortfolioSimulationRequest,
    PortfolioSimulationResponse,
    capability_roadmap,
    evaluate_portfolio,
    strategy_routes,
)
from app.public_data import AwardContextResponse, get_award_context
from app.schemas import EvidenceVerificationRequest, HumanApprovalRequest
from app.serializers import serialize_bid
from app.services.clock import now
from app.services.deadline import calculate_deadline_risk
from app.services.metrics import calculate_submission_coverage, derive_operational_status
from app.tender_lab.agent_loop import run_agent_loop
from app.tender_lab.agent_models import AgentLoopRequest, AgentLoopResponse
from app.tender_lab.change_simulator import (
    ChangeSimulationRequest,
    ChangeSimulationResponse,
    simulate_tender_change,
)
from app.tender_lab.extractor import (
    MAX_UPLOAD_BYTES,
    DocumentExtractionError,
    extract_document,
)
from app.tender_lab.partner_router import (
    PartnerRoutePackage,
    PartnerRouteRequest,
    build_partner_route_package,
)
from app.tender_lab.proposal_builder import (
    ProposalAnswerReviewRequest,
    ProposalAnswerReviewResponse,
    ProposalDraftRequest,
    ProposalDraftResponse,
    ProposalPlanRequest,
    ProposalPlanResponse,
    build_proposal_plan,
    generate_proposal_draft,
    review_proposal_answer,
)
from app.tender_lab.sample import sample_request
from app.tender_lab.schemas import (
    DocumentExtractionResponse,
    TenderLabRequest,
    TenderLabResponse,
)
from app.tender_lab.workflow import run_tender_lab


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


@app.post("/api/portfolio/simulate", response_model=PortfolioSimulationResponse)
def simulate_portfolio(payload: PortfolioSimulationRequest) -> PortfolioSimulationResponse:
    """Run a deterministic, non-persisting capability simulation for supplied bid scenarios."""
    evaluation = evaluate_portfolio(payload)
    return PortfolioSimulationResponse.model_validate(
        {
            **evaluation,
            "routes": strategy_routes(payload),
            "capability_roadmap": capability_roadmap(payload, evaluation),
        }
    )


@app.get("/api/tender-lab/sample/{mode}", response_model=TenderLabRequest)
def tender_lab_sample(mode: str) -> TenderLabRequest:
    """Load an explicit synthetic sample without changing the operational demo."""
    normalised_mode = mode.upper()
    if normalised_mode not in {"SME", "STARTUP"}:
        raise HTTPException(status_code=404, detail="Tender Lab mode must be SME or STARTUP.")
    return sample_request(normalised_mode)  # type: ignore[arg-type]


@app.post("/api/tender-lab/analyze", response_model=TenderLabResponse)
def analyze_tender_lab(payload: TenderLabRequest) -> TenderLabResponse:
    """Run the non-persisting Tender Lab decision-support workflow."""
    return run_tender_lab(payload)


@app.post("/api/tender-lab/agent-loop", response_model=AgentLoopResponse)
def run_tender_lab_agent_loop(payload: AgentLoopRequest) -> AgentLoopResponse:
    """Run a bounded planner-specialist-critic loop without changing bid state."""
    return run_agent_loop(payload)


@app.post("/api/tender-lab/proposal/plan", response_model=ProposalPlanResponse)
def plan_tender_lab_proposal(payload: ProposalPlanRequest) -> ProposalPlanResponse:
    """Plan a bounded, source-aware founder interview without persisting supplier material."""
    return build_proposal_plan(payload)


@app.post(
    "/api/tender-lab/proposal/review-answer",
    response_model=ProposalAnswerReviewResponse,
)
def review_tender_lab_proposal_answer(
    payload: ProposalAnswerReviewRequest,
) -> ProposalAnswerReviewResponse:
    """Critique one recorded founder answer with a visible deterministic fallback."""
    try:
        return review_proposal_answer(payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/tender-lab/proposal/draft", response_model=ProposalDraftResponse)
def draft_tender_lab_proposal(payload: ProposalDraftRequest) -> ProposalDraftResponse:
    """Generate a grounded preparation draft from the completed founder interview."""
    try:
        return generate_proposal_draft(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/tender-lab/partner-route", response_model=PartnerRoutePackage)
def build_tender_lab_partner_route(payload: PartnerRouteRequest) -> PartnerRoutePackage:
    """Build a non-persisting, evidence-bounded subcontracting research package."""
    return build_partner_route_package(payload)


@app.post("/api/tender-lab/simulate-change", response_model=ChangeSimulationResponse)
def simulate_tender_lab_change(payload: ChangeSimulationRequest) -> ChangeSimulationResponse:
    """Rehearse how supplied amendment wording invalidates Tender Lab outputs without persisting."""
    return simulate_tender_change(payload)


@app.post("/api/tender-lab/extract", response_model=DocumentExtractionResponse)
async def extract_tender_lab_document(
    file: UploadFile = File(...),
) -> DocumentExtractionResponse:
    """Extract selectable text in memory; no uploaded bytes are persisted."""
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    try:
        return extract_document(
            filename=file.filename or "upload",
            content_type=file.content_type,
            raw=raw,
        )
    except DocumentExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        await file.close()


@app.post(
    "/api/tender-lab/company-profile/extract",
    response_model=BusinessProfileIngestionResult,
)
async def extract_tender_lab_company_profile(
    file: UploadFile = File(...),
) -> BusinessProfileIngestionResult:
    """Extract an uploaded profile in memory and return source-backed declared company facts."""
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    try:
        document = extract_document(
            filename=file.filename or "business-profile.pdf",
            content_type=file.content_type,
            raw=raw,
        )
        return ingest_business_profile(document)
    except (DocumentExtractionError, BusinessProfileIngestionError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        await file.close()


@app.get("/api/public-data/gebiz/awards", response_model=AwardContextResponse)
def gebiz_award_context(
    query: str = Query(default="cybersecurity", min_length=2, max_length=100),
    agency: str | None = Query(default=None, max_length=160),
) -> AwardContextResponse:
    """Return descriptive context from the official MOF award dataset or a labelled cache."""
    return get_award_context(query=query, agency=agency)


@app.get("/api/bids/{bid_id}")
def get_bid(bid_id: str, session: Session = Depends(get_session)) -> dict:
    _get_bid_or_404(session, bid_id)
    return serialize_bid(session, bid_id)


@app.post(
    "/api/bids/{bid_id}/amendments/preview",
    response_model=AmendmentPreviewResponse,
)
def preview_bid_amendment(
    bid_id: str,
    payload: AmendmentPreviewRequest,
    session: Session = Depends(get_session),
) -> AmendmentPreviewResponse:
    """Dry-run one user-selected current requirement without writing bid state."""
    try:
        return preview_amendment(session, bid_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (AmendmentPreviewStaleError, AmendmentSourceVersionConflictError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@app.post("/api/bids/{bid_id}/amendments/apply")
def apply_bid_amendment(
    bid_id: str,
    payload: AmendmentApplyRequest,
    session: Session = Depends(get_session),
) -> dict:
    """Apply a reviewed preview to the internal workspace in one transaction."""
    _get_bid_or_404(session, bid_id)
    try:
        apply_amendment_preview(session, bid_id, payload)
    except (AmendmentPreviewExpiredError, AmendmentApplyBlockedError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except (
        AmendmentPreviewStaleError,
        AmendmentAlreadyAppliedError,
        AmendmentSourceVersionConflictError,
    ) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    session.expire_all()
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
