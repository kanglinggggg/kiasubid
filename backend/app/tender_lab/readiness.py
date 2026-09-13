"""Evidence-bounded company screening and recommendations for both user modes.

These outputs are computed from this request, not from the independent control-room demo.
Unknown evidence is deliberately not converted into a passed eligibility check.
"""
import re
from datetime import date

from app.tender_lab.engine import _sentences_with_locations
from app.tender_lab.schemas import (
    CompanyFit,
    FitCheck,
    QualityAdvisor,
    QualityOpportunity,
    ReadinessRecommendation,
    SourceReference,
    TenderLabRequest,
    TenderLabResponse,
)


def assess_company(payload: TenderLabRequest, today: date | None = None) -> CompanyFit:
    today = today or date.today()
    company = payload.company
    age = None
    try:
        registered = date.fromisoformat(company.registration_date or "")
        if registered <= today:
            age = today.year - registered.year - ((today.month, today.day) < (registered.month, registered.day))
    except ValueError:
        pass
    checks = [FitCheck(
        id="FIT-IDENTITY", area="Company identity", status="CONTEXT" if company.uen else "UNKNOWN",
        company_fact=f"{company.name} · UEN {company.uen or 'not supplied'} · {company.registration_status or 'status not supplied'}",
        explanation=f"Source: {company.profile_source_label or 'workspace declaration'}. This is not a registry verification.",
        next_step="Confirm the current entity status and any supplier registration required by this tender.",
    ), FitCheck(
        id="FIT-CAPITAL", area="Capital and company age", status="CONTEXT",
        company_fact=f"Paid-up capital: {'SGD ' + format(company.paid_up_capital_sgd, ',.0f') if company.paid_up_capital_sgd is not None else 'not supplied'} · Age: {str(age) + ' years' if age is not None else 'unknown'}",
        explanation="Capital and age are context only. They do not determine an official financial grade, cash available or contract ceiling.",
        next_step="Check actual cash flow, delivery capacity and tender-specific financial evidence separately.",
    )]
    value, capacity = payload.contract_value_sgd, company.max_delivery_value_sgd
    checks.append(FitCheck(
        id="FIT-CAPACITY", area="Delivery size", status="UNKNOWN" if value is None or capacity is None else "MISMATCH" if value > capacity else "MATCH",
        company_fact=f"Tender size: {value if value is not None else 'unknown'} SGD · Declared delivery limit: {capacity if capacity is not None else 'unknown'} SGD",
        explanation="Compares a user-entered tender value with the company's own delivery limit, not an official eligibility threshold.",
        next_step="Confirm staffing, cash-flow and delivery assumptions before making the bid decision.",
    ))
    vocabulary = [*company.capabilities, company.primary_ssic_description or ""]
    matches = [v for v in vocabulary if any(
        re.search(r"\b" + re.escape(word) + r"\b", payload.tender_text, re.I)
        for word in re.findall(r"[a-zA-Z]{5,}", v)
        if word.lower() not in {"services", "other", "activities", "including", "related", "company"}
    )]
    checks.append(FitCheck(
        id="FIT-SCOPE", area="Business scope and capability", status="CONTEXT" if matches else "UNKNOWN",
        company_fact=f"SSIC {company.primary_ssic_code or 'not supplied'} · " + (", ".join(v for v in vocabulary if v) or "No capabilities supplied"),
        explanation=("Shared scope terms: " + ", ".join(matches) + ". Keyword overlap is not evidence of delivery capability.") if matches else "No supported scope overlap identified. This does not establish ineligibility.",
        next_step="Attach relevant project examples, named people and delivery evidence against the required functions.",
    ))
    for i, sentence in enumerate(_sentences_with_locations(payload.tender_text)):
        staff = re.search(r"(?:at least|minimum(?: of)?|requires?|must (?:provide|have|assign))\s+(\d+)\s+(engineers?|staff|employees?|personnel|developers?)\b", sentence.text, re.I)
        if staff:
            required = int(staff[1])
            checks.append(FitCheck(
                id=f"FIT-STAFF-{i}", area="Staffing requirement",
                status="MISMATCH" if company.employee_count is not None and company.employee_count < required else "UNKNOWN",
                company_fact=f"Declared employee count: {company.employee_count if company.employee_count is not None else 'unknown'}",
                explanation=f"Tender names {required} {staff[2]}. Total employees do not prove qualified, available project personnel.",
                next_step="Confirm a named roster, qualifications, availability and any permitted subcontracting.",
                source=SourceReference(source_label=payload.source_label, location=sentence.location, excerpt=sentence.text),
            ))
        if re.search(r"\b(certification|certified|iso\s?\d+|mtcs|financial grade|gsr|epu/|sca/)\b", sentence.text, re.I):
            checks.append(FitCheck(
                id=f"FIT-CREDENTIAL-{i}", area="Credential verification", status="UNKNOWN",
                company_fact="Declared credentials: " + (", ".join(company.certifications) or "none supplied"),
                explanation="A profile or declared certificate name cannot establish the required tier, scope or validity.",
                next_step="Attach the current certificate or registration and verify its scope against this clause.",
                source=SourceReference(source_label=payload.source_label, location=sentence.location, excerpt=sentence.text),
            ))
    return CompanyFit(
        company_age_years=age, assessed_on=today.isoformat(), checks=checks,
        status="MISMATCH" if any(c.status == "MISMATCH" for c in checks) else "NEEDS_INFORMATION" if any(c.status == "UNKNOWN" for c in checks) else "POTENTIAL_FIT",
        boundary="Initial bid-fit screen only. Not official eligibility, GSR grading, legal advice or a decision to submit.",
    )


QUALITY_TOPICS = (
    ("Workforce development", r"skillsfuture|workforce development|staff training|employee training|skills development|local workforce",
     "For [named project roles], propose [relevant training] with [hours and completion date], subject to employer approval.",
     ["Role-to-skills gap assessment", "Training provider, schedule and completion records"], "People / delivery lead",
     "Budget course fees and staff time; do not assume SkillsFuture funding eligibility."),
    ("Environmental sustainability", r"esg|sustainab\w*|carbon|emissions|energy efficiency|green procurement",
     "Measure [environmental baseline] and propose [feasible target] for [in-scope service], reported [cadence].",
     ["Measured baseline and calculation method", "Supplier evidence and reporting owner"], "Sustainability / technical lead",
     "Cost the measurement and delivery changes before agreeing a target."),
    ("Social impact", r"social impact|social value|accessibility|inclusive|inclusion",
     "For [intended users], propose [accessible or inclusive outcome] measured by [test method] at [milestone].",
     ["User needs and accessibility test plan", "Outcome measure and evidence owner"], "Product / accessibility lead",
     "Budget user testing and any accessibility implementation work."),
)


def advise_quality(result: TenderLabResponse) -> QualityAdvisor:
    opportunities = []
    for clause in result.brief.clauses:
        if "Evaluation criteria" not in clause.categories:
            continue
        if re.search(r"\b(not evaluated|not scored|no (?:additional )?points|excluded from|not an evaluation)\b", clause.source.excerpt, re.I):
            continue
        for topic, terms, draft, evidence, owner, cost in QUALITY_TOPICS:
            if re.search(terms, clause.source.excerpt, re.I):
                opportunities.append(QualityOpportunity(
                    id=f"QUALITY-{len(opportunities) + 1}", topic=topic, criterion=clause.source,
                    suggested_commitment=draft, evidence_needed=evidence, owner_role=owner, cost_consideration=cost,
                ))
    return QualityAdvisor(
        status="CRITERIA_FOUND" if opportunities else "NO_PUBLISHED_CRITERIA_FOUND",
        opportunities=opportunities,
        boundary="Suggestions are tied to detected published evaluation wording. Verify applicability and every placeholder before use. No automatic points, funding, accreditation or company commitments are claimed.",
    )


def recommend(payload: TenderLabRequest, result: TenderLabResponse) -> ReadinessRecommendation:
    fit = result.company_fit
    mismatches = [c for c in fit.checks if c.status == "MISMATCH"] if fit else []
    gaps = [c for c in result.policy_checks if c.status == "GAP" and c.risk == "MANDATORY"]
    reviews = [c for c in result.policy_checks if c.status == "REVIEW"]
    missing = [c.next_step for c in fit.checks if c.status == "UNKNOWN"] if fit else []
    missing += [f"Review the original tender for {name.lower()}." for name in result.brief.missing_sections]
    alternatives = []
    if mismatches:
        action, headline = "DO_NOT_BID_YET", "Resolve the capacity mismatch before committing"
        reasons = [c.explanation for c in mismatches]
        ids = [c.id for c in mismatches]
        alternatives.append("Research a narrower subcontracting role only if the tender permits it and a prime contractor confirms scope; no partner is verified by this screen.")
    elif gaps or not payload.proposal_text.strip():
        action, headline = "IMPROVE_FIRST", "Prepare missing responses and supporting evidence"
        reasons = [f"{c.title}: {c.rationale}" for c in gaps] or ["No proposal draft has been supplied for the completeness review."]
        ids = [c.id for c in gaps]
    elif result.clarification_questions:
        action, headline = "REQUEST_CLARIFICATION", "Resolve the tender assumptions before finalising"
        reasons = [q.commercial_impact for q in result.clarification_questions]
        ids = [q.id for q in result.clarification_questions]
    elif reviews or missing or (result.pricing and result.pricing.gross_margin_sgd <= 0):
        action, headline = "PROCEED_WITH_CAUTION", "Continue preparation with unresolved review items"
        reasons = ["Applicability, credentials or source sections still need verification."]
        ids = [c.id for c in reviews]
    else:
        action, headline = "PROCEED_TO_HUMAN_REVIEW", "Take the prepared evidence to the bid owner"
        reasons = ["The configured screening rules found no outstanding block. This is not approval to submit or an exhaustive compliance check."]
        ids = [c.id for c in result.policy_checks]
    if result.pricing and result.pricing.gross_margin_sgd <= 0:
        reasons.append("The supplied price does not exceed estimated cost. Rework the commercial assumptions before approval.")
    return ReadinessRecommendation(action=action, headline=headline, reasons=reasons, evidence_ids=ids,
                                   alternatives=alternatives, missing_information=list(dict.fromkeys(missing)))
