import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { tenderLabApi } from "../api/client";
import type {
  ProposalAnswerReviewResponse,
  ProposalDraftResponse,
  ProposalPlanResponse,
  TenderLabRequest,
} from "../types/tenderLab";
import { GuidedProposalBuilder } from "./GuidedProposalBuilder";

const tender: TenderLabRequest = {
  mode: "STARTUP",
  tender_title: "Secure portal",
  agency: "Synthetic agency",
  source_label: "Synthetic tender",
  source_type: "SYNTHETIC_SAMPLE",
  tender_text: "[Page 1]\nThe supplier must provide a secure portal and test evidence.",
  proposal_text: "",
  contract_value_sgd: null,
  company: {
    name: "Demo team",
    uen: null,
    employee_count: 3,
    annual_revenue_sgd: null,
    max_delivery_value_sgd: null,
    capabilities: ["Web delivery"],
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
  pricing: null,
  startup_answers: {
    solution_summary: "We give agency users one portal and provide an acceptance test report.",
    technical_architecture: "Architecture answer",
    delivery_approach: "Delivery answer",
    operations_maintenance: "Operations and maintenance answer",
    security_approach: "Security answer",
    risk_management: "Risk management answer",
    team_strength: "Team answer",
    social_value: "",
  },
};

const plan: ProposalPlanResponse = {
  mentor_intro: "Explain your idea naturally.",
  boundary: "This does not confirm compliance.",
  questions: [
    {
      id: "Q-SOLUTION",
      answer_key: "solution_summary",
      section: "Solution and outcome",
      question: "What problem does the solution solve and what can the buyer verify?",
      why_it_matters: "The outcome must be reviewable.",
      answer_guidance: ["Name the problem", "Name acceptance evidence"],
      required: true,
      context_refs: ["TENDER-OBJECTIVE"],
    },
  ],
};

const review: ProposalAnswerReviewResponse = {
  provider_state: "FALLBACK",
  critique: {
    question_id: "Q-SOLUTION",
    verdict: "STRONG",
    mentor_feedback: "Good first-pass answer.",
    strengths: ["The answer names acceptance evidence."],
    gaps: [],
    evidence_needed: ["Acceptance test report"],
    unsupported_claims: [],
    formalized_answer: tender.startup_answers!.solution_summary,
    answer_quotes: [tender.startup_answers!.solution_summary],
    needs_follow_up: false,
    follow_up_question: null,
  },
  execution: {
    mode: "DETERMINISTIC_FALLBACK",
    model_id: null,
    attempts: 0,
    duration_ms: 0,
    detail: "Stable critique continued.",
  },
  fallback_reason: "Provider unavailable.",
  boundary: "The mentor does not validate claims.",
};

const draft: ProposalDraftResponse = {
  provider_state: "FALLBACK",
  model_id: null,
  title: "Secure portal — Supplier Response Draft",
  executive_summary: tender.startup_answers!.solution_summary,
  sections: [
    {
      section_key: "solution_summary",
      heading: "Proposed Solution and Outcomes",
      text: tender.startup_answers!.solution_summary,
      supporting_answer_keys: ["solution_summary"],
      context_refs: ["TENDER-OBJECTIVE"],
    },
  ],
  open_items: ["Attach the acceptance test report."],
  markdown: "# Secure portal\n\n## Proposed Solution and Outcomes\n\nGrounded answer.\n",
  review_notice: "Verify every claim before submission.",
  execution: {
    mode: "DETERMINISTIC_FALLBACK",
    model_id: null,
    attempts: 0,
    duration_ms: 0,
    detail: "Used recorded answers directly.",
  },
  fallback_reason: "Provider unavailable.",
  boundary: "Preparation material only.",
};

afterEach(() => vi.restoreAllMocks());

it("reviews a founder answer, generates a draft and hands it to Agent Room", async () => {
  vi.spyOn(tenderLabApi, "proposalPlan").mockResolvedValue(plan);
  vi.spyOn(tenderLabApi, "reviewProposalAnswer").mockResolvedValue(review);
  vi.spyOn(tenderLabApi, "generateProposalDraft").mockResolvedValue(draft);
  const onUseDraft = vi.fn().mockResolvedValue(undefined);

  render(<GuidedProposalBuilder tender={tender} onUseDraft={onUseDraft} />);

  expect(await screen.findByRole("heading", { name: /Founder interview/i })).toBeInTheDocument();
  expect(screen.getByText("0/1")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Review answer" }));
  expect(await screen.findByText("Good first-pass answer.")).toBeInTheDocument();
  expect(screen.getByText("1/1")).toBeInTheDocument();
  expect(screen.getByText(/policy rules engine/i)).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: /Finish interview/i }));
  fireEvent.click(screen.getByRole("button", { name: "Generate grounded draft" }));
  expect(await screen.findByRole("heading", { name: draft.title })).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Use draft in Agent Room" }));
  await waitFor(() =>
    expect(onUseDraft).toHaveBeenCalledWith(draft.markdown, tender.startup_answers),
  );
  expect(screen.getByRole("button", { name: "Use draft in Agent Room" })).not.toBeDisabled();
});

it("clears the previous question plan when the tender changes and replacement planning fails", async () => {
  vi.spyOn(tenderLabApi, "proposalPlan")
    .mockResolvedValueOnce(plan)
    .mockRejectedValueOnce(new Error("Replacement plan unavailable"));

  const view = render(<GuidedProposalBuilder tender={tender} onUseDraft={vi.fn()} />);
  expect(await screen.findByText(plan.questions[0].question)).toBeInTheDocument();

  view.rerender(
    <GuidedProposalBuilder
      tender={{ ...tender, tender_text: tender.tender_text + "\nThe buyer added a new condition." }}
      onUseDraft={vi.fn()}
    />,
  );

  expect(screen.queryByText(plan.questions[0].question)).not.toBeInTheDocument();
  expect(await screen.findByText("Replacement plan unavailable")).toBeInTheDocument();
  expect(screen.queryByText(plan.questions[0].question)).not.toBeInTheDocument();
});
