from copy import deepcopy

import pytest
from app.database import SessionLocal
from app.demo.seed import DEMO_BID_ID
from app.main import app
from app.models import Requirement
from fastapi.testclient import TestClient
from sqlalchemy import select


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        response = test_client.post("/api/demo/reset")
        assert response.status_code == 200
        yield test_client
        test_client.post("/api/demo/reset")


def _simulation_payload(primary_count: int = 3) -> dict:
    return {
        "scenario_label": "Shared specialist capacity",
        "capabilities": [
            {
                "capability": "CERTIFIED_SPECIALIST",
                "label": "Certified specialists",
                "proven_count": 3,
                "potential_count": 4,
                "provenance": "Three verified records and one candidate with an evidence gap.",
            }
        ],
        "opportunities": [
            {
                "id": "BID-A",
                "title": "Primary managed service",
                "agency": "Example agency A",
                "reference_number": "EX/A/001",
                "stage": "DELIVERY_COMMITMENT",
                "demands": [
                    {
                        "capability": "CERTIFIED_SPECIALIST",
                        "count": primary_count,
                        "starts_at": "2026-09-01T00:00:00",
                        "ends_at": "2026-12-01T00:00:00",
                        "source": "Structured requirement A17",
                    }
                ],
            },
            {
                "id": "BID-B",
                "title": "Existing delivery commitment",
                "agency": "Example agency B",
                "reference_number": "EX/B/002",
                "stage": "ACTIVE_BID",
                "demands": [
                    {
                        "capability": "CERTIFIED_SPECIALIST",
                        "count": 1,
                        "starts_at": "2026-10-01T00:00:00",
                        "ends_at": "2027-01-01T00:00:00",
                        "source": "Existing staffing plan",
                    }
                ],
            },
        ],
    }


def test_portfolio_simulation_detects_recoverable_evidence_gap(client: TestClient):
    response = client.post("/api/portfolio/simulate", json=_simulation_payload())
    assert response.status_code == 200
    data = response.json()
    assert data["state"] == "RECOVERABLE"
    capacity = data["capabilities"][0]
    assert capacity["peak_demand"] == 4
    assert capacity["evidence_gap"] == 1
    assert capacity["shortfall"] == 0


def test_portfolio_simulation_detects_hard_cross_bid_collision(client: TestClient):
    response = client.post("/api/portfolio/simulate", json=_simulation_payload(primary_count=4))
    assert response.status_code == 200
    data = response.json()
    assert data["state"] == "BLOCKED"
    capacity = data["capabilities"][0]
    assert capacity["peak_demand"] == 5
    assert capacity["potential_count"] == 4
    assert capacity["shortfall"] == 1
    assert {route["route"] for route in data["routes"]} >= {"WALK_AWAY", "PARTNER"}
    partner = next(route for route in data["routes"] if route["route"] == "PARTNER")
    assert partner["resulting_state"] == "UNCERTAIN"
    assert partner["requires_human_decision"] is True
    roadmap = data["capability_roadmap"]
    assert [item["gap_type"] for item in roadmap] == [
        "ADDITIONAL_CAPACITY_REQUIRED",
        "EVIDENCE_OR_AVAILABILITY",
    ]
    assert [item["priority"] for item in roadmap] == [1, 2]
    for item in roadmap:
        assert item["opportunity_ids"] == ["BID-A", "BID-B"]
        assert item["opportunities_affected"] == 2
        assert item["requirement_count"] == 2
        assert item["earliest_window_start"] == "2026-09-01T00:00:00"
        assert item["known_gap"] == 1


def test_unknown_mandatory_count_fails_closed_as_uncertain(client: TestClient):
    payload = _simulation_payload()
    payload["opportunities"][0]["demands"][0]["count"] = None
    response = client.post("/api/portfolio/simulate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["state"] == "UNCERTAIN"
    assert data["capabilities"][0]["peak_demand"] is None
    assert data["capabilities"][0]["minimum_peak_demand"] == 2


def test_unknown_count_outside_peak_still_fails_closed(client: TestClient):
    payload = _simulation_payload(primary_count=3)
    payload["capabilities"][0]["proven_count"] = 4
    payload["capabilities"][0]["potential_count"] = 4
    companion = payload["opportunities"][1]["demands"][0]
    companion["count"] = None
    companion["starts_at"] = "2027-01-01T00:00:00"
    companion["ends_at"] = "2027-02-01T00:00:00"

    response = client.post("/api/portfolio/simulate", json=payload)
    assert response.status_code == 200
    data = response.json()
    capacity = data["capabilities"][0]
    assert data["state"] == "UNCERTAIN"
    assert capacity["peak_demand"] is None
    assert capacity["minimum_peak_demand"] == 3
    assert capacity["uncertain_demand"] is True
    assert capacity["uncertain_opportunity_ids"] == ["BID-B"]


def test_unknown_count_uses_positive_lower_bound_before_uncertain_precedence(
    client: TestClient,
):
    payload = _simulation_payload(primary_count=3)
    payload["capabilities"][0]["potential_count"] = 3
    payload["opportunities"][1]["demands"][0]["count"] = None

    response = client.post("/api/portfolio/simulate", json=payload)
    assert response.status_code == 200
    data = response.json()
    capacity = data["capabilities"][0]
    assert data["state"] == "BLOCKED"
    assert capacity["peak_demand"] is None
    assert capacity["minimum_peak_demand"] == 4
    assert capacity["shortfall"] is None
    assert capacity["minimum_shortfall"] == 1


def test_non_overlapping_demands_are_not_double_counted(client: TestClient):
    payload = _simulation_payload(primary_count=3)
    payload["opportunities"][1]["demands"][0]["starts_at"] = "2026-12-01T00:00:00"
    response = client.post("/api/portfolio/simulate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["state"] == "FEASIBLE"
    assert data["capabilities"][0]["peak_demand"] == 3


def test_roadmap_scopes_provenance_to_the_constrained_peak(client: TestClient):
    payload = _simulation_payload(primary_count=4)
    payload["opportunities"].append(
        {
            "id": "BID-C",
            "title": "Earlier completed engagement",
            "agency": "Example agency C",
            "reference_number": "EX/C/003",
            "stage": "DELIVERY_COMMITMENT",
            "demands": [
                {
                    "capability": "CERTIFIED_SPECIALIST",
                    "count": 1,
                    "starts_at": "2026-01-01T00:00:00",
                    "ends_at": "2026-02-01T00:00:00",
                    "source": "Completed staffing plan",
                }
            ],
        }
    )

    response = client.post("/api/portfolio/simulate", json=payload)
    assert response.status_code == 200
    roadmap = response.json()["capability_roadmap"]
    assert len(roadmap) == 2
    for item in roadmap:
        assert item["opportunity_ids"] == ["BID-A", "BID-B"]
        assert item["opportunities_affected"] == 2
        assert item["requirement_count"] == 2
        assert item["earliest_window_start"] == "2026-09-01T00:00:00"
        assert "Completed staffing plan" not in item["sources"]


def test_roadmap_includes_all_disjoint_windows_tied_at_peak(client: TestClient):
    payload = _simulation_payload(primary_count=4)
    payload["opportunities"].append(
        {
            "id": "BID-C",
            "title": "Earlier constrained engagement",
            "agency": "Example agency C",
            "reference_number": "EX/C/003",
            "stage": "DELIVERY_COMMITMENT",
            "demands": [
                {
                    "capability": "CERTIFIED_SPECIALIST",
                    "count": 5,
                    "starts_at": "2026-01-01T00:00:00",
                    "ends_at": "2026-02-01T00:00:00",
                    "source": "Earlier constrained staffing plan",
                }
            ],
        }
    )

    response = client.post("/api/portfolio/simulate", json=payload)
    assert response.status_code == 200
    data = response.json()
    capacity = data["capabilities"][0]
    assert capacity["peak_demand"] == 5
    assert capacity["active_opportunity_ids"] == ["BID-C"]
    assert len(capacity["peak_windows"]) == 2
    for item in data["capability_roadmap"]:
        assert item["opportunity_ids"] == ["BID-A", "BID-B", "BID-C"]
        assert item["opportunities_affected"] == 3
        assert item["requirement_count"] == 3
        assert item["earliest_window_start"] == "2026-01-01T00:00:00"
        assert "Earlier constrained staffing plan" in item["sources"]


def test_known_blocker_keeps_roadmap_when_other_demand_is_unknown(client: TestClient):
    payload = _simulation_payload(primary_count=5)
    companion = payload["opportunities"][1]["demands"][0]
    companion["count"] = None
    companion["starts_at"] = "2027-01-01T00:00:00"
    companion["ends_at"] = "2027-02-01T00:00:00"

    response = client.post("/api/portfolio/simulate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["state"] == "BLOCKED"
    capacity = data["capabilities"][0]
    assert capacity["peak_demand"] is None
    assert capacity["minimum_peak_demand"] == 5
    assert capacity["minimum_shortfall"] == 1
    additional_capacity = next(
        item
        for item in data["capability_roadmap"]
        if item["gap_type"] == "ADDITIONAL_CAPACITY_REQUIRED"
    )
    assert additional_capacity["known_gap"] == 1
    assert additional_capacity["opportunity_ids"] == ["BID-A"]
    assert additional_capacity["sources"] == ["Structured requirement A17"]


def test_mixed_timezone_offsets_are_normalised_before_interval_math(client: TestClient):
    payload = _simulation_payload(primary_count=4)
    payload["opportunities"][0]["demands"][0]["ends_at"] = "2026-12-01T00:00:00Z"
    companion = payload["opportunities"][1]["demands"][0]
    companion["starts_at"] = "2026-10-01T08:00:00+08:00"
    companion["ends_at"] = "2027-01-01T00:00:00Z"

    response = client.post("/api/portfolio/simulate", json=payload)
    assert response.status_code == 200
    capacity = response.json()["capabilities"][0]
    assert capacity["peak_demand"] == 5
    assert capacity["window_start"] == "2026-10-01T00:00:00"


def test_same_input_produces_identical_stably_ordered_output(client: TestClient):
    payload = _simulation_payload(primary_count=4)
    first = client.post("/api/portfolio/simulate", json=payload)
    second = client.post("/api/portfolio/simulate", json=payload)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["capabilities"][0]["active_opportunity_ids"] == ["BID-A", "BID-B"]


def test_strict_schema_rejects_unrecognised_inputs(client: TestClient):
    payload = _simulation_payload()
    payload["estimated_value_sgd"] = 999999
    response = client.post("/api/portfolio/simulate", json=payload)
    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "extra_forbidden"


def test_opportunity_ids_must_be_unique_ignoring_case(client: TestClient):
    payload = _simulation_payload()
    payload["opportunities"][1]["id"] = "bid-a"
    response = client.post("/api/portfolio/simulate", json=payload)
    assert response.status_code == 422
    assert "unique ignoring case" in response.json()["detail"][0]["msg"]


def test_simulation_is_read_only_for_the_hero_bid(client: TestClient):
    before = client.get(f"/api/bids/{DEMO_BID_ID}").json()
    response = client.post("/api/portfolio/simulate", json=_simulation_payload(primary_count=4))
    assert response.status_code == 200
    after = client.get(f"/api/bids/{DEMO_BID_ID}").json()
    assert after == before


def test_invalid_or_unconfigured_capability_is_rejected(client: TestClient):
    payload = deepcopy(_simulation_payload())
    payload["opportunities"][0]["demands"][0]["capability"] = "UNCONFIGURED"
    response = client.post("/api/portfolio/simulate", json=payload)
    assert response.status_code == 422
    assert "No capability pool is configured" in response.json()["detail"][0]["msg"]


def test_portfolio_response_has_a_typed_openapi_contract(client: TestClient):
    schema = client.get("/openapi.json").json()
    response_schema = schema["paths"]["/api/portfolio/simulate"]["post"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]
    assert response_schema["$ref"].endswith("/PortfolioSimulationResponse")


def test_main_hero_has_no_portfolio_claim_before_change(client: TestClient):
    data = client.get(f"/api/bids/{DEMO_BID_ID}").json()
    assert data["portfolio_impact"] is None
    assert data["metrics"]["operational_status"] == "FEASIBLE"


def test_corrigendum_exposes_simulation_without_changing_bid_status(client: TestClient):
    response = client.post(f"/api/demo/bids/{DEMO_BID_ID}/apply-corrigendum")
    assert response.status_code == 200
    data = response.json()
    assert data["metrics"]["operational_status"] == "RECOVERABLE"
    impact = data["portfolio_impact"]
    assert impact["mode"] == "SIMULATION_ONLY"
    assert impact["synthetic"] is True
    assert impact["before_state"] == "RECOVERABLE"
    assert impact["after_state"] == "BLOCKED"
    assert impact["capacity"] == {
        "capability": "CISSP delivery personnel",
        "unit": "concurrent CISSP assignments",
        "proven_now": 3,
        "potential_after_recovery": 4,
        "concurrent_required": 5,
        "shortfall": 1,
        "window_start": "2026-10-01T00:00:00",
        "window_end": "2026-12-01T00:00:00",
    }
    assert {route["action"] for route in impact["routes"]} == {
        "RECOVER",
        "WALK_AWAY",
        "PARTNER",
    }
    assert data["metrics"]["critical_gates_verified"] == 7


def test_demo_projection_requires_the_exact_canonical_three_to_four_transition(
    client: TestClient,
):
    response = client.post(f"/api/demo/bids/{DEMO_BID_ID}/apply-corrigendum")
    assert response.status_code == 200
    assert response.json()["portfolio_impact"] is not None

    with SessionLocal() as session:
        previous = session.scalar(
            select(Requirement).where(
                Requirement.tender_id == DEMO_BID_ID,
                Requirement.stable_key == "R17",
                Requirement.version == 1,
            )
        )
        assert previous is not None
        previous.rule_config = {**previous.rule_config, "minimum_count": 2}
        session.commit()

    data = client.get(f"/api/bids/{DEMO_BID_ID}").json()
    assert data["latest_change"]["old_count"] == 2
    assert data["portfolio_impact"] is None
