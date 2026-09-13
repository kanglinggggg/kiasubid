from datetime import date

import pytest
from app.tender_lab.agent_loop import _evidence_register
from app.tender_lab.agent_models import AgentLoopRequest
from app.tender_lab.engine import build_brief, build_startup_coach, scan_policy_checks
from app.tender_lab.guidance import retrieve_guidance
from app.tender_lab.readiness import assess_company
from app.tender_lab.schemas import CompanyContext, TenderLabRequest
from app.tender_lab.workflow import run_tender_lab


def request(**updates):
    return TenderLabRequest(mode="SME", agency="Sample agency", tender_title="Portal service",
                            tender_text=updates.pop("tender_text", "[Page 1] The supplier must provide a secure portal."),
                            company=updates.pop("company", CompanyContext(name="Example SME")), **updates)


@pytest.mark.parametrize("response", [
    "We do not support multi-factor authentication for administrator accounts.",
    "Multi-factor authentication is not implemented.",
    "We plan to implement multi-factor authentication next year.",
    "MFA covers staff except administrators.",
    "We support MFA. Administrator MFA is not available.",
    "No account can log in without MFA.",  # conservative review, not a false green
])
def test_qualified_or_negated_implementation_does_not_pass(response):
    checks = scan_policy_checks(request(tender_text="All administrator accounts must use multi-factor authentication.", proposal_text=response))
    assert checks[0].status == "REVIEW"
    assert checks[0].remediation is not None


def test_positive_mfa_text_is_only_text_support():
    check = scan_policy_checks(request(tender_text="All administrator accounts must use MFA.", proposal_text="All administrators authenticate with MFA."))[0]
    assert check.status == "SUPPORTED"
    assert "reviewer" in check.rationale.lower()


def test_full_brief_does_not_drop_seventh_requirement_and_preserves_provenance():
    text = "[Page 3]\n" + "\n".join(f"Supplier must deliver component {i}." for i in range(1, 10))
    brief = build_brief(request(tender_text=text))
    assert len(brief.mandatory_signals) == 9
    assert len(brief.clauses) == 9
    assert all(c.source.location == "Page 3" for c in brief.clauses)
    assert "component 9" in brief.clauses[-1].source.excerpt


def test_structured_sections_quality_gating_and_milestone_checklist():
    text = """[Page 1]
The supplier shall develop a portal.
Evaluation criteria:
Sustainability: 10 percent based on energy consumption.
Local workforce development: 5 percent based on the training plan.
Payment terms:
20 percent on acceptance and 80 percent after delivery.
Contract conditions:
Warranty lasts 12 months.
Milestones:
Deposit due 20 September 2026 at 10:00 SGT.
Delivery on 30 September 2026 at 12:00 SGT.
"""
    result = run_tender_lab(request(tender_text=text))
    assert result.quality_advisor.status == "CRITERIA_FOUND"
    assert len(result.quality_advisor.opportunities) == 2
    assert all(q.criterion.location == "Page 1" for q in result.quality_advisor.opportunities)
    assert any("Payment" in c.categories and "80 percent" in c.source.excerpt for c in result.brief.clauses)
    assert any("Contract conditions" in c.categories and "Warranty" in c.source.excerpt for c in result.brief.clauses)
    assert {m.label for m in result.milestones} == {"Financial instrument deadline", "Delivery milestone"}
    assert all(any(m.id in a.source_ids for a in result.next_actions) for m in result.milestones)


def test_wrapped_deadline_keeps_its_event_label():
    text = """[Page 11]
Clarification questions
must be submitted by 12 September 2026 at 17:00 SGT. Tender submission closes on
18 September 2026 at 12:00 SGT.
"""
    result = run_tender_lab(request(tender_text=text))
    assert [(m.label, m.starts_at) for m in result.milestones] == [
        ("Clarification deadline", "2026-09-12T17:00"),
        ("Tender submission", "2026-09-18T12:00"),
    ]


@pytest.mark.parametrize("text", [
    "The supplier shall describe ESG and SkillsFuture plans for information only.",
    "Evaluation criteria: ESG is not scored and carries no additional points.",
    "No additional points are awarded for local workforce development.",
])
def test_no_invented_quality_points(text):
    result = run_tender_lab(request(tender_text=text))
    assert result.quality_advisor.opportunities == []


def test_startup_coach_adds_social_value_only_for_a_published_evaluation_criterion():
    payload = request(
        tender_text=(
            "The supplier must provide a portal.\n\n"
            "Evaluation criteria\n\n"
            "Environmental sustainability will carry 10 percent of the published quality score."
        )
    ).model_copy(update={"mode": "STARTUP"})

    coach = build_startup_coach(payload, [])

    assert coach is not None
    assert "Social value" in {item.area for item in coach.findings}
    assert "Social value and measurement" in {item.title for item in coach.sections}


def test_acra_context_is_not_an_official_financial_limit():
    company = CompanyContext(name="Example SME", uen="123456789X", registration_date="2021-09-13", paid_up_capital_sgd=100, max_delivery_value_sgd=500000)
    payload = request(company=company, contract_value_sgd=400000)
    fit = assess_company(payload, date(2026, 9, 12))
    assert fit.company_age_years == 4
    assert next(c for c in fit.checks if c.id == "FIT-CAPACITY").status == "MATCH"
    assert "official" in fit.boundary
    assert next(c for c in fit.checks if c.id == "FIT-CAPITAL").status == "CONTEXT"


def test_staff_shortfall_is_not_hidden_by_matching_ssic_or_price():
    payload = request(tender_text="The supplier must provide 4 engineers for the project.", company=CompanyContext(name="Small SME", employee_count=3))
    result = run_tender_lab(payload)
    assert result.company_fit.status == "MISMATCH"
    assert result.recommendation.action == "DO_NOT_BID_YET"
    assert result.recommendation.human_review_required
    assert result.recommendation.alternatives


def test_retrieval_is_tender_triggered_and_used_by_agents():
    assert retrieve_guidance("Buy a set of office tables") == []
    payload = request(tender_text="The supplier must implement MFA and follow applicable PWM requirements.")
    baseline = run_tender_lab(payload)
    sources = {p.id for p in baseline.retrieved_guidance}
    assert sources >= {"POLICY-AC2", "POLICY-PWM"}
    evidence = _evidence_register(AgentLoopRequest(tender=payload), baseline)
    assert sources <= {e.id for e in evidence}
    assert all(p.passage_type == "CURATED_SUMMARY" for p in baseline.retrieved_guidance)


def test_missing_draft_is_improve_first_and_missing_information_stays_unknown():
    result = run_tender_lab(request())
    assert result.company_fit.status == "NEEDS_INFORMATION"
    assert result.recommendation.action == "IMPROVE_FIRST"
    assert result.recommendation.missing_information
