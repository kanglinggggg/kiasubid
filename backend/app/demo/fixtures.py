from sqlalchemy.orm import Session

from app.demo.seed import DEMO_BID_ID, DEMO_NOW, reset_demo
from app.graph.workflow import apply_corrigendum
from app.models import ActivityEvent, Assessment, Evidence, Requirement, Tender
from app.services.deadline import calculate_deadline_risk
from app.services.metrics import calculate_submission_coverage, derive_operational_status

DEMO_FIXTURES = [
    {
        "id": "main-corrigendum",
        "label": "Main corrigendum demo",
        "description": "Baseline bid with three verified CISSP engineers and every mandatory gate met.",
        "expected_status": "FEASIBLE",
    },
    {
        "id": "blocked-no-fourth-engineer",
        "label": "BLOCKED · no fourth engineer",
        "description": "Corrigendum #2 raises R17 to four, but no verified recovery candidate remains.",
        "expected_status": "BLOCKED",
    },
    {
        "id": "uncertain-ambiguous-clause",
        "label": "UNCERTAIN · ambiguous clause",
        "description": "A mandatory standby-resource clause has no defined count or qualification threshold.",
        "expected_status": "UNCERTAIN",
    },
]


def list_demo_fixtures() -> list[dict[str, str]]:
    return DEMO_FIXTURES


def load_demo_fixture(session: Session, fixture_id: str) -> Tender:
    if fixture_id not in {fixture["id"] for fixture in DEMO_FIXTURES}:
        raise LookupError(f"Unknown demo fixture: {fixture_id}")

    tender = reset_demo(session)
    if fixture_id == "main-corrigendum":
        return tender

    if fixture_id == "blocked-no-fourth-engineer":
        fourth_certificate = session.get(Evidence, "EV-D-CERT")
        fourth_certificate.verification_status = "STALE"
        fourth_certificate.verified_at = None
        session.commit()
        apply_corrigendum(DEMO_BID_ID)
        session.expire_all()
        return session.get(Tender, DEMO_BID_ID)

    ambiguous = Requirement(
        id="REQ-R19-V1",
        stable_key="R19",
        tender_id=DEMO_BID_ID,
        version=1,
        text="The Tenderer shall maintain adequate suitably qualified standby resources for the service period.",
        requirement_type="MANPOWER",
        gate_type="MANDATORY",
        source_document_id="DOC-TECH",
        source_page=19,
        source_section="4.8 Standby Resources",
        source_snippet="The Tenderer shall maintain adequate suitably qualified standby resources",
        rule_config={"kind": "ambiguous"},
        created_at=DEMO_NOW,
    )
    assessment = Assessment(
        id="ASM-R19-V1",
        requirement_id=ambiguous.id,
        requirement_version=1,
        status="UNCERTAIN",
        evidence_ids=[],
        reason_summary="The clause does not define how many standby resources are adequate or which qualifications are acceptable. Human clarification is required.",
        assessed_at=DEMO_NOW,
        assessment_method="RULE",
    )
    activity = ActivityEvent(
        id="ACT-FIX-UNCERTAIN",
        tender_id=DEMO_BID_ID,
        event_type="HUMAN_ACTION_REQUIRED",
        actor="system",
        entity_id=ambiguous.id,
        summary="R19 remains UNCERTAIN because the mandatory resource threshold is ambiguous.",
        timestamp=DEMO_NOW,
    )
    session.add_all([ambiguous, assessment, activity])
    session.flush()
    tender.previous_operational_status = "FEASIBLE"
    tender.operational_status = derive_operational_status(session, tender).value
    tender.submission_coverage = calculate_submission_coverage(session, tender)
    tender.deadline_risk = calculate_deadline_risk(session, tender).value
    session.commit()
    return tender
