from datetime import datetime

import pytest
from app.database import SessionLocal
from app.demo.seed import DEMO_BID_ID
from app.enums import OperationalStatus
from app.main import app
from app.models import Assessment, Evidence, Requirement
from app.services.metrics import calculate_submission_coverage, derive_operational_status
from fastapi.testclient import TestClient
from sqlalchemy import select


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def reset_demo_state(client: TestClient):
    response = client.post("/api/demo/reset")
    assert response.status_code == 200
    yield
    response = client.post("/api/demo/reset")
    assert response.status_code == 200


def _bid(client: TestClient) -> dict:
    response = client.get(f"/api/bids/{DEMO_BID_ID}")
    assert response.status_code == 200
    return response.json()


def _apply(client: TestClient) -> dict:
    response = client.post(f"/api/demo/bids/{DEMO_BID_ID}/apply-corrigendum")
    assert response.status_code == 200, response.text
    return response.json()


def test_fixture_extraction_preserves_key_requirement_and_source(client: TestClient):
    data = _bid(client)
    assert len(data["requirements"]) == 18
    r17 = next(item for item in data["requirements"] if item["stable_key"] == "R17")
    assert "three personnel" in r17["text"]
    assert r17["source"]["document"].endswith("Technical_Specification.pdf")
    assert r17["source"]["page"] == 17
    assert r17["source"]["section"].startswith("4.3")


def test_initial_operational_feasibility_is_feasible(client: TestClient):
    data = _bid(client)
    assert data["interpretation"] == {
        "mode": "DEMO_FALLBACK",
        "label": "Demo fallback",
        "model_id": None,
        "source": "no_persisted_interpretation",
        "event_id": None,
    }
    r17 = next(item for item in data["requirements"] if item["stable_key"] == "R17")
    assert r17["assessment"] == "SATISFIED"
    assert r17["evidence_count"] == 3
    assert data["metrics"] == {
        "operational_status": "FEASIBLE",
        "previous_operational_status": None,
        "critical_gates_verified": 8,
        "critical_gates_total": 8,
        "submission_coverage": 91,
        "deadline_risk": "LOW",
    }


def test_corrigendum_versions_requirement_without_erasing_history(client: TestClient):
    data = _apply(client)
    r17 = next(item for item in data["requirements"] if item["stable_key"] == "R17")
    assert r17["version"] == 2
    assert [item["version"] for item in r17["history"]] == [2, 1]
    assert r17["history"][1]["assessment"] == "SUPERSEDED"
    with SessionLocal() as session:
        versions = session.scalars(
            select(Requirement).where(Requirement.stable_key == "R17").order_by(Requirement.version)
        ).all()
        assert [version.id for version in versions] == ["REQ-R17-V1", "REQ-R17-V2"]


def test_changed_requirement_is_partial_not_falsely_satisfied(client: TestClient):
    data = _apply(client)
    r17 = next(item for item in data["requirements"] if item["stable_key"] == "R17")
    assert r17["assessment"] == "PARTIAL"
    assert "Only 3" in r17["assessment_reason"]
    assert r17["evidence_count"] == 3


def test_recovery_candidate_retains_evidence_gaps(client: TestClient):
    data = _apply(client)
    candidate = data["recovery_candidate"]
    assert candidate["name"] == "Daniel Tan"
    assert candidate["certification"] == "VERIFIED"
    assert candidate["cv"] == "STALE"
    assert candidate["availability"] == "UNKNOWN"
    assert candidate["can_satisfy_now"] is False


def test_recovery_tasks_and_dependencies_are_created(client: TestClient):
    data = _apply(client)
    recovery = {task["id"]: task for task in data["tasks"] if task["recovery_path"]}
    assert set(recovery) == {
        "TASK-REC-CV",
        "TASK-REC-AVAIL",
        "TASK-REC-PLAN",
        "TASK-REC-RECHECK",
    }
    assert set(recovery["TASK-REC-PLAN"]["depends_on"]) == {
        "TASK-REC-CV",
        "TASK-REC-AVAIL",
    }
    assert recovery["TASK-REC-RECHECK"]["depends_on"] == ["TASK-REC-PLAN"]


def test_corrigendum_changes_operational_status_to_recoverable(client: TestClient):
    data = _apply(client)
    assert data["metrics"]["previous_operational_status"] == "FEASIBLE"
    assert data["metrics"]["operational_status"] == "RECOVERABLE"
    assert data["metrics"]["critical_gates_verified"] == 7
    assert data["metrics"]["critical_gates_total"] == 8
    assert data["latest_change"]["impact"] == {
        "critical_gates_broken": 1,
        "assessments_superseded": 1,
        "recovery_paths_found": 1,
    }


def test_submission_coverage_is_deterministic(client: TestClient):
    data = _bid(client)
    with SessionLocal() as session:
        tender = session.get(__import__("app.models", fromlist=["Tender"]).Tender, DEMO_BID_ID)
        first = calculate_submission_coverage(session, tender)
        second = calculate_submission_coverage(session, tender)
    assert first == second == data["metrics"]["submission_coverage"]


def test_calculation_traces_match_persisted_state(client: TestClient):
    data = _bid(client)
    calculations = data["calculations"]
    assert calculations["operational_feasibility"]["matches_persisted_value"] is True
    assert calculations["submission_coverage"]["matches_persisted_value"] is True
    assert calculations["deadline_risk"]["matches_persisted_value"] is True
    coverage = calculations["submission_coverage"]
    assert coverage["components"]["requirements"]["completed_units"] == 30
    assert coverage["components"]["requirements"]["total_units"] == 31
    assert coverage["components"]["evidence"]["completed_units"] == 18
    assert coverage["components"]["evidence"]["total_units"] == 20
    assert coverage["components"]["tasks"]["completed_units"] == 8
    assert coverage["components"]["tasks"]["total_units"] == 10
    assert coverage["raw_percent"] == pytest.approx(91.3871, abs=0.001)
    assert coverage["display_percent"] == 91


def test_selectable_blocked_fixture(client: TestClient):
    response = client.post("/api/demo/fixtures/blocked-no-fourth-engineer")
    assert response.status_code == 200
    data = response.json()
    assert data["bid"]["fixture_id"] == "blocked-no-fourth-engineer"
    assert data["metrics"]["operational_status"] == "BLOCKED"
    assert data["latest_change"]["impact"]["recovery_paths_found"] == 0
    assert data["recovery_candidate"] is None
    unresolved = data["calculations"]["operational_feasibility"]["unresolved"]
    assert unresolved == [
        {
            "requirement_id": "REQ-R17-V2",
            "stable_key": "R17",
            "assessment_status": "UNMET",
            "recovery_task_ids": [],
            "recovery_viable": False,
        }
    ]


def test_selectable_uncertain_fixture(client: TestClient):
    response = client.post("/api/demo/fixtures/uncertain-ambiguous-clause")
    assert response.status_code == 200
    data = response.json()
    assert data["bid"]["fixture_id"] == "uncertain-ambiguous-clause"
    assert data["metrics"]["operational_status"] == "UNCERTAIN"
    assert data["metrics"]["critical_gates_verified"] == 8
    assert data["metrics"]["critical_gates_total"] == 9
    r19 = next(item for item in data["requirements"] if item["stable_key"] == "R19")
    assert r19["assessment"] == "UNCERTAIN"
    assert "Human clarification is required" in r19["assessment_reason"]
    assert r19["source"]["snippet"] in r19["text"]


def test_main_fixture_remains_original_start_state(client: TestClient):
    response = client.post("/api/demo/fixtures/main-corrigendum")
    assert response.status_code == 200
    data = response.json()
    assert data["bid"]["fixture_id"] == "main-corrigendum"
    assert data["latest_change"] is None
    assert data["metrics"]["operational_status"] == "FEASIBLE"
    assert data["metrics"]["critical_gates_verified"] == 8
    assert data["metrics"]["critical_gates_total"] == 8
    assert data["metrics"]["submission_coverage"] == 91
    assert data["metrics"]["deadline_risk"] == "LOW"


def test_no_fourth_engineer_produces_blocked_state(client: TestClient):
    with SessionLocal() as session:
        evidence = session.get(Evidence, "EV-D-CERT")
        evidence.verification_status = "STALE"
        session.commit()
    data = _apply(client)
    assert data["metrics"]["operational_status"] == "BLOCKED"
    assert not [task for task in data["tasks"] if task["recovery_path"]]


def test_ambiguous_mandatory_clause_produces_uncertain_state(client: TestClient):
    with SessionLocal() as session:
        requirement = Requirement(
            id="REQ-R19-V1",
            stable_key="R19",
            tender_id=DEMO_BID_ID,
            version=1,
            text="The supplier should provide adequate suitably qualified standby resources.",
            requirement_type="MANPOWER",
            gate_type="MANDATORY",
            source_document_id="DOC-TECH",
            source_page=19,
            source_section="4.8",
            source_snippet="Adequate suitably qualified standby resources.",
            rule_config={"kind": "ambiguous"},
            created_at=datetime(2026, 8, 21, 5, 0),
        )
        assessment = Assessment(
            id="ASM-R19-V1",
            requirement_id=requirement.id,
            requirement_version=1,
            status="UNCERTAIN",
            evidence_ids=[],
            reason_summary="The number and qualification threshold are ambiguous; human clarification is required.",
            assessed_at=datetime(2026, 8, 21, 5, 0),
            assessment_method="HYBRID",
        )
        session.add_all([requirement, assessment])
        session.commit()
        tender = requirement.tender_id
        from app.models import Tender

        result = derive_operational_status(session, session.get(Tender, tender))
    assert result == OperationalStatus.UNCERTAIN


def test_duplicate_corrigendum_is_rejected(client: TestClient):
    _apply(client)
    response = client.post(f"/api/demo/bids/{DEMO_BID_ID}/apply-corrigendum")
    assert response.status_code == 409
    assert "already been applied" in response.json()["detail"]
