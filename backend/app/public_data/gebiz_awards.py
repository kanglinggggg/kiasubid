import json
import statistics
from datetime import UTC, datetime

import httpx

from app.public_data.schemas import (
    AnnualAwardPattern,
    AwardContextResponse,
    AwardIntelligence,
    AwardRecord,
    AwardSummary,
    PublicDataProvenance,
    SupplierPattern,
)

DATASET_ID = "d_acde1106003906a75c3fa052592f2fcb"
DATASET_TITLE = "Government Procurement via GeBIZ"
DATASET_URL = f"https://data.gov.sg/datasets/{DATASET_ID}/view"
SEARCH_URL = "https://data.gov.sg/api/action/datastore_search"

# Small source-preserving fallback retrieved from the official dataset on 8 September 2026.
# It keeps the product demonstrable during API outages and is never presented as a full dataset.
CACHED_PUBLIC_ROWS = (
    {
        "tender_no": "CAA000ETT21000061",
        "tender_description": "Provision of Cybersecurity Incident Response Support Services",
        "agency": "Civil Aviation Authority of Singapore",
        "award_date": "17/2/2022",
        "tender_detail_status": "Awarded to Suppliers",
        "supplier_name": "ENSIGN INFOSECURITY (SMARTTECH) PTE. LTD.",
        "awarded_amt": "200000",
    },
    {
        "tender_no": "CAA000ETT25000003",
        "tender_description": (
            "Provision of professional services to conduct cybersecurity table-top exercise "
            "for aviation sector"
        ),
        "agency": "Civil Aviation Authority of Singapore",
        "award_date": "24/3/2025",
        "tender_detail_status": "Awarded to Suppliers",
        "supplier_name": "ENSIGN INFOSECURITY (SMARTTECH) PTE. LTD.",
        "awarded_amt": "294600",
    },
    {
        "tender_no": "CAA000ETT25000033",
        "tender_description": "Provision of Cybersecurity Incident Response Support Services",
        "agency": "Civil Aviation Authority of Singapore",
        "award_date": "16/9/2025",
        "tender_detail_status": "Awarded to Suppliers",
        "supplier_name": "ENSIGN INFOSECURITY (SMARTTECH) PTE. LTD.",
        "awarded_amt": "114000",
    },
    {
        "tender_no": "DST000ETT21000020",
        "tender_description": "Provision of Cybersecurity Training and Competition",
        "agency": "Defence Science and Technology Agency",
        "award_date": "7/3/2022",
        "tender_detail_status": "Awarded to Suppliers",
        "supplier_name": "ATHENA DYNAMICS PTE. LTD.",
        "awarded_amt": "544000",
    },
    {
        "tender_no": "DST000ETT24000002",
        "tender_description": "Provision of Cybersecurity Training and Competition",
        "agency": "Defence Science and Technology Agency",
        "award_date": "4/4/2024",
        "tender_detail_status": "Awarded to Suppliers",
        "supplier_name": "ATHENA DYNAMICS PTE. LTD.",
        "awarded_amt": "689992",
    },
    {
        "tender_no": "EMA000ETT22000017",
        "tender_description": (
            "Provision of cybersecurity and audit services in accordance to CSA SBD "
            "framework for Energy Management Systems upgrade project"
        ),
        "agency": "Energy Market Authority of Singapore",
        "award_date": "7/12/2022",
        "tender_detail_status": "Awarded to Suppliers",
        "supplier_name": "BOOZ ALLEN HAMILTON INTERNATIONAL PTE. LTD.",
        "awarded_amt": "659997.75",
    },
    {
        "tender_no": "EMA000ETT25000022",
        "tender_description": (
            "Provision of cybersecurity and audit services for Cybersecurity Operation Centre"
        ),
        "agency": "Energy Market Authority of Singapore",
        "award_date": "15/9/2025",
        "tender_detail_status": "Awarded to Suppliers",
        "supplier_name": "BOOZ ALLEN HAMILTON INTERNATIONAL PTE. LTD.",
        "awarded_amt": "731687.81",
    },
    {
        "tender_no": "EMA000ETT26000001",
        "tender_description": "Provision of services for cybersecurity risk assessment for 3 years",
        "agency": "Energy Market Authority of Singapore",
        "award_date": "27/2/2026",
        "tender_detail_status": "Awarded to Suppliers",
        "supplier_name": "PULSESECURE PTE. LTD.",
        "awarded_amt": "80000",
    },
)


def _percentile(values: list[float], proportion: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * proportion
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _date_sort_key(record: AwardRecord) -> datetime:
    try:
        return datetime.strptime(record.award_date, "%d/%m/%Y")
    except ValueError:
        return datetime.min


def _clean_rows(
    rows: list[dict] | tuple[dict, ...], *, query: str, agency: str | None
) -> tuple[list[AwardRecord], int]:
    records: list[AwardRecord] = []
    excluded = 0
    query_terms = [term.casefold() for term in query.split() if term]
    for row in rows:
        description = str(row.get("tender_description") or "").strip()
        row_agency = str(row.get("agency") or "").strip()
        if query_terms and not all(term in description.casefold() for term in query_terms):
            continue
        if agency and agency.casefold() not in row_agency.casefold():
            continue
        try:
            amount = float(row.get("awarded_amt") or 0)
        except (TypeError, ValueError):
            excluded += 1
            continue
        if row.get("tender_detail_status") != "Awarded to Suppliers" or amount <= 1:
            excluded += 1
            continue
        try:
            records.append(
                AwardRecord(
                    tender_no=str(row.get("tender_no") or "").strip(),
                    tender_description=description,
                    agency=row_agency,
                    award_date=str(row.get("award_date") or "").strip(),
                    supplier_name=str(row.get("supplier_name") or "").strip(),
                    awarded_amt_sgd=round(amount, 2),
                )
            )
        except ValueError:
            excluded += 1
    records.sort(key=_date_sort_key, reverse=True)
    return records, excluded


def _summary(records: list[AwardRecord]) -> AwardSummary:
    values = [record.awarded_amt_sgd for record in records]
    return AwardSummary(
        sample_count=len(records),
        distinct_tenders=len({record.tender_no for record in records}),
        median_sgd=round(float(statistics.median(values)), 2) if values else None,
        lower_quartile_sgd=(
            round(value, 2) if (value := _percentile(values, 0.25)) is not None else None
        ),
        upper_quartile_sgd=(
            round(value, 2) if (value := _percentile(values, 0.75)) is not None else None
        ),
        minimum_sgd=round(min(values), 2) if values else None,
        maximum_sgd=round(max(values), 2) if values else None,
    )


def _provenance(status: str, retrieved_at: str) -> PublicDataProvenance:
    return PublicDataProvenance(
        status=status,  # type: ignore[arg-type]
        publisher="Ministry of Finance via data.gov.sg",
        dataset_title=DATASET_TITLE,
        dataset_id=DATASET_ID,
        source_url=DATASET_URL,
        retrieved_at=retrieved_at,
        coverage="April 2021 to March 2026",
        methodology=[
            "Description keyword filter applied to returned rows.",
            "Only exact 'Awarded to Suppliers' rows with amount above S$1 are retained.",
            "Median and quartiles describe the retained sample; scope is not normalised.",
        ],
        limitation=(
            "The dataset contains awarded suppliers and amounts, not losing bids, evaluation "
            "weights, bidder counts or win probabilities."
        ),
    )


def _intelligence(records: list[AwardRecord]) -> AwardIntelligence:
    if not records:
        return AwardIntelligence(
            sample_strength="NO_SAMPLE",
            date_start=None,
            date_end=None,
            supplier_count=0,
            recurring_supplier_count=0,
            price_dispersion_percent=None,
            top_suppliers=[],
            annual_patterns=[],
            observations=["No retained supplier-award row matched this source query."],
            boundary=(
                "No market or agency behaviour can be inferred without comparable retained rows."
            ),
        )

    amounts = [record.awarded_amt_sgd for record in records]
    total_value = sum(amounts)
    supplier_values: dict[str, float] = {}
    supplier_counts: dict[str, int] = {}
    for record in records:
        supplier_values[record.supplier_name] = (
            supplier_values.get(record.supplier_name, 0) + record.awarded_amt_sgd
        )
        supplier_counts[record.supplier_name] = supplier_counts.get(record.supplier_name, 0) + 1

    ranked_suppliers = sorted(
        supplier_counts,
        key=lambda supplier: (
            supplier_counts[supplier],
            supplier_values[supplier],
            supplier,
        ),
        reverse=True,
    )
    top_suppliers = [
        SupplierPattern(
            supplier_name=supplier,
            award_rows=supplier_counts[supplier],
            total_awarded_sgd=round(supplier_values[supplier], 2),
            row_share_percent=round(supplier_counts[supplier] / len(records) * 100, 1),
            value_share_percent=round(supplier_values[supplier] / total_value * 100, 1),
        )
        for supplier in ranked_suppliers[:5]
    ]

    dated_records: list[tuple[datetime, AwardRecord]] = []
    annual_values: dict[int, list[float]] = {}
    for record in records:
        parsed = _date_sort_key(record)
        if parsed == datetime.min:
            continue
        dated_records.append((parsed, record))
        annual_values.setdefault(parsed.year, []).append(record.awarded_amt_sgd)
    annual_patterns = [
        AnnualAwardPattern(
            year=year,
            award_rows=len(values),
            median_sgd=round(float(statistics.median(values)), 2),
            total_awarded_sgd=round(sum(values), 2),
        )
        for year, values in sorted(annual_values.items())
    ]

    median = float(statistics.median(amounts))
    lower = _percentile(amounts, 0.25)
    upper = _percentile(amounts, 0.75)
    dispersion = (
        round((upper - lower) / median * 100, 1)
        if median and lower is not None and upper is not None
        else None
    )
    recurring = sum(count > 1 for count in supplier_counts.values())
    strength = "DIRECTIONAL" if len(records) >= 8 else "THIN"
    observations = [
        (
            f"The retained sample contains {len(records)} supplier-award row(s) across "
            f"{len({record.tender_no for record in records})} distinct tender(s)."
        ),
        (
            f"{recurring} supplier(s) appear more than once in this query result."
            if recurring
            else "No supplier repeats in the retained rows for this query."
        ),
    ]
    leader = top_suppliers[0]
    observations.append(
        f"The most frequent supplier appears in {leader.award_rows} row(s), "
        f"or {leader.row_share_percent:.1f}% of retained rows."
    )
    if annual_patterns:
        observations.append(
            f"Retained dated rows span {annual_patterns[0].year} to {annual_patterns[-1].year}."
        )

    return AwardIntelligence(
        sample_strength=strength,
        date_start=(
            min(item[0] for item in dated_records).strftime("%d/%m/%Y")
            if dated_records
            else None
        ),
        date_end=(
            max(item[0] for item in dated_records).strftime("%d/%m/%Y")
            if dated_records
            else None
        ),
        supplier_count=len(supplier_counts),
        recurring_supplier_count=recurring,
        price_dispersion_percent=dispersion,
        top_suppliers=top_suppliers,
        annual_patterns=annual_patterns,
        observations=observations,
        boundary=(
            "These are descriptive patterns in the returned public rows. The data does not reveal "
            "losing bids or evaluation weights and is not normalised for tender scope, so it cannot "
            "support a win probability or recommended bid price."
        ),
    )


def get_award_context(
    query: str,
    agency: str | None = None,
    *,
    client: httpx.Client | None = None,
) -> AwardContextResponse:
    normalised_query = " ".join(query.split())
    normalised_agency = " ".join(agency.split()) if agency else None
    owns_client = client is None
    http_client = client or httpx.Client(timeout=httpx.Timeout(6.0, connect=3.0))
    retrieved_at = datetime.now(UTC).isoformat()
    try:
        response = http_client.get(
            SEARCH_URL,
            params={
                "resource_id": DATASET_ID,
                "limit": 100,
                "q": json.dumps({"tender_description": normalised_query}),
            },
        )
        response.raise_for_status()
        payload = response.json()
        result = payload.get("result", {})
        raw_rows = result.get("records", [])
        if not isinstance(raw_rows, list):
            raise ValueError("Unexpected data.gov.sg response shape")
        records, excluded = _clean_rows(
            raw_rows,
            query=normalised_query,
            agency=normalised_agency,
        )
        source_total = int(result.get("total") or len(raw_rows))
        provenance = _provenance("LIVE_PUBLIC", retrieved_at)
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        records, excluded = _clean_rows(
            CACHED_PUBLIC_ROWS,
            query=normalised_query,
            agency=normalised_agency,
        )
        source_total = len(records) + excluded
        provenance = _provenance("CACHED_PUBLIC", "2026-09-08T00:00:00+00:00")
    finally:
        if owns_client:
            http_client.close()

    return AwardContextResponse(
        query=normalised_query,
        agency=normalised_agency,
        source_total_matches=source_total,
        excluded_rows=excluded,
        summary=_summary(records),
        records=records[:50],
        provenance=provenance,
        intelligence=_intelligence(records),
    )
