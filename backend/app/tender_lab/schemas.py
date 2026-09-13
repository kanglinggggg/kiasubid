from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

TenderLabMode = Literal["SME", "STARTUP"]
FindingStatus = Literal["SUPPORTED", "GAP", "REVIEW"]
RouteStatus = Literal["FEASIBLE", "RECOVERABLE", "BLOCKED", "UNCERTAIN"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CompanyContext(StrictModel):
    name: str = Field(min_length=2, max_length=160)
    uen: str | None = Field(default=None, max_length=40)
    employee_count: int | None = Field(default=None, ge=0, le=1_000_000)
    annual_revenue_sgd: float | None = Field(default=None, ge=0)
    max_delivery_value_sgd: float | None = Field(default=None, ge=0)
    capabilities: list[str] = Field(default_factory=list, max_length=20)
    certifications: list[str] = Field(default_factory=list, max_length=20)
    entity_type: str | None = Field(default=None, max_length=160)
    registration_status: str | None = Field(default=None, max_length=120)
    registration_date: str | None = Field(default=None, max_length=40)
    primary_ssic_code: str | None = Field(default=None, pattern=r"^\d{5}$")
    primary_ssic_description: str | None = Field(default=None, max_length=500)
    paid_up_capital_sgd: float | None = Field(default=None, ge=0)
    profile_source_label: str | None = Field(default=None, max_length=255)
    source_type: Literal["USER_SUPPLIED", "SYNTHETIC_SAMPLE"] = "USER_SUPPLIED"
    verification_status: Literal["DECLARED", "VERIFIED", "NOT_VERIFIED"] = "DECLARED"


class PricingInputs(StrictModel):
    estimated_cost_sgd: float = Field(gt=0)
    proposed_price_sgd: float = Field(gt=0)
    comparable_awards_sgd: list[float] = Field(default_factory=list, max_length=30)
    comparables_source: Literal[
        "USER_SUPPLIED", "SYNTHETIC_SAMPLE", "PUBLIC_AWARD_CONTEXT"
    ] = "USER_SUPPLIED"
    comparables_note: str = Field(
        default="Values supplied by the user; scope comparability has not been verified.",
        max_length=500,
    )

    @model_validator(mode="after")
    def valid_comparables(self) -> "PricingInputs":
        if any(value <= 0 for value in self.comparable_awards_sgd):
            raise ValueError("comparable_awards_sgd values must be greater than zero")
        return self


class StartupAnswers(StrictModel):
    solution_summary: str = Field(default="", max_length=3000)
    technical_architecture: str = Field(default="", max_length=3000)
    delivery_approach: str = Field(default="", max_length=3000)
    operations_maintenance: str = Field(default="", max_length=3000)
    security_approach: str = Field(default="", max_length=3000)
    risk_management: str = Field(default="", max_length=3000)
    team_strength: str = Field(default="", max_length=3000)
    social_value: str = Field(default="", max_length=3000)


class TenderLabRequest(StrictModel):
    mode: TenderLabMode
    tender_title: str = Field(min_length=3, max_length=240)
    agency: str = Field(min_length=2, max_length=160)
    source_label: str = Field(default="User-supplied tender text", min_length=2, max_length=200)
    source_type: Literal["USER_SUPPLIED", "SYNTHETIC_SAMPLE"] = "USER_SUPPLIED"
    tender_text: str = Field(min_length=30, max_length=120_000)
    proposal_text: str = Field(default="", max_length=120_000)
    contract_value_sgd: float | None = Field(default=None, gt=0)
    company: CompanyContext
    pricing: PricingInputs | None = None
    startup_answers: StartupAnswers | None = None


class SourceReference(StrictModel):
    source_label: str
    location: str
    excerpt: str


class OfficialPolicySource(StrictModel):
    publisher: str
    title: str
    url: str
    reviewed_on: str
    supports: str
    limitation: str


class RemediationDraft(StrictModel):
    title: str
    draft: str
    placeholders: list[str]
    evidence_needed: list[str]
    boundary: str


class BriefClause(StrictModel):
    id: str
    categories: list[str]
    plain_language: str
    source: SourceReference


class TenderBrief(StrictModel):
    objective: str
    plain_language_summary: str
    mandatory_signals: list[str]
    requested_outcomes: list[str]
    clauses: list[BriefClause] = Field(default_factory=list)
    missing_sections: list[str] = Field(default_factory=list)
    method: str = "Source-linked extractive brief; not an exhaustive legal review."


class FitCheck(StrictModel):
    id: str
    area: str
    status: Literal["MATCH", "MISMATCH", "UNKNOWN", "CONTEXT"]
    company_fact: str
    explanation: str
    next_step: str
    source: SourceReference | None = None


class CompanyFit(StrictModel):
    company_age_years: int | None = None
    assessed_on: str
    status: Literal["POTENTIAL_FIT", "MISMATCH", "NEEDS_INFORMATION"]
    checks: list[FitCheck]
    boundary: str


class RetrievedGuidance(StrictModel):
    id: str
    title: str
    publisher: str
    url: str
    reviewed_on: str
    passage: str
    matched_terms: list[str]
    limitation: str
    passage_type: Literal["CURATED_SUMMARY"] = "CURATED_SUMMARY"


class QualityOpportunity(StrictModel):
    id: str
    topic: str
    criterion: SourceReference
    suggested_commitment: str
    evidence_needed: list[str]
    owner_role: str
    cost_consideration: str


class QualityAdvisor(StrictModel):
    status: Literal["CRITERIA_FOUND", "NO_PUBLISHED_CRITERIA_FOUND"]
    opportunities: list[QualityOpportunity]
    boundary: str


class ReadinessRecommendation(StrictModel):
    action: Literal["PROCEED_TO_HUMAN_REVIEW", "PROCEED_WITH_CAUTION", "IMPROVE_FIRST", "REQUEST_CLARIFICATION", "DO_NOT_BID_YET"]
    headline: str
    reasons: list[str]
    evidence_ids: list[str]
    alternatives: list[str]
    missing_information: list[str]
    human_review_required: bool = True


class PolicyCheck(StrictModel):
    id: str
    title: str
    status: FindingStatus
    risk: Literal["MANDATORY", "REVIEW"]
    rationale: str
    tender_source: SourceReference
    proposal_evidence: str | None
    next_step: str
    pack_id: str = "TENDER-ICT-KEYWORD-PACK"
    pack_version: str = "2026-09"
    basis: Literal[
        "DETERMINISTIC_HEURISTIC", "TENDER_TRIGGERED_OFFICIAL_CONTEXT"
    ] = "DETERMINISTIC_HEURISTIC"
    official_source: OfficialPolicySource | None = None
    applicability_note: str | None = None
    remediation: RemediationDraft | None = None


class ClarificationQuestion(StrictModel):
    id: str
    issue: str
    question: str
    commercial_impact: str
    tender_source: SourceReference


class Milestone(StrictModel):
    id: str
    label: str
    starts_at: str
    timezone: str = "Asia/Singapore"
    confidence: Literal["HIGH", "REVIEW"]
    tender_source: SourceReference


class PriceScenario(StrictModel):
    label: str
    price_sgd: float
    gross_margin_sgd: float
    gross_margin_percent: float
    versus_median_percent: float | None


class PricingAnalysis(StrictModel):
    proposed_price_sgd: float
    estimated_cost_sgd: float
    gross_margin_sgd: float
    gross_margin_percent: float
    comparable_count: int
    comparable_median_sgd: float | None
    position: str
    confidence: Literal[
        "PUBLIC_AWARD_CONTEXT", "USER_SUPPLIED_COMPARABLES", "NO_COMPARABLES"
    ]
    comparables_note: str
    scenarios: list[PriceScenario]
    boundary: str


class StrategyRoute(StrictModel):
    id: str
    title: str
    status: RouteStatus
    rationale: str
    unresolved_facts: list[str]
    output: list[str]
    human_decision_required: bool = True
    simulation_only: bool = True
    basis: Literal["USER_SUPPLIED_FACTS", "SYNTHETIC_SAMPLE"] = "USER_SUPPLIED_FACTS"


class ProposalSection(StrictModel):
    title: str
    draft: str
    evidence_needed: list[str]


class CoachFinding(StrictModel):
    area: str
    status: Literal["READY", "THIN", "MISSING"]
    critique: str
    next_prompt: str


class StartupCoach(StrictModel):
    sections: list[ProposalSection]
    findings: list[CoachFinding]
    rehearsal_questions: list[str]
    boundary: str


class NextAction(StrictModel):
    priority: int = Field(ge=1)
    title: str
    reason: str
    owner_role: str
    due_before: str | None
    source_ids: list[str]


class TraceStep(StrictModel):
    id: str
    label: str
    status: Literal["COMPLETED", "SKIPPED"]
    detail: str


class TenderLabResponse(StrictModel):
    mode: TenderLabMode
    source_type: Literal["USER_SUPPLIED", "SYNTHETIC_SAMPLE"]
    brief: TenderBrief
    policy_checks: list[PolicyCheck]
    clarification_questions: list[ClarificationQuestion]
    milestones: list[Milestone]
    pricing: PricingAnalysis | None
    strategy_routes: list[StrategyRoute]
    startup_coach: StartupCoach | None
    next_actions: list[NextAction]
    trace: list[TraceStep]
    calendar_ics: str
    boundaries: list[str]
    company_fit: CompanyFit | None = None
    quality_advisor: QualityAdvisor | None = None
    retrieved_guidance: list[RetrievedGuidance] = Field(default_factory=list)
    recommendation: ReadinessRecommendation | None = None


class DocumentPage(StrictModel):
    page: int
    text: str
    character_count: int = Field(ge=0)


class DocumentExtractionResponse(StrictModel):
    filename: str
    content_type: str
    page_count: int = Field(ge=1)
    character_count: int = Field(ge=0)
    text: str
    pages: list[DocumentPage]
    truncated: bool
    warnings: list[str]
