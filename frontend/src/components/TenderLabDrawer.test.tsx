import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { tenderLabApi } from "../api/client";
import type {
  AgentLoopResponse,
  AwardContextResponse,
  BusinessProfileIngestionResult,
  PartnerRoutePackage,
  TenderChangeSimulation,
  TenderLabMode,
  TenderLabRequest,
  TenderLabResponse,
} from "../types/tenderLab";
import { TenderLabDrawer } from "./TenderLabDrawer";
import { buildReadinessReport } from "./ReadinessPanels";

function sample(mode: TenderLabMode): TenderLabRequest {
  return {
    mode,
    tender_title: "Managed security service",
    agency: "Synthetic agency",
    source_label: "Synthetic tender pack",
    source_type: "SYNTHETIC_SAMPLE",
    tender_text:
      "[Page 1]\nThe supplier must provide 24x7 support. Clarification closes 12 September 2026 at 17:00 SGT.",
    proposal_text: "[Page 2]\nWe provide a 24x7 operating roster.",
    contract_value_sgd: 450000,
    company: {
      name: "Northstar Digital",
      uen: null,
      employee_count: 12,
      annual_revenue_sgd: null,
      max_delivery_value_sgd: 500000,
      capabilities: ["Security monitoring"],
      certifications: [],
      entity_type: null,
      registration_status: null,
      registration_date: null,
      primary_ssic_code: null,
      primary_ssic_description: null,
      paid_up_capital_sgd: null,
      profile_source_label: null,
      source_type: "SYNTHETIC_SAMPLE",
      verification_status: "NOT_VERIFIED",
    },
    pricing:
      mode === "SME"
        ? {
            estimated_cost_sgd: 350000,
            proposed_price_sgd: 450000,
            comparable_awards_sgd: [400000, 450000],
            comparables_source: "SYNTHETIC_SAMPLE",
            comparables_note: "Synthetic values",
          }
        : null,
    startup_answers:
      mode === "STARTUP"
        ? {
            solution_summary: "A useful solution",
            technical_architecture: "A web dashboard with a bounded alert-ingestion API.",
            delivery_approach: "",
            operations_maintenance: "",
            security_approach: "",
            risk_management: "",
            team_strength: "",
            social_value: "",
          }
        : null,
  };
}

function result(mode: TenderLabMode): TenderLabResponse {
  return {
    mode,
    source_type: "SYNTHETIC_SAMPLE",
    brief: {
      objective: "The agency seeks a managed security service.",
      plain_language_summary: "Review the mandatory service coverage before preparing a response.",
      mandatory_signals: ["The supplier must provide 24x7 support."],
      requested_outcomes: ["Provide 24x7 support."],
    },
    policy_checks: [
      {
        id: "CTRL-COVERAGE",
        title: "Service coverage",
        status: "SUPPORTED",
        risk: "MANDATORY",
        rationale: "Matching proposal text was found.",
        tender_source: {
          source_label: "Synthetic tender pack",
          location: "Page 1",
          excerpt: "The supplier must provide 24x7 support.",
        },
        proposal_evidence: "We provide a 24x7 operating roster.",
        next_step: "Review the operating roster.",
        pack_id: "TENDER-ICT-KEYWORD-PACK",
        pack_version: "2026-09",
        basis: "DETERMINISTIC_HEURISTIC",
      },
      {
        id: "CTRL-MFA",
        title: "Multi-factor authentication",
        status: "GAP",
        risk: "MANDATORY",
        rationale: "No matching implementation statement was found.",
        tender_source: {
          source_label: "Synthetic tender pack",
          location: "Page 2",
          excerpt: "The supplier must provide multi-factor authentication.",
        },
        proposal_evidence: null,
        next_step: "Add an implementation statement.",
        pack_id: "TENDER-ICT-KEYWORD-PACK",
        pack_version: "2026-09",
        basis: "DETERMINISTIC_HEURISTIC",
        remediation: {
          title: "Response scaffold — Multi-factor authentication",
          draft: "Implementation: [Describe the control that is actually in place.]",
          placeholders: ["Actual implementation", "Covered scope"],
          evidence_needed: ["Identity-provider configuration evidence"],
          boundary: "Fill every placeholder. Copying this scaffold does not establish compliance.",
        },
      },
    ],
    clarification_questions: [],
    milestones: [
      {
        id: "MILESTONE-01",
        label: "Clarification deadline",
        starts_at: "2026-09-12T17:00",
        timezone: "Asia/Singapore",
        confidence: "HIGH",
        tender_source: {
          source_label: "Synthetic tender pack",
          location: "Page 1",
          excerpt: "Clarification closes 12 September 2026 at 17:00 SGT.",
        },
      },
    ],
    pricing:
      mode === "SME"
        ? {
            proposed_price_sgd: 450000,
            estimated_cost_sgd: 350000,
            gross_margin_sgd: 100000,
            gross_margin_percent: 22.2,
            comparable_count: 2,
            comparable_median_sgd: 425000,
            position: "Validate scope comparability.",
            confidence: "USER_SUPPLIED_COMPARABLES",
            comparables_note: "Synthetic values",
            scenarios: [],
            boundary: "Not a win-probability model or recommendation.",
          }
        : null,
    strategy_routes: [
      {
        id: "ROUTE-DIRECT",
        title: "Prepare a direct bid",
        status: "FEASIBLE",
        rationale: "No hard stop found in supplied facts.",
        unresolved_facts: [],
        output: ["Human review"],
        human_decision_required: true,
        simulation_only: true,
        basis: "SYNTHETIC_SAMPLE",
      },
    ],
    startup_coach:
      mode === "STARTUP"
        ? {
            sections: [],
            findings: [],
            rehearsal_questions: [],
            boundary: "Does not invent experience.",
          }
        : null,
    next_actions: [
      {
        priority: 1,
        title: "Run human review",
        reason: "A person makes the final call.",
        owner_role: "Bid owner",
        due_before: null,
        source_ids: ["HUMAN-REVIEW"],
      },
    ],
    trace: [
      {
        id: "INGEST",
        label: "Read supplied tender text",
        status: "COMPLETED",
        detail: "Retained page markers.",
      },
    ],
    calendar_ics: "BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n",
    boundaries: [
      "A supported control means matching proposal text was found, not official compliance.",
    ],
  };
}

it("exports a consolidated review without overstating unrun agents or commercial certainty", () => {
  const payload = sample("SME");
  const markdown = buildReadinessReport(payload, result("SME"), null);

  expect(markdown).toContain("# Bid readiness review — Managed security service");
  expect(markdown).toContain("## Company bid fit");
  expect(markdown).toContain("## Clarifications");
  expect(markdown).toContain("## Commercial context");
  expect(markdown).toContain("Not a win-probability model or recommendation.");
  expect(markdown).toContain("Not run for this input. The screening recommendation is not a five-agent approval.");
  expect(markdown).toContain("Human review required before submission.");
});

it("retains the founder interview answer and critique when switching result tabs", async () => {
  vi.spyOn(tenderLabApi, "sample").mockImplementation(async mode => sample(mode));
  vi.spyOn(tenderLabApi, "analyze").mockResolvedValue(result("STARTUP"));
  vi.spyOn(tenderLabApi, "proposalPlan").mockResolvedValue({
    mentor_intro: "Founder interview", boundary: "Draft only",
    questions: [{ id: "Q-SOLUTION", answer_key: "solution_summary", section: "Solution",
      question: "What are you building?", why_it_matters: "Connect the product to the tender",
      answer_guidance: ["Give one concrete outcome"], required: true, context_refs: [] }],
  });
  vi.spyOn(tenderLabApi, "reviewProposalAnswer").mockResolvedValue({
    provider_state: "FALLBACK", fallback_reason: "Offline", boundary: "Draft only",
    execution: { mode: "DETERMINISTIC_FALLBACK", model_id: null, attempts: 0, duration_ms: 0, detail: "Local critique" },
    critique: { question_id: "Q-SOLUTION", verdict: "NEEDS_DETAIL", mentor_feedback: "Add acceptance evidence",
      strengths: [], gaps: [], evidence_needed: ["Acceptance test"], unsupported_claims: [],
      formalized_answer: "Our portal provides a clear project dashboard.", answer_quotes: ["Our portal"],
      needs_follow_up: true, follow_up_question: "How will the buyer test it?" },
  });
  render(<TenderLabDrawer open onClose={vi.fn()} />);
  await enterStartupWorkspace();
  fireEvent.click(await screen.findByRole("button", { name: "Run startup guide" }));
  await screen.findByText("Analysis ready");
  fireEvent.click(screen.getByRole("button", { name: "Proposal studio" }));
  const answer = await screen.findByLabelText("Solution answer");
  fireEvent.change(answer, { target: { value: "Our portal provides a clear project dashboard." } });
  fireEvent.click(screen.getByRole("button", { name: "Review answer" }));
  await screen.findByText("Add acceptance evidence");
  fireEvent.click(screen.getByRole("button", { name: "Brief" }));
  fireEvent.click(screen.getByRole("button", { name: "Quality advisor" }));
  fireEvent.click(screen.getByRole("button", { name: "Proposal studio" }));
  expect(screen.getByLabelText("Solution answer")).toHaveValue("Our portal provides a clear project dashboard.");
  expect(screen.getByText("Add acceptance evidence")).toBeVisible();
  expect(screen.getByText("How will the buyer test it?")).toBeVisible();
  expect(screen.getByText("Structured response wording")).toBeVisible();
  expect(tenderLabApi.proposalPlan).toHaveBeenCalledTimes(1);
});

const awardContext: AwardContextResponse = {
  query: "cybersecurity",
  agency: null,
  source_total_matches: 3,
  excluded_rows: 1,
  summary: {
    sample_count: 2,
    distinct_tenders: 2,
    median_sgd: 200000,
    lower_quartile_sgd: 150000,
    upper_quartile_sgd: 250000,
    minimum_sgd: 100000,
    maximum_sgd: 300000,
  },
  records: [
    {
      tender_no: "T-1",
      tender_description: "Cybersecurity monitoring",
      agency: "Agency A",
      award_date: "1/2/2026",
      supplier_name: "Supplier One",
      awarded_amt_sgd: 100000,
    },
    {
      tender_no: "T-2",
      tender_description: "Cybersecurity response",
      agency: "Agency A",
      award_date: "1/3/2026",
      supplier_name: "Supplier Two",
      awarded_amt_sgd: 300000,
    },
  ],
  provenance: {
    status: "LIVE_PUBLIC",
    publisher: "Ministry of Finance via data.gov.sg",
    dataset_title: "Government Procurement via GeBIZ",
    dataset_id: "d_acde1106003906a75c3fa052592f2fcb",
    source_url: "https://data.gov.sg/datasets/d_acde1106003906a75c3fa052592f2fcb/view",
    retrieved_at: "2026-09-08T00:00:00Z",
    coverage: "April 2021 to March 2026",
    methodology: [],
    limitation: "The dataset contains awards, not losing bids or win probabilities.",
  },
  intelligence: {
    sample_strength: "THIN",
    date_start: "01/02/2026",
    date_end: "01/03/2026",
    supplier_count: 2,
    recurring_supplier_count: 0,
    price_dispersion_percent: 50,
    top_suppliers: [
      {
        supplier_name: "Supplier One",
        award_rows: 1,
        total_awarded_sgd: 100000,
        row_share_percent: 50,
        value_share_percent: 25,
      },
    ],
    annual_patterns: [
      { year: 2026, award_rows: 2, median_sgd: 200000, total_awarded_sgd: 400000 },
    ],
    observations: ["No supplier repeats in the retained rows for this query."],
    boundary: "Descriptive only and cannot support a win probability or recommended price.",
  },
};

const reviewField = (reason: string) => ({
  value: null,
  confidence: "REVIEW" as const,
  sources: [],
  review_reason: reason,
}) satisfies BusinessProfileIngestionResult["epu_grade"];

const companyProfile: BusinessProfileIngestionResult = {
  source_type: "USER_SUPPLIED",
  verification_status: "NOT_OFFICIALLY_VERIFIED",
  source_document: "acra-profile.pdf",
  entity_name: {
    value: "Imported Digital Pte. Ltd.",
    confidence: "HIGH",
    sources: [{ page: 1, excerpt: "Entity Name: Imported Digital Pte. Ltd." }],
    review_reason: null,
  },
  uen: {
    value: "202612345N",
    confidence: "HIGH",
    sources: [{ page: 1, excerpt: "UEN: 202612345N" }],
    review_reason: null,
  },
  entity_type: reviewField("Review entity type"),
  status: reviewField("Review status"),
  registration_or_incorporation_date: reviewField("Review date"),
  primary_ssic: {
    value: { code: "62011", description: "Software development" },
    confidence: "HIGH",
    sources: [{ page: 2, excerpt: "Primary SSIC: 62011 Software development" }],
    review_reason: null,
  },
  secondary_ssic: reviewField("Review secondary SSIC"),
  paid_up_capital: {
    value: { amount: "250000.00", currency: "SGD" },
    confidence: "HIGH",
    sources: [{ page: 2, excerpt: "Paid-up Capital: SGD 250,000.00" }],
    review_reason: null,
  },
  epu_grade: reviewField("Separate EPU evidence required"),
  sca_grade: reviewField("Separate SCA evidence required"),
  warnings: [],
  boundaries: ["The upload is not an ACRA registry verification."],
};

const partnerPackage: PartnerRoutePackage = {
  eligibility: "APPROVAL_REQUIRED",
  eligibility_reason: "Subcontracting requires buyer approval.",
  tender_source: {
    source_label: "Synthetic tender pack",
    location: "Page 9",
    excerpt: "Subcontracting requires prior written approval.",
  },
  direct_bid_context: "Direct-bid capacity remains a human review.",
  work_packages: [
    {
      id: "WP-01",
      title: "Security monitoring",
      scope: "A bounded security monitoring module.",
      handoffs: ["Prime supplies interfaces"],
      exclusions: ["No unlisted obligations"],
      evidence_needed: ["Relevant delivery example"],
    },
  ],
  research_leads: [
    {
      supplier_name: "Supplier One",
      status: "RESEARCH_ONLY",
      observed_award_rows: 1,
      observed_total_awarded_sgd: 100000,
      public_basis: "One retained award row; no prime status or partner demand is implied.",
      source_url: "https://data.gov.sg/datasets/example/view",
      qualification_questions: ["Is there an active partner intake?"],
    },
  ],
  capability_statement_draft: "Capability note draft",
  outreach_draft: "Outreach draft",
  next_actions: ["Review the complete tender"],
  boundaries: ["Nothing is sent, committed or submitted by this function."],
};

const changeSimulation: TenderChangeSimulation = {
  source_label: "Corrigendum 3.pdf",
  before: {
    mandatory_gap_count: 0,
    review_item_count: 0,
    next_milestone: "2026-09-18T12:00",
    direct_route_status: "FEASIBLE",
  },
  simulated_after: {
    mandatory_gap_count: 1,
    review_item_count: 0,
    next_milestone: "2026-09-20T12:00",
    direct_route_status: "RECOVERABLE",
  },
  control_changes: [
    {
      id: "CTRL-CONTINUITY",
      title: "Service continuity",
      change_type: "NEW_CONTROL",
      before_status: null,
      simulated_status: "GAP",
      source: {
        source_label: "Corrigendum 3.pdf",
        location: "Page 2",
        excerpt: "The supplier must maintain disaster recovery.",
      },
      check: {
        id: "CTRL-CONTINUITY",
        title: "Service continuity",
        status: "GAP",
        risk: "MANDATORY",
        rationale: "No matching proposal evidence was found.",
        tender_source: {
          source_label: "Corrigendum 3.pdf",
          location: "Page 2",
          excerpt: "The supplier must maintain disaster recovery.",
        },
        proposal_evidence: null,
        next_step: "Provide recovery objectives and test evidence.",
        pack_id: "TENDER-ICT-KEYWORD-PACK",
        pack_version: "2026-09",
        basis: "DETERMINISTIC_HEURISTIC",
      },
    },
  ],
  milestone_changes: [
    {
      id: "MILE-01",
      label: "Tender submission",
      change_type: "REPLACED",
      previous_starts_at: "2026-09-18T12:00",
      simulated_starts_at: "2026-09-20T12:00",
      confidence: "HIGH",
      source: {
        source_label: "Corrigendum 3.pdf",
        location: "Page 2",
        excerpt: "Tender submission closes on 20 September 2026 at 12:00 SGT.",
      },
    },
  ],
  clarification_questions: [
    {
      id: "CLAR-01",
      issue: "Demand volume is not measurable",
      question: "Please confirm the expected event volume.",
      commercial_impact: "Changes capacity and cost.",
      tender_source: {
        source_label: "Corrigendum 3.pdf",
        location: "Page 2",
        excerpt: "Expected event volume remains TBC.",
      },
    },
  ],
  commercial_recheck: {
    status: "REVALIDATE",
    triggers: ["delivery scope", "demand volume"],
    impact: "Existing cost and capacity assumptions are stale until reviewed.",
    source: {
      source_label: "Corrigendum 3.pdf",
      location: "Page 2",
      excerpt: "The service adds three locations.",
    },
  },
  invalidated_outputs: ["Cost, capacity and public-award comparability assumptions"],
  recovery_actions: ["Update cost and capacity inputs, then rerun the simulations."],
  trace: [
    {
      id: "CHANGE-INGEST",
      label: "Read the supplied amendment",
      status: "COMPLETED",
      detail: "Kept the amendment separate from the baseline.",
    },
  ],
  boundaries: ["This is a stateless rehearsal. The baseline is unchanged."],
};

const agentLoopResult: AgentLoopResponse = {
  source_type: "SYNTHETIC_SAMPLE",
  provider_state: "LIVE",
  model_id: "anthropic.claude-test",
  loop_iterations: 2,
  plan: {
    mission: "Review the bid for grounded compliance, commercial and timeline risks.",
    tasks: [
      { agent: "COMPLIANCE", objective: "Test mandatory requirements.", focus: ["MFA", "service coverage"] },
      { agent: "COMMERCIAL", objective: "Test cost resilience.", focus: ["gross margin"] },
      { agent: "TIMELINE", objective: "Test extracted deadlines.", focus: ["clarification"] },
    ],
    success_criteria: ["Every finding cites a returned evidence ID."],
  },
  specialists: [
    {
      agent: "COMPLIANCE",
      output: {
        agent: "COMPLIANCE",
        summary: "The stated service coverage is supported by proposal wording.",
        findings: [
          {
            id: "CMP-001",
            title: "24x7 service coverage",
            status: "SUPPORTED",
            severity: "INFO",
            claim: "The tender asks for 24x7 support and the proposal states a 24x7 roster.",
            evidence_ids: ["TENDER-001", "PROPOSAL-001"],
            evidence_gap: null,
            downstream_effects: ["The operating roster still needs human verification."],
            recommended_action: "Attach the actual roster and escalation evidence.",
            confidence: "HIGH",
          },
        ],
        assumptions: [],
        handoff: "Critic should verify the cited source pair.",
      },
      critic_verdict: "PASS",
      critic_feedback: ["The claim stays within the cited wording."],
      revision_count: 1,
    },
    {
      agent: "COMMERCIAL",
      output: {
        agent: "COMMERCIAL",
        summary: "The arithmetic is available but remains a scenario, not a price recommendation.",
        findings: [
          {
            id: "COM-001",
            title: "Declared pricing inputs",
            status: "SUPPORTED",
            severity: "INFO",
            claim: "The workspace contains declared cost and price inputs for sensitivity testing.",
            evidence_ids: ["FACT-PRICING-INPUTS"],
            evidence_gap: null,
            downstream_effects: [],
            recommended_action: "Validate scope comparability before changing price.",
            confidence: "MEDIUM",
          },
        ],
        assumptions: ["The declared cost estimate is current."],
        handoff: "Human owner validates the cost basis.",
      },
      critic_verdict: "PASS",
      critic_feedback: ["No win probability was claimed."],
      revision_count: 0,
    },
    {
      agent: "TIMELINE",
      output: {
        agent: "TIMELINE",
        summary: "One clarification deadline is stated in the source.",
        findings: [
          {
            id: "TIM-001",
            title: "Clarification deadline",
            status: "SUPPORTED",
            severity: "INFO",
            claim: "The source states a clarification deadline on 12 September 2026 at 17:00 SGT.",
            evidence_ids: ["TENDER-002"],
            evidence_gap: null,
            downstream_effects: [],
            recommended_action: "Confirm the deadline against the complete tender portal record.",
            confidence: "HIGH",
          },
        ],
        assumptions: [],
        handoff: "Human owner confirms the portal time.",
      },
      critic_verdict: "PASS",
      critic_feedback: ["The date matches the cited excerpt."],
      revision_count: 0,
    },
  ],
  critic: {
    overall_verdict: "PASS",
    finding_reviews: [
      { finding_id: "CMP-001", verdict: "PASS", feedback: "The claim stays within the cited wording." },
      { finding_id: "COM-001", verdict: "PASS", feedback: "No win probability was claimed." },
      { finding_id: "TIM-001", verdict: "PASS", feedback: "The date matches the cited excerpt." },
    ],
    cross_agent_conflicts: [],
    human_checks: ["Verify the roster and tender portal deadline before approval."],
  },
  decision: {
    readiness: "READY_FOR_HUMAN_REVIEW",
    headline: "Grounded review ready for the bid owner",
    grounded_finding_ids: ["CMP-001", "COM-001", "TIM-001"],
    unresolved_finding_ids: [],
    decisions_required: ["Confirm whether the operating roster is sufficient."],
    next_step: "Bid owner reviews the evidence packet and records a decision.",
    boundary: "The loop does not approve, contact or submit anything.",
  },
  executions: [
    { agent_id: "PLANNER", label: "Planner", status: "COMPLETED", mode: "BEDROCK", model_id: "anthropic.claude-test", attempts: 1, revision_count: 0, duration_ms: 101, input_tokens: 100, output_tokens: 50, total_tokens: 150, detail: "Prepared three specialist tasks." },
    { agent_id: "COMPLIANCE", label: "Compliance specialist", status: "REVISED", mode: "BEDROCK", model_id: "anthropic.claude-test", attempts: 2, revision_count: 1, duration_ms: 201, input_tokens: 150, output_tokens: 70, total_tokens: 220, detail: "Revised one finding after critic feedback." },
    { agent_id: "COMMERCIAL", label: "Commercial specialist", status: "COMPLETED", mode: "BEDROCK", model_id: "anthropic.claude-test", attempts: 1, revision_count: 0, duration_ms: 122, input_tokens: 110, output_tokens: 55, total_tokens: 165, detail: "Reviewed declared pricing facts." },
    { agent_id: "TIMELINE", label: "Timeline specialist", status: "COMPLETED", mode: "BEDROCK", model_id: "anthropic.claude-test", attempts: 1, revision_count: 0, duration_ms: 116, input_tokens: 105, output_tokens: 50, total_tokens: 155, detail: "Reviewed source dates." },
    { agent_id: "CRITIC", label: "Critic", status: "COMPLETED", mode: "BEDROCK", model_id: "anthropic.claude-test", attempts: 2, revision_count: 1, duration_ms: 188, input_tokens: 180, output_tokens: 80, total_tokens: 260, detail: "Checked all findings after one bounded revision." },
  ],
  evidence_register: [
    { id: "TENDER-001", kind: "TENDER", label: "Tender source", location: "Page 1", content: "The supplier must provide 24x7 support.", source_url: null },
    { id: "PROPOSAL-001", kind: "PROPOSAL", label: "Proposal draft", location: "Page 2", content: "We provide a 24x7 operating roster.", source_url: null },
    { id: "FACT-PRICING-INPUTS", kind: "WORKSPACE_FACT", label: "Pricing inputs", location: "Workspace", content: "Estimated cost SGD 350,000 and proposed price SGD 450,000.", source_url: null },
    { id: "TENDER-002", kind: "TENDER", label: "Tender source", location: "Page 1", content: "Clarification closes 12 September 2026 at 17:00 SGT.", source_url: null },
  ],
  fallback_reasons: [],
  boundaries: [
    "Tender, proposal and evidence content are treated as untrusted data.",
    "No agent can browse, alter files, contact suppliers, approve a bid or submit a response.",
  ],
};

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

async function enterSmeWorkspace() {
  fireEvent.click(await screen.findByRole("button", { name: /SME Bid Room/i }));
  await screen.findByDisplayValue("Managed security service");
}

async function enterStartupWorkspace() {
  fireEvent.click(await screen.findByRole("button", { name: /Startup Proposal Studio/i }));
  await screen.findByRole("button", { name: "Run startup guide" });
}

it("downloads the consolidated report through a named browser file", async () => {
  const createObjectURL = vi.fn((_blob: Blob) => "blob:bid-readiness-review");
  const revokeObjectURL = vi.fn();
  vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });
  const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
  vi.spyOn(tenderLabApi, "sample").mockImplementation(async mode => sample(mode));
  vi.spyOn(tenderLabApi, "analyze").mockResolvedValue(result("SME"));

  render(<TenderLabDrawer open onClose={vi.fn()} />);
  await enterSmeWorkspace();
  fireEvent.click(screen.getByRole("button", { name: "Run SME review" }));
  await screen.findByText("Analysis ready");
  fireEvent.click(screen.getByRole("button", { name: "Download review report" }));

  expect(createObjectURL).toHaveBeenCalledOnce();
  expect(createObjectURL.mock.calls[0][0]).toBeInstanceOf(Blob);
  expect(anchorClick).toHaveBeenCalledOnce();
  expect((anchorClick.mock.instances[0] as HTMLAnchorElement).download).toBe("bid-readiness-review.md");
  await waitFor(() => expect(revokeObjectURL).toHaveBeenCalledWith("blob:bid-readiness-review"));
});

it("runs a bounded SME review and exposes its truth boundary", async () => {
  vi.spyOn(tenderLabApi, "sample").mockImplementation(async (mode) => sample(mode));
  vi.spyOn(tenderLabApi, "analyze").mockResolvedValue(result("SME"));
  vi.spyOn(tenderLabApi, "awardContext").mockResolvedValue(awardContext);
  vi.spyOn(tenderLabApi, "companyProfile").mockResolvedValue(companyProfile);
  vi.spyOn(tenderLabApi, "partnerRoute").mockResolvedValue(partnerPackage);
  vi.spyOn(tenderLabApi, "simulateChange").mockResolvedValue(changeSimulation);

  render(<TenderLabDrawer onClose={vi.fn()} open />);

  await enterSmeWorkspace();
  expect(screen.getByDisplayValue("Managed security service")).toBeInTheDocument();
  expect(screen.getByText("Prepared workspace")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Import ACRA Business Profile"), {
    target: { files: [new File(["profile"], "acra-profile.pdf", { type: "application/pdf" })] },
  });
  expect(await screen.findByDisplayValue("Imported Digital Pte. Ltd.")).toBeInTheDocument();
  expect(screen.getByText("NOT OFFICIALLY VERIFIED")).toBeInTheDocument();
  expect(screen.getByText("EPU / SCA are not inferred from ACRA data")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Run SME review" }));

  expect(await screen.findByText("Analysis ready")).toBeInTheDocument();
  expect(screen.getByText("The agency seeks a managed security service.")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "What the buyer wants delivered" })).toBeInTheDocument();
  expect(screen.getByText(/stateless/i)).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Checks" }));
  expect(screen.getByText("Proposal coverage")).toBeInTheDocument();
  expect(screen.getByText(/not official compliance certification/i)).toBeInTheDocument();
  expect(screen.getByText("Response scaffold")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Decision" }));
  expect(screen.getByRole("heading", { name: "Cost resilience" })).toBeInTheDocument();
  expect(screen.getByText(/not a win-probability model/i)).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Plan" }));
  expect(screen.getByRole("link", { name: /Google Calendar/i })).toHaveAttribute(
    "href",
    expect.stringContaining("calendar.google.com/calendar/render"),
  );

  fireEvent.click(screen.getByRole("button", { name: "Change impact" }));
  fireEvent.change(screen.getByLabelText("Amendment source"), {
    target: { value: "Corrigendum 3.pdf" },
  });
  fireEvent.change(screen.getByLabelText("Exact amendment wording"), {
    target: { value: "The supplier must maintain disaster recovery with a four-hour recovery time objective." },
  });
  fireEvent.click(screen.getByRole("button", { name: "Analyse change impact" }));
  expect(await screen.findByRole("heading", { name: "Decision state movement" })).toBeInTheDocument();
  expect(screen.getByText("NOT IN BASELINE")).toBeInTheDocument();
  expect(screen.getByText("MANDATORY")).toBeInTheDocument();
  expect(screen.getByText("Outputs that are now stale")).toBeInTheDocument();
  expect(screen.getByText(/baseline is unchanged/i)).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Award history" }));
  fireEvent.click(screen.getByRole("button", { name: "Search records" }));
  expect(await screen.findByText("Government Procurement via GeBIZ")).toBeInTheDocument();
  expect(screen.getByText(/not losing bids or win probabilities/i)).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: /Agency pattern/i })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /Build partner research package/i }));
  expect(await screen.findByRole("heading", { name: "Delivery-partner research package" })).toBeInTheDocument();
  expect(screen.getByText("RESEARCH ONLY")).toBeInTheDocument();
  expect(screen.getByText(/Nothing is sent, committed or submitted/i)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Award history" }));
  fireEvent.click(
    screen.getByRole("button", { name: /Use 2 values for pricing context/i }),
  );
  expect(screen.getByText(/2 public award value/i)).toBeInTheDocument();
}, 10_000);

it("locks amendment inputs while a change impact analysis is in flight", async () => {
  let resolveSimulation!: (value: TenderChangeSimulation) => void;
  const pendingSimulation = new Promise<TenderChangeSimulation>((resolve) => {
    resolveSimulation = resolve;
  });
  vi.spyOn(tenderLabApi, "sample").mockImplementation(async (mode) => sample(mode));
  vi.spyOn(tenderLabApi, "analyze").mockResolvedValue(result("SME"));
  vi.spyOn(tenderLabApi, "simulateChange").mockReturnValue(pendingSimulation);

  render(<TenderLabDrawer onClose={vi.fn()} open />);

  await enterSmeWorkspace();
  fireEvent.click(screen.getByRole("button", { name: "Run SME review" }));
  await screen.findByText("Analysis ready");
  fireEvent.click(screen.getByRole("button", { name: "Change impact" }));

  const source = screen.getByLabelText("Amendment source");
  const wording = screen.getByLabelText("Exact amendment wording");
  fireEvent.change(source, { target: { value: "Corrigendum 3.pdf" } });
  fireEvent.change(wording, {
    target: { value: "The supplier must maintain disaster recovery with a four-hour recovery time objective." },
  });
  fireEvent.click(screen.getByRole("button", { name: "Analyse change impact" }));

  await waitFor(() => {
    expect(source).toBeDisabled();
    expect(wording).toBeDisabled();
  });

  resolveSimulation(changeSimulation);
  expect(await screen.findByRole("heading", { name: "Decision state movement" })).toBeInTheDocument();
  await waitFor(() => expect(source).not.toBeDisabled());
}, 10_000);

it("switches to the startup branch and closes with Escape", async () => {
  const onClose = vi.fn();
  vi.spyOn(tenderLabApi, "sample").mockImplementation(async (mode) => sample(mode));
  render(<TenderLabDrawer onClose={onClose} open />);

  await enterStartupWorkspace();

  await waitFor(() => expect(tenderLabApi.sample).toHaveBeenLastCalledWith("STARTUP"));
  expect(await screen.findByRole("button", { name: "Run startup guide" })).toBeInTheDocument();

  fireEvent.keyDown(document, { key: "Escape" });
  expect(onClose).toHaveBeenCalledOnce();
});

it("runs the Agent Room and keeps findings traceable through critic to human decision", async () => {
  vi.spyOn(tenderLabApi, "sample").mockImplementation(async (mode) => sample(mode));
  vi.spyOn(tenderLabApi, "analyze").mockResolvedValue(result("SME"));
  vi.spyOn(tenderLabApi, "agentLoop").mockResolvedValue(agentLoopResult);

  render(<TenderLabDrawer onClose={vi.fn()} open />);

  await enterSmeWorkspace();
  fireEvent.click(screen.getByRole("button", { name: "Run SME review" }));
  await screen.findByText("Analysis ready");
  fireEvent.click(screen.getByRole("button", { name: "Agent room" }));

  expect(screen.getByRole("heading", { name: "Agent Room" })).toBeInTheDocument();
  expect(screen.getByLabelText(/Planner to specialists to critic to human decision/i)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Run agent loop" }));

  expect(await screen.findByRole("heading", { name: "What actually ran" })).toBeInTheDocument();
  expect(screen.getAllByText("LIVE").length).toBeGreaterThan(0);
  expect(screen.getByRole("heading", { name: "Evidence-grounded findings" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Grounded review ready for the bid owner" })).toBeInTheDocument();
  expect(screen.getByText("READY FOR HUMAN REVIEW")).toBeInTheDocument();
  expect(screen.getByText("The claim stays within the cited wording.")).toBeInTheDocument();

  fireEvent.click(screen.getAllByText("Evidence sources")[0]);
  expect(screen.getByText("The supplier must provide 24x7 support.")).toBeInTheDocument();
  expect(screen.getByText(/No agent can browse, alter files, contact suppliers/i)).toBeInTheDocument();
  expect(tenderLabApi.agentLoop).toHaveBeenCalledWith(expect.objectContaining({ mode: "SME" }), 1);
});
