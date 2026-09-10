from app.main import app
from app.public_data.schemas import AwardContextResponse
from app.tender_lab.partner_router import PartnerRouteRequest, build_partner_route_package
from app.tender_lab.sample import sample_request
from fastapi.testclient import TestClient


def _award_context() -> AwardContextResponse:
    return AwardContextResponse.model_validate(
        {
            "query": "cybersecurity",
            "agency": "Digital Services",
            "source_total_matches": 3,
            "excluded_rows": 0,
            "summary": {
                "sample_count": 3,
                "distinct_tenders": 3,
                "median_sgd": 300000,
                "lower_quartile_sgd": 200000,
                "upper_quartile_sgd": 400000,
                "minimum_sgd": 100000,
                "maximum_sgd": 500000,
            },
            "records": [
                {
                    "tender_no": "T-1",
                    "tender_description": "Cyber monitoring",
                    "agency": "Digital Services Office",
                    "award_date": "01/02/2026",
                    "supplier_name": "Prime Systems Pte. Ltd.",
                    "awarded_amt_sgd": 100000,
                },
                {
                    "tender_no": "T-2",
                    "tender_description": "Cyber response",
                    "agency": "Digital Services Office",
                    "award_date": "01/03/2026",
                    "supplier_name": "Prime Systems Pte. Ltd.",
                    "awarded_amt_sgd": 300000,
                },
                {
                    "tender_no": "T-3",
                    "tender_description": "Security operations",
                    "agency": "Digital Services Office",
                    "award_date": "01/04/2026",
                    "supplier_name": "Second Supplier Pte. Ltd.",
                    "awarded_amt_sgd": 500000,
                },
            ],
            "provenance": {
                "status": "LIVE_PUBLIC",
                "publisher": "Ministry of Finance via data.gov.sg",
                "dataset_title": "Government Procurement via GeBIZ",
                "dataset_id": "dataset-1",
                "source_url": "https://data.gov.sg/datasets/dataset-1/view",
                "retrieved_at": "2026-09-09T00:00:00Z",
                "coverage": "Public sample",
                "methodology": [],
                "limitation": "Awarded rows only.",
            },
            "intelligence": {
                "sample_strength": "THIN",
                "date_start": "01/02/2026",
                "date_end": "01/04/2026",
                "supplier_count": 2,
                "recurring_supplier_count": 1,
                "price_dispersion_percent": 66.7,
                "top_suppliers": [
                    {
                        "supplier_name": "Prime Systems Pte. Ltd.",
                        "award_rows": 2,
                        "total_awarded_sgd": 400000,
                        "row_share_percent": 66.7,
                        "value_share_percent": 44.4,
                    },
                    {
                        "supplier_name": "Second Supplier Pte. Ltd.",
                        "award_rows": 1,
                        "total_awarded_sgd": 500000,
                        "row_share_percent": 33.3,
                        "value_share_percent": 55.6,
                    },
                ],
                "annual_patterns": [],
                "observations": [],
                "boundary": "Descriptive only.",
            },
        }
    )


def test_partner_package_checks_permission_and_keeps_public_suppliers_as_research_leads():
    result = build_partner_route_package(
        PartnerRouteRequest(tender=sample_request("SME"), award_context=_award_context())
    )

    assert result.eligibility == "APPROVAL_REQUIRED"
    assert result.tender_source is not None
    assert result.tender_source.location == "Page 9"
    assert len(result.work_packages) == 3
    assert result.work_packages[0].title == "Managed security monitoring"
    assert [item.supplier_name for item in result.research_leads] == [
        "Prime Systems Pte. Ltd.",
        "Second Supplier Pte. Ltd.",
    ]
    assert all(item.status == "RESEARCH_ONLY" for item in result.research_leads)
    assert "does not show prime status" in result.research_leads[0].public_basis
    assert "Nothing is sent" in result.boundaries[-1]
    assert "[recipient name]" in result.outreach_draft


def test_explicit_subcontracting_prohibition_blocks_route_preparation():
    payload = sample_request("SME").model_copy(
        update={
            "tender_text": (
                "[Page 14]\nThe supplier shall not subcontract any part of the services. "
                "The supplier must provide monthly reports."
            )
        }
    )
    result = build_partner_route_package(
        PartnerRouteRequest(tender=payload, award_context=_award_context())
    )

    assert result.eligibility == "PROHIBITED"
    assert result.next_actions[0].startswith("Stop partner-route preparation")
    assert result.tender_source is not None
    assert "shall not subcontract" in result.tender_source.excerpt


def test_missing_subcontracting_wording_fails_closed():
    payload = sample_request("SME").model_copy(
        update={"tender_text": "[Page 1]\nThe supplier must provide a managed security service."}
    )
    result = build_partner_route_package(
        PartnerRouteRequest(tender=payload, award_context=_award_context())
    )

    assert result.eligibility == "NOT_FOUND_IN_TENDER"
    assert result.tender_source is None
    assert "manual review" in result.eligibility_reason


def test_partner_route_endpoint_returns_strict_package():
    request = PartnerRouteRequest(tender=sample_request("SME"), award_context=_award_context())

    with TestClient(app) as client:
        response = client.post("/api/tender-lab/partner-route", json=request.model_dump())

    assert response.status_code == 200, response.text
    assert response.json()["eligibility"] == "APPROVAL_REQUIRED"
    assert response.json()["research_leads"][0]["status"] == "RESEARCH_ONLY"
