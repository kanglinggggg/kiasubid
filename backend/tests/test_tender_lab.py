from io import BytesIO

import pytest
from app.demo.seed import DEMO_BID_ID
from app.main import app
from fastapi.testclient import TestClient
from pypdf import PdfWriter


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def reset_demo_state(client: TestClient):
    response = client.post("/api/demo/reset")
    assert response.status_code == 200
    yield
    client.post("/api/demo/reset")


def _sample(client: TestClient, mode: str = "sme") -> dict:
    response = client.get(f"/api/tender-lab/sample/{mode}")
    assert response.status_code == 200, response.text
    return response.json()


def test_sme_workflow_is_source_backed_and_bounded(client: TestClient):
    response = client.post("/api/tender-lab/analyze", json=_sample(client))
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["mode"] == "SME"
    assert data["source_type"] == "SYNTHETIC_SAMPLE"
    assert data["startup_coach"] is None
    assert data["pricing"]["confidence"] == "USER_SUPPLIED_COMPARABLES"
    assert data["pricing"]["comparable_count"] == 5
    assert data["pricing"]["gross_margin_sgd"] == 95_000
    assert data["pricing"]["gross_margin_percent"] == 21.1
    assert {item["status"] for item in data["policy_checks"]} >= {"SUPPORTED", "GAP"}
    assert all(item["tender_source"]["location"].startswith("Page ") for item in data["policy_checks"])
    official = [
        item for item in data["policy_checks"]
        if item["basis"] == "TENDER_TRIGGERED_OFFICIAL_CONTEXT"
    ]
    assert {item["id"] for item in official} >= {
        "POLICY-IM8",
        "POLICY-MTCS",
        "POLICY-PW-MARK",
        "POLICY-SUSTAINABILITY",
    }
    assert all(item["official_source"]["url"].startswith("https://") for item in official)
    assert all(item["official_source"]["limitation"] for item in official)
    missing_checks = [item for item in data["policy_checks"] if item["proposal_evidence"] is None]
    assert missing_checks
    assert all(item["remediation"] is not None for item in missing_checks)
    assert all("[Describe" in item["remediation"]["draft"] for item in missing_checks)
    assert all(item["remediation"]["evidence_needed"] for item in missing_checks)
    assert all(
        "does not establish compliance" in item["remediation"]["boundary"]
        for item in missing_checks
    )
    assert all(
        item["remediation"] is None
        for item in data["policy_checks"]
        if item["proposal_evidence"] is not None
    )
    assert len(data["clarification_questions"]) >= 2
    assert len(data["milestones"]) == 3
    assert data["calendar_ics"].startswith("BEGIN:VCALENDAR\r\n")
    assert "win-probability" in data["pricing"]["boundary"]
    assert all(route["simulation_only"] is True for route in data["strategy_routes"])
    assert all(route["human_decision_required"] is True for route in data["strategy_routes"])
    assert "win_probability" not in response.text.casefold()


def test_startup_workflow_builds_critique_without_commercial_prediction(client: TestClient):
    response = client.post("/api/tender-lab/analyze", json=_sample(client, "startup"))
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["mode"] == "STARTUP"
    assert data["pricing"] is None
    assert data["startup_coach"] is not None
    assert len(data["startup_coach"]["sections"]) == 5
    assert {item["status"] for item in data["startup_coach"]["findings"]} >= {
        "THIN",
        "MISSING",
    }
    assert any(item["id"] == "STARTUP_COACH" for item in data["trace"])
    assert "does not invent" in data["startup_coach"]["boundary"]


def test_public_award_values_keep_their_provenance_label(client: TestClient):
    payload = _sample(client)
    payload["pricing"]["comparables_source"] = "PUBLIC_AWARD_CONTEXT"
    payload["pricing"]["comparables_note"] = (
        "Government Procurement via GeBIZ · cybersecurity · LIVE_PUBLIC"
    )

    response = client.post("/api/tender-lab/analyze", json=payload)

    assert response.status_code == 200, response.text
    assert response.json()["pricing"]["confidence"] == "PUBLIC_AWARD_CONTEXT"


def test_tender_lab_does_not_mutate_operational_bid(client: TestClient):
    before = client.get(f"/api/bids/{DEMO_BID_ID}").json()
    response = client.post("/api/tender-lab/analyze", json=_sample(client))
    assert response.status_code == 200
    after = client.get(f"/api/bids/{DEMO_BID_ID}").json()
    assert after == before


def test_text_document_extraction_adds_page_provenance(client: TestClient):
    response = client.post(
        "/api/tender-lab/extract",
        files={"file": ("tender.txt", b"The supplier shall provide 24x7 support.", "text/plain")},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["filename"] == "tender.txt"
    assert data["page_count"] == 1
    assert data["pages"][0]["page"] == 1
    assert data["text"].startswith("[Page 1]\n")
    assert data["warnings"] == []


def test_company_profile_upload_returns_source_backed_declared_facts(client: TestClient):
    profile = b"""Entity Name: Northstar Digital Pte. Ltd.
Unique Entity Number (UEN): 202612345N
Entity Type: EXEMPT PRIVATE COMPANY LIMITED BY SHARES
Company Status: Live Company
Date of Incorporation: 12 September 2021
Primary SSIC Code: 62011 SOFTWARE DEVELOPMENT
Paid-Up Capital: SGD 250,000.00
"""

    response = client.post(
        "/api/tender-lab/company-profile/extract",
        files={"file": ("acra-profile.txt", profile, "text/plain")},
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["source_type"] == "USER_SUPPLIED"
    assert data["verification_status"] == "NOT_OFFICIALLY_VERIFIED"
    assert data["entity_name"]["value"] == "Northstar Digital Pte. Ltd."
    assert data["uen"]["value"] == "202612345N"
    assert data["primary_ssic"]["value"]["code"] == "62011"
    assert data["paid_up_capital"]["value"] == {
        "amount": "250000.00",
        "currency": "SGD",
    }
    assert data["epu_grade"]["value"] is None
    assert data["epu_grade"]["confidence"] == "REVIEW"


def test_image_only_pdf_fails_closed(client: TestClient):
    stream = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.write(stream)

    response = client.post(
        "/api/tender-lab/extract",
        files={"file": ("scan.pdf", stream.getvalue(), "application/pdf")},
    )
    assert response.status_code == 422
    assert "OCR is not enabled" in response.json()["detail"]


def test_unknown_mode_and_unknown_fields_fail_closed(client: TestClient):
    assert client.get("/api/tender-lab/sample/enterprise").status_code == 404
    payload = _sample(client)
    payload["invented_switch"] = True
    response = client.post("/api/tender-lab/analyze", json=payload)
    assert response.status_code == 422
