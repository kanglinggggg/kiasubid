import httpx
from app.public_data.gebiz_awards import DATASET_ID, get_award_context


def test_live_award_context_filters_placeholder_rows_and_calculates_summary():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["resource_id"] == DATASET_ID
        return httpx.Response(
            200,
            json={
                "success": True,
                "result": {
                    "total": 4,
                    "records": [
                        {
                            "tender_no": "T-1",
                            "tender_description": "Cybersecurity monitoring service",
                            "agency": "Agency A",
                            "award_date": "1/2/2026",
                            "tender_detail_status": "Awarded to Suppliers",
                            "supplier_name": "Supplier One",
                            "awarded_amt": "100000",
                        },
                        {
                            "tender_no": "T-2",
                            "tender_description": "Cybersecurity incident response",
                            "agency": "Agency A",
                            "award_date": "1/3/2026",
                            "tender_detail_status": "Awarded to Suppliers",
                            "supplier_name": "Supplier Two",
                            "awarded_amt": "300000",
                        },
                        {
                            "tender_no": "T-3",
                            "tender_description": "Cybersecurity framework",
                            "agency": "Agency A",
                            "award_date": "1/4/2026",
                            "tender_detail_status": "Awarded by Items",
                            "supplier_name": "Supplier Three",
                            "awarded_amt": "1",
                        },
                        {
                            "tender_no": "T-4",
                            "tender_description": "Office furniture",
                            "agency": "Agency A",
                            "award_date": "1/5/2026",
                            "tender_detail_status": "Awarded to Suppliers",
                            "supplier_name": "Supplier Four",
                            "awarded_amt": "50000",
                        },
                    ],
                },
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = get_award_context("cybersecurity", client=client)

    assert result.provenance.status == "LIVE_PUBLIC"
    assert result.source_total_matches == 4
    assert result.excluded_rows == 1
    assert result.summary.sample_count == 2
    assert result.summary.distinct_tenders == 2
    assert result.summary.median_sgd == 200_000
    assert result.summary.lower_quartile_sgd == 150_000
    assert result.summary.upper_quartile_sgd == 250_000
    assert [record.tender_no for record in result.records] == ["T-2", "T-1"]
    assert result.intelligence.sample_strength == "THIN"
    assert result.intelligence.supplier_count == 2
    assert result.intelligence.recurring_supplier_count == 0
    assert result.intelligence.price_dispersion_percent == 50.0
    assert result.intelligence.annual_patterns[0].year == 2026


def test_award_context_falls_back_to_labelled_public_snapshot():
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = get_award_context("cybersecurity", client=client)

    assert result.provenance.status == "CACHED_PUBLIC"
    assert result.summary.sample_count == 8
    assert result.summary.distinct_tenders == 8
    assert all(record.awarded_amt_sgd > 1 for record in result.records)
    assert "not losing bids" in result.provenance.limitation
    assert result.intelligence.sample_strength == "DIRECTIONAL"
    assert result.intelligence.supplier_count == 4
    assert result.intelligence.recurring_supplier_count == 3
    assert result.intelligence.top_suppliers[0].supplier_name == (
        "ENSIGN INFOSECURITY (SMARTTECH) PTE. LTD."
    )
    assert "cannot support a win probability" in result.intelligence.boundary


def test_award_context_agency_filter_does_not_infer_scoring_preferences():
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = get_award_context(
            "cybersecurity", agency="Energy Market Authority", client=client
        )

    assert result.summary.sample_count == 3
    assert all("Energy Market Authority" in record.agency for record in result.records)
    payload = result.model_dump()
    assert "win_probability" not in payload
    assert "recommended_price" not in payload
    assert result.intelligence.sample_strength == "THIN"
    assert result.intelligence.top_suppliers[0].award_rows == 2
