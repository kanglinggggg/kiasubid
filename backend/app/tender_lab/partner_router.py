import re
from collections import Counter
from typing import Literal

from pydantic import Field

from app.public_data.schemas import AwardContextResponse
from app.tender_lab.schemas import SourceReference, StrictModel, TenderLabRequest


class PartnerRouteRequest(StrictModel):
    tender: TenderLabRequest
    award_context: AwardContextResponse


class PartnerWorkPackage(StrictModel):
    id: str
    title: str
    scope: str
    handoffs: list[str]
    exclusions: list[str]
    evidence_needed: list[str]


class PartnerResearchLead(StrictModel):
    supplier_name: str
    status: Literal["RESEARCH_ONLY"] = "RESEARCH_ONLY"
    observed_award_rows: int = Field(ge=1)
    observed_total_awarded_sgd: float = Field(ge=0)
    public_basis: str
    source_url: str
    qualification_questions: list[str]


class PartnerRoutePackage(StrictModel):
    eligibility: Literal[
        "POSSIBLE", "APPROVAL_REQUIRED", "PROHIBITED", "NOT_FOUND_IN_TENDER"
    ]
    eligibility_reason: str
    tender_source: SourceReference | None
    direct_bid_context: str
    work_packages: list[PartnerWorkPackage]
    research_leads: list[PartnerResearchLead]
    capability_statement_draft: str
    outreach_draft: str
    next_actions: list[str]
    boundaries: list[str]


PROHIBITED_PATTERNS = (
    r"\bshall\s+not\s+subcontract\b",
    r"\bmust\s+not\s+subcontract\b",
    r"\bsubcontracting\s+is\s+prohibited\b",
    r"\bno\s+subcontract(?:ing|ors?)\b",
)
APPROVAL_PATTERNS = (
    r"\bprior\s+(?:written\s+)?approval\b.{0,80}\bsubcontract",
    r"\bsubcontract.{0,80}\bprior\s+(?:written\s+)?approval\b",
    r"\bapproval\s+of\s+subcontractors?\b",
    r"\bsubcontractors?\s+(?:must|shall)\s+be\s+approved\b",
)
ALLOWED_PATTERNS = (
    r"\bmay\s+subcontract\b",
    r"\bsubcontracting\s+is\s+permitted\b",
    r"\bapproved\s+subcontractors?\s+may\b",
)


def _normalise(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _tender_sentences(payload: TenderLabRequest) -> list[tuple[str, str]]:
    page = "Supplied text"
    result: list[tuple[str, str]] = []
    for segment in re.split(r"(?=\[Page\s+\d+\])", payload.tender_text, flags=re.I):
        match = re.match(r"\[Page\s+(\d+)\]", segment, flags=re.I)
        if match:
            page = f"Page {match.group(1)}"
            segment = segment[match.end() :]
        for sentence in re.split(r"(?<=[.!?])\s+|\n{2,}", segment):
            cleaned = _normalise(sentence)
            if cleaned:
                result.append((page, cleaned))
    return result


def _eligibility(
    payload: TenderLabRequest,
) -> tuple[str, str, SourceReference | None]:
    sentences = _tender_sentences(payload)
    checks: tuple[tuple[str, tuple[str, ...], str], ...] = (
        (
            "PROHIBITED",
            PROHIBITED_PATTERNS,
            "The supplied tender explicitly prohibits subcontracting. Do not prepare partner outreach unless the buyer formally changes this condition.",
        ),
        (
            "APPROVAL_REQUIRED",
            APPROVAL_PATTERNS,
            "The supplied tender indicates that subcontracting or subcontractors require buyer approval.",
        ),
        (
            "POSSIBLE",
            ALLOWED_PATTERNS,
            "The supplied tender contains wording that permits subcontracting, subject to the exact clause and any stated conditions.",
        ),
    )
    for status, patterns, reason in checks:
        for location, sentence in sentences:
            if any(re.search(pattern, sentence, re.I) for pattern in patterns):
                return (
                    status,
                    reason,
                    SourceReference(
                        source_label=payload.source_label,
                        location=location,
                        excerpt=sentence[:260],
                    ),
                )
    return (
        "NOT_FOUND_IN_TENDER",
        "No subcontracting permission or prohibition was detected in the supplied text. The full tender and contract conditions need manual review.",
        None,
    )


def _work_packages(payload: TenderLabRequest) -> list[PartnerWorkPackage]:
    capabilities: list[str] = []
    seen: set[str] = set()
    for raw in payload.company.capabilities:
        capability = _normalise(raw)
        key = capability.casefold()
        if capability and key not in seen:
            capabilities.append(capability)
            seen.add(key)
        if len(capabilities) == 3:
            break
    if not capabilities:
        capabilities = ["Capability and scope to be confirmed"]
    return [
        PartnerWorkPackage(
            id=f"WP-{index:02d}",
            title=capability,
            scope=(
                f"Deliver a bounded {capability} work package within “{payload.tender_title}”, "
                "subject to an agreed statement of work and acceptance criteria."
            ),
            handoffs=[
                "Prime contractor supplies the approved architecture, interfaces and delivery plan",
                "Company returns implementation evidence and acceptance artefacts for the bounded module",
            ],
            exclusions=[
                "No responsibility for unlisted prime-contractor or buyer obligations",
                "No pricing, staffing or compliance commitment until due diligence is complete",
            ],
            evidence_needed=[
                f"Two relevant delivery examples for {capability}",
                "Named delivery owner and availability",
                "Tender-specific security, quality and acceptance evidence",
            ],
        )
        for index, capability in enumerate(capabilities, start=1)
    ]


def _research_leads(
    payload: TenderLabRequest, context: AwardContextResponse
) -> list[PartnerResearchLead]:
    company_key = payload.company.name.casefold().strip()
    record_counts = Counter(record.supplier_name for record in context.records)
    record_totals: Counter[str] = Counter()
    for record in context.records:
        record_totals[record.supplier_name] += record.awarded_amt_sgd

    ranked_names = [item.supplier_name for item in context.intelligence.top_suppliers]
    ranked_names.extend(record_counts)
    leads: list[PartnerResearchLead] = []
    seen: set[str] = set()
    for supplier_name in ranked_names:
        name = _normalise(supplier_name)
        key = name.casefold()
        if not name or key == company_key or key in seen:
            continue
        seen.add(key)
        top = next(
            (
                item
                for item in context.intelligence.top_suppliers
                if item.supplier_name.casefold() == key
            ),
            None,
        )
        rows = top.award_rows if top else record_counts[name]
        total = top.total_awarded_sgd if top else float(record_totals[name])
        if rows <= 0:
            continue
        leads.append(
            PartnerResearchLead(
                supplier_name=name,
                observed_award_rows=rows,
                observed_total_awarded_sgd=round(total, 2),
                public_basis=(
                    f"Appears in {rows} retained awarded-supplier row(s) for the public query "
                    f"\"{context.query}\". This shows award history only; it does not show prime status, "
                    "current demand or willingness to partner."
                ),
                source_url=context.provenance.source_url,
                qualification_questions=[
                    "Was this supplier the contracting party for work comparable to the current tender?",
                    "Does the tender permit the proposed subcontracting structure?",
                    "Does the supplier have an active vendor or delivery-partner intake process?",
                    "Are scope, liability, data access and payment terms acceptable to both parties?",
                ],
            )
        )
        if len(leads) == 5:
            break
    return leads


def _direct_bid_context(payload: TenderLabRequest) -> str:
    if (
        payload.contract_value_sgd is not None
        and payload.company.max_delivery_value_sgd is not None
        and payload.contract_value_sgd > payload.company.max_delivery_value_sgd
    ):
        return (
            f"The supplied contract value of SGD {payload.contract_value_sgd:,.0f} exceeds the "
            f"company's declared delivery-value limit of SGD {payload.company.max_delivery_value_sgd:,.0f}."
        )
    if payload.company.max_delivery_value_sgd is None:
        return "The company has not supplied an approved delivery-value limit, so direct-bid capacity is unresolved."
    return "The supplied contract value does not exceed the company's declared delivery-value limit; a partner route is an option, not an automatic fallback."


def build_partner_route_package(request: PartnerRouteRequest) -> PartnerRoutePackage:
    payload = request.tender
    eligibility, eligibility_reason, tender_source = _eligibility(payload)
    packages = _work_packages(payload)
    leads = _research_leads(payload, request.award_context)
    package_lines = "\n".join(f"- {item.title}: {item.scope}" for item in packages)
    declared_certifications = (
        ", ".join(payload.company.certifications)
        if payload.company.certifications
        else "[Confirm relevant certifications and validity]"
    )
    capability_statement = (
        f"{payload.company.name} — delivery-partner capability note\n\n"
        f"Tender context: {payload.tender_title} for {payload.agency}\n"
        f"UEN: {payload.company.uen or '[Confirm UEN]'}\n"
        f"Declared certifications: {declared_certifications}\n\n"
        f"Proposed bounded work packages:\n{package_lines}\n\n"
        "Evidence to attach: relevant delivery examples, named available personnel, implementation "
        "evidence, commercial assumptions and tender-specific compliance mapping."
    )
    outreach = (
        f"Subject: Delivery-partner capability for {payload.tender_title}\n\n"
        "Hello [recipient name],\n\n"
        f"We are assessing whether {payload.company.name} could support a bounded delivery package "
        f"for {payload.tender_title}. Our relevant declared capabilities are "
        f"{', '.join(item.title for item in packages)}.\n\n"
        "Before sharing commercial or confidential material, could we confirm whether your team "
        "has an active partner intake for this opportunity and whether the tender permits the "
        "proposed subcontracting structure? If relevant, we can provide a scoped capability note "
        "and evidence pack for review.\n\n"
        "Regards,\n[Name and role]"
    )
    next_actions = [
        "Review the complete tender and contract conditions for subcontracting restrictions",
        "Validate each public-award supplier as a relevant contracting party before contact",
        "Replace all placeholders and attach proof for the proposed work packages",
        "Complete commercial, liability, security and conflict due diligence",
        "Obtain human approval before any outreach or commitment",
    ]
    if eligibility == "PROHIBITED":
        next_actions.insert(0, "Stop partner-route preparation unless the buyer formally changes the prohibition")
    return PartnerRoutePackage(
        eligibility=eligibility,  # type: ignore[arg-type]
        eligibility_reason=eligibility_reason,
        tender_source=tender_source,
        direct_bid_context=_direct_bid_context(payload),
        work_packages=packages,
        research_leads=leads,
        capability_statement_draft=capability_statement,
        outreach_draft=outreach,
        next_actions=next_actions,
        boundaries=[
            "Awarded suppliers are research leads only, not verified prime contractors or active partner opportunities.",
            "The public dataset does not disclose subcontracting demand, contact details or willingness to partner.",
            "Company facts and capabilities are user supplied and must be verified before external use.",
            "Nothing is sent, committed or submitted by this function.",
        ],
    )
