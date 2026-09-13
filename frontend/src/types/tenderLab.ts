export type TenderLabMode = "SME" | "STARTUP";
export type TenderLabSourceType = "USER_SUPPLIED" | "SYNTHETIC_SAMPLE";

export interface TenderLabCompany {
  name: string;
  uen: string | null;
  employee_count: number | null;
  annual_revenue_sgd: number | null;
  max_delivery_value_sgd: number | null;
  capabilities: string[];
  certifications: string[];
  entity_type: string | null;
  registration_status: string | null;
  registration_date: string | null;
  primary_ssic_code: string | null;
  primary_ssic_description: string | null;
  paid_up_capital_sgd: number | null;
  profile_source_label: string | null;
  source_type: TenderLabSourceType;
  verification_status: "DECLARED" | "VERIFIED" | "NOT_VERIFIED";
}

export interface ProfileSourceExcerpt {
  page: number;
  excerpt: string;
}

export interface ExtractedProfileField<T> {
  value: T | null;
  confidence: "HIGH" | "REVIEW";
  sources: ProfileSourceExcerpt[];
  review_reason: string | null;
}

export interface BusinessProfileIngestionResult {
  source_type: "USER_SUPPLIED";
  verification_status: "NOT_OFFICIALLY_VERIFIED";
  source_document: string;
  entity_name: ExtractedProfileField<string>;
  uen: ExtractedProfileField<string>;
  entity_type: ExtractedProfileField<string>;
  status: ExtractedProfileField<string>;
  registration_or_incorporation_date: ExtractedProfileField<{
    date: string;
    kind: "REGISTRATION" | "INCORPORATION";
  }>;
  primary_ssic: ExtractedProfileField<{ code: string | null; description: string | null }>;
  secondary_ssic: ExtractedProfileField<{ code: string | null; description: string | null }>;
  paid_up_capital: ExtractedProfileField<{ amount: string; currency: string | null }>;
  epu_grade: ExtractedProfileField<string>;
  sca_grade: ExtractedProfileField<string>;
  warnings: string[];
  boundaries: string[];
}

export interface TenderLabPricingInputs {
  estimated_cost_sgd: number;
  proposed_price_sgd: number;
  comparable_awards_sgd: number[];
  comparables_source: TenderLabSourceType | "PUBLIC_AWARD_CONTEXT";
  comparables_note: string;
}

export interface TenderLabStartupAnswers {
  solution_summary: string;
  technical_architecture: string;
  delivery_approach: string;
  operations_maintenance: string;
  security_approach: string;
  risk_management: string;
  team_strength: string;
  social_value: string;
}

export type ProposalAnswerKey = keyof TenderLabStartupAnswers;

export interface ProposalQuestion {
  id: string;
  answer_key: ProposalAnswerKey;
  section: string;
  question: string;
  why_it_matters: string;
  answer_guidance: string[];
  required: boolean;
  context_refs: string[];
}

export interface ProposalPlanResponse {
  questions: ProposalQuestion[];
  mentor_intro: string;
  boundary: string;
}

export interface ProposalCritique {
  question_id: string;
  verdict: "STRONG" | "NEEDS_DETAIL" | "RISKY_CLAIM";
  mentor_feedback: string;
  strengths: string[];
  gaps: string[];
  evidence_needed: string[];
  unsupported_claims: string[];
  formalized_answer: string;
  answer_quotes: string[];
  needs_follow_up: boolean;
  follow_up_question: string | null;
}

export interface ProposalExecution {
  mode: "BEDROCK" | "GROQ" | "DETERMINISTIC_FALLBACK";
  model_id: string | null;
  attempts: number;
  duration_ms: number;
  detail: string;
}

export interface ProposalAnswerReviewResponse {
  provider_state: "LIVE" | "FALLBACK";
  critique: ProposalCritique;
  execution: ProposalExecution;
  fallback_reason: string | null;
  boundary: string;
}

export interface GroundedDraftSection {
  section_key: ProposalAnswerKey;
  heading: string;
  text: string;
  supporting_answer_keys: ProposalAnswerKey[];
  context_refs: string[];
}

export interface ProposalDraftResponse {
  provider_state: "LIVE" | "FALLBACK";
  model_id: string | null;
  title: string;
  executive_summary: string;
  sections: GroundedDraftSection[];
  open_items: string[];
  markdown: string;
  review_notice: string;
  execution: ProposalExecution;
  fallback_reason: string | null;
  boundary: string;
}

export interface TenderLabRequest {
  mode: TenderLabMode;
  tender_title: string;
  agency: string;
  source_label: string;
  source_type: TenderLabSourceType;
  tender_text: string;
  proposal_text: string;
  contract_value_sgd: number | null;
  company: TenderLabCompany;
  pricing: TenderLabPricingInputs | null;
  startup_answers: TenderLabStartupAnswers | null;
}

export interface TenderLabSourceReference {
  source_label: string;
  location: string;
  excerpt: string;
}

export interface TenderLabPolicyCheck {
  id: string;
  title: string;
  status: "SUPPORTED" | "GAP" | "REVIEW";
  risk: "MANDATORY" | "REVIEW";
  rationale: string;
  tender_source: TenderLabSourceReference;
  proposal_evidence: string | null;
  next_step: string;
  pack_id: string;
  pack_version: string;
  basis: "DETERMINISTIC_HEURISTIC" | "TENDER_TRIGGERED_OFFICIAL_CONTEXT";
  official_source?: {
    publisher: string;
    title: string;
    url: string;
    reviewed_on: string;
    supports: string;
    limitation: string;
  } | null;
  applicability_note?: string | null;
  remediation?: {
    title: string;
    draft: string;
    placeholders: string[];
    evidence_needed: string[];
    boundary: string;
  } | null;
}

export interface TenderLabClarification {
  id: string;
  issue: string;
  question: string;
  commercial_impact: string;
  tender_source: TenderLabSourceReference;
}

export interface TenderLabMilestone {
  id: string;
  label: string;
  starts_at: string;
  timezone: string;
  confidence: "HIGH" | "REVIEW";
  tender_source: TenderLabSourceReference;
}

export interface TenderLabPriceScenario {
  label: string;
  price_sgd: number;
  gross_margin_sgd: number;
  gross_margin_percent: number;
  versus_median_percent: number | null;
}

export interface TenderLabPricing {
  proposed_price_sgd: number;
  estimated_cost_sgd: number;
  gross_margin_sgd: number;
  gross_margin_percent: number;
  comparable_count: number;
  comparable_median_sgd: number | null;
  position: string;
  confidence: "PUBLIC_AWARD_CONTEXT" | "USER_SUPPLIED_COMPARABLES" | "NO_COMPARABLES";
  comparables_note: string;
  scenarios: TenderLabPriceScenario[];
  boundary: string;
}

export interface TenderLabRoute {
  id: string;
  title: string;
  status: "FEASIBLE" | "RECOVERABLE" | "BLOCKED" | "UNCERTAIN";
  rationale: string;
  unresolved_facts: string[];
  output: string[];
  human_decision_required: boolean;
  simulation_only: boolean;
  basis: "USER_SUPPLIED_FACTS" | "SYNTHETIC_SAMPLE";
}

export interface TenderLabCoach {
  sections: Array<{ title: string; draft: string; evidence_needed: string[] }>;
  findings: Array<{
    area: string;
    status: "READY" | "THIN" | "MISSING";
    critique: string;
    next_prompt: string;
  }>;
  rehearsal_questions: string[];
  boundary: string;
}

export interface TenderLabResponse {
  mode: TenderLabMode;
  source_type: TenderLabSourceType;
  brief: {
    objective: string;
    plain_language_summary: string;
    mandatory_signals: string[];
    requested_outcomes: string[];
    clauses?: Array<{ id: string; categories: string[]; plain_language: string; source: TenderLabSourceReference }>;
    missing_sections?: string[];
    method?: string;
  };
  policy_checks: TenderLabPolicyCheck[];
  clarification_questions: TenderLabClarification[];
  milestones: TenderLabMilestone[];
  pricing: TenderLabPricing | null;
  strategy_routes: TenderLabRoute[];
  startup_coach: TenderLabCoach | null;
  next_actions: Array<{
    priority: number;
    title: string;
    reason: string;
    owner_role: string;
    due_before: string | null;
    source_ids: string[];
  }>;
  trace: Array<{
    id: string;
    label: string;
    status: "COMPLETED" | "SKIPPED";
    detail: string;
  }>;
  calendar_ics: string;
  boundaries: string[];
  company_fit?: {
    company_age_years: number | null;
    assessed_on: string;
    status: "POTENTIAL_FIT" | "MISMATCH" | "NEEDS_INFORMATION";
    checks: Array<{ id: string; area: string; status: "MATCH" | "MISMATCH" | "UNKNOWN" | "CONTEXT"; company_fact: string; explanation: string; next_step: string; source: TenderLabSourceReference | null }>;
    boundary: string;
  } | null;
  quality_advisor?: {
    status: "CRITERIA_FOUND" | "NO_PUBLISHED_CRITERIA_FOUND";
    opportunities: Array<{ id: string; topic: string; criterion: TenderLabSourceReference; suggested_commitment: string; evidence_needed: string[]; owner_role: string; cost_consideration: string }>;
    boundary: string;
  } | null;
  retrieved_guidance?: Array<{ id: string; title: string; publisher: string; url: string; reviewed_on: string; passage: string; matched_terms: string[]; limitation: string; passage_type: "CURATED_SUMMARY" }>;
  recommendation?: {
    action: string; headline: string; reasons: string[]; evidence_ids: string[];
    alternatives: string[]; missing_information: string[]; human_review_required: boolean;
  } | null;
}

export interface DocumentExtractionResponse {
  filename: string;
  content_type: string;
  page_count: number;
  character_count: number;
  text: string;
  pages: Array<{ page: number; text: string; character_count: number }>;
  truncated: boolean;
  warnings: string[];
}

export interface AwardContextResponse {
  query: string;
  agency: string | null;
  source_total_matches: number;
  excluded_rows: number;
  summary: {
    sample_count: number;
    distinct_tenders: number;
    median_sgd: number | null;
    lower_quartile_sgd: number | null;
    upper_quartile_sgd: number | null;
    minimum_sgd: number | null;
    maximum_sgd: number | null;
  };
  records: Array<{
    tender_no: string;
    tender_description: string;
    agency: string;
    award_date: string;
    supplier_name: string;
    awarded_amt_sgd: number;
  }>;
  provenance: {
    status: "LIVE_PUBLIC" | "CACHED_PUBLIC" | "UNAVAILABLE";
    publisher: string;
    dataset_title: string;
    dataset_id: string;
    source_url: string;
    retrieved_at: string;
    coverage: string;
    methodology: string[];
    limitation: string;
  };
  intelligence: {
    sample_strength: "NO_SAMPLE" | "THIN" | "DIRECTIONAL";
    date_start: string | null;
    date_end: string | null;
    supplier_count: number;
    recurring_supplier_count: number;
    price_dispersion_percent: number | null;
    top_suppliers: Array<{
      supplier_name: string;
      award_rows: number;
      total_awarded_sgd: number;
      row_share_percent: number;
      value_share_percent: number;
    }>;
    annual_patterns: Array<{
      year: number;
      award_rows: number;
      median_sgd: number;
      total_awarded_sgd: number;
    }>;
    observations: string[];
    boundary: string;
  };
}

export interface PartnerRoutePackage {
  eligibility: "POSSIBLE" | "APPROVAL_REQUIRED" | "PROHIBITED" | "NOT_FOUND_IN_TENDER";
  eligibility_reason: string;
  tender_source: TenderLabSourceReference | null;
  direct_bid_context: string;
  work_packages: Array<{
    id: string;
    title: string;
    scope: string;
    handoffs: string[];
    exclusions: string[];
    evidence_needed: string[];
  }>;
  research_leads: Array<{
    supplier_name: string;
    status: "RESEARCH_ONLY";
    observed_award_rows: number;
    observed_total_awarded_sgd: number;
    public_basis: string;
    source_url: string;
    qualification_questions: string[];
  }>;
  capability_statement_draft: string;
  outreach_draft: string;
  next_actions: string[];
  boundaries: string[];
}

export interface TenderChangeSimulation {
  source_label: string;
  before: {
    mandatory_gap_count: number;
    review_item_count: number;
    next_milestone: string | null;
    direct_route_status: TenderLabRoute["status"];
  };
  simulated_after: {
    mandatory_gap_count: number;
    review_item_count: number;
    next_milestone: string | null;
    direct_route_status: TenderLabRoute["status"];
  };
  control_changes: Array<{
    id: string;
    title: string;
    change_type: "NEW_CONTROL" | "RESTATED_CONTROL";
    before_status: TenderLabPolicyCheck["status"] | null;
    simulated_status: TenderLabPolicyCheck["status"];
    source: TenderLabSourceReference;
    check: TenderLabPolicyCheck;
  }>;
  milestone_changes: Array<{
    id: string;
    label: string;
    change_type: "ADDED" | "REPLACED" | "RESTATED";
    previous_starts_at: string | null;
    simulated_starts_at: string;
    confidence: "HIGH" | "REVIEW";
    source: TenderLabSourceReference;
  }>;
  clarification_questions: TenderLabClarification[];
  commercial_recheck: {
    status: "REVALIDATE" | "NO_AUTOMATIC_CHANGE";
    triggers: string[];
    impact: string;
    source: TenderLabSourceReference;
  };
  invalidated_outputs: string[];
  recovery_actions: string[];
  trace: TenderLabResponse["trace"];
  boundaries: string[];
}

export type AgentTask = "COMPLIANCE" | "COMMERCIAL" | "TIMELINE";
export type AgentMode = "BEDROCK" | "GROQ" | "DETERMINISTIC_FALLBACK";

export interface AgentEvidence {
  id: string;
  kind: "TENDER" | "PROPOSAL" | "WORKSPACE_FACT" | "PUBLIC_POLICY_CONTEXT";
  label: string;
  location: string;
  content: string;
  source_url: string | null;
}

export interface AgentPlan {
  mission: string;
  tasks: Array<{
    agent: AgentTask;
    objective: string;
    focus: string[];
  }>;
  success_criteria: string[];
}

export interface AgentFinding {
  id: string;
  title: string;
  status: "SUPPORTED" | "GAP" | "UNCERTAIN";
  severity: "BLOCKER" | "RISK" | "INFO";
  claim: string;
  evidence_ids: string[];
  evidence_gap: string | null;
  downstream_effects: string[];
  recommended_action: string;
  confidence: "HIGH" | "MEDIUM" | "LOW";
}

export interface SpecialistOutput {
  agent: AgentTask;
  summary: string;
  findings: AgentFinding[];
  assumptions: string[];
  handoff: string;
}

export interface CriticFindingReview {
  finding_id: string;
  verdict: "PASS" | "REVISE";
  feedback: string;
}

export interface AgentLoopResponse {
  source_type: TenderLabSourceType;
  provider_state: "LIVE" | "MIXED" | "FALLBACK";
  model_id: string | null;
  loop_iterations: number;
  plan: AgentPlan;
  specialists: Array<{
    agent: AgentTask;
    output: SpecialistOutput;
    critic_verdict: "PASS" | "REVISE";
    critic_feedback: string[];
    revision_count: number;
  }>;
  critic: {
    overall_verdict: "PASS" | "REVISE";
    finding_reviews: CriticFindingReview[];
    cross_agent_conflicts: string[];
    human_checks: string[];
  };
  decision: {
    readiness: "READY_FOR_HUMAN_REVIEW" | "NEEDS_EVIDENCE" | "HOLD";
    headline: string;
    grounded_finding_ids: string[];
    unresolved_finding_ids: string[];
    decisions_required: string[];
    next_step: string;
    boundary: string;
  };
  executions: Array<{
    agent_id: "PLANNER" | AgentTask | "CRITIC";
    label: string;
    status: "COMPLETED" | "REVISED" | "FALLBACK" | "NEEDS_REVIEW";
    mode: AgentMode;
    model_id: string | null;
    attempts: number;
    revision_count: number;
    duration_ms: number;
    input_tokens: number | null;
    output_tokens: number | null;
    total_tokens: number | null;
    detail: string;
  }>;
  evidence_register: AgentEvidence[];
  fallback_reasons: string[];
  boundaries: string[];
}
