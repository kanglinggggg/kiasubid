import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { amendmentApi } from "../api/client";
import { bidFixture } from "../test/bidFixture";
import type { AmendmentPreviewResponse } from "../types/amendment";
import type { BidState } from "../types/bid";
import { AmendmentReviewDrawer } from "./AmendmentReviewDrawer";

const source = {
  document_name: "DGA_ICT_2026_017_Corrigendum_2.pdf",
  document_version: 2,
  page: 2,
  section: "1. Amendment to Clause 4.3",
  exact_excerpt:
    "Replace ‘not fewer than three personnel holding valid CISSP certification’ with ‘not fewer than four personnel holding valid CISSP certification’.",
  sha256: "74c30a9fa3aeb6adfef4d350dc09eed53efa9330bc5e53c39e93ff65982be5a5",
  provenance: "USER_SUPPLIED_EXACT_TEXT" as const,
};

const target = {
  id: "REQ-R17-V1",
  stable_key: "R17",
  version: 1,
  text: "Minimum 3 valid CISSP-certified engineers.",
  requirement_type: "MANPOWER",
  gate_type: "MANDATORY",
  minimum_count: 3,
  certification: "CISSP",
  assessment: "SATISFIED",
};

const clearPreview: AmendmentPreviewResponse = {
  preview_id: "preview-r17-clear-0001",
  state: "PREVIEW_READY",
  apply_allowed: true,
  block_reason: null,
  source,
  target,
  proposed: {
    ...target,
    id: "PREVIEW-REQ-R17-V2",
    version: 2,
    text: "Minimum 4 valid CISSP-certified engineers.",
    minimum_count: 4,
    assessment: "PARTIAL",
  },
  change_type: "MODIFIED",
  changed_fields: [
    { field: "minimum_count", old_value: "3", new_value: "4" },
    {
      field: "text",
      old_value: "Minimum 3 valid CISSP-certified engineers.",
      new_value: "Minimum 4 valid CISSP-certified engineers.",
    },
  ],
  reason_summary: "R17 increases the minimum certified personnel count from 3 to 4.",
  interpretation_mode: "DEMO_FALLBACK",
  model_id: null,
  fallback_reason: "Deterministic test parser used.",
  impact: {
    assessment_before: "SATISFIED",
    assessment_after: "PARTIAL",
    operational_status_before: "FEASIBLE",
    operational_status_after: "RECOVERABLE",
    critical_gates_before: "8/8",
    critical_gates_after: "7/8",
    submission_coverage_before: 91,
    submission_coverage_after: 84,
    deadline_risk_before: "LOW",
    deadline_risk_after: "MEDIUM",
    calculation_note: "Projected from the current internal evidence and open-task state.",
  },
  planned_tasks: [
    {
      key: "verify-candidate",
      title: "Verify the fourth CISSP candidate",
      description: "Collect a current certificate and confirm delivery availability.",
      owner: "Bid manager",
      status: "OPEN",
      priority: "CRITICAL",
      due_at: "2026-08-24T09:00:00",
      latest_safe_at: "2026-08-25T09:00:00",
      estimated_duration_hours: 3,
      depends_on: [],
    },
    {
      key: "refresh-matrix",
      title: "Refresh the compliance matrix",
      description: "Attach the verified evidence to the revised obligation.",
      owner: "Compliance lead",
      status: "WAITING",
      priority: "HIGH",
      due_at: "2026-08-25T12:00:00",
      latest_safe_at: "2026-08-26T09:00:00",
      estimated_duration_hours: 1,
      depends_on: ["verify-candidate"],
    },
  ],
  clarification: null,
  workflow_trace: [
    { step: 1, node: "SOURCE_VALIDATION", status: "DONE", detail: "Exact source text retained." },
    { step: 2, node: "TARGET_MATCH", status: "DONE", detail: "Matched the selected R17 obligation." },
    { step: 3, node: "IMPACT_SIMULATION", status: "DONE", detail: "Calculated without writing records." },
    { step: 4, node: "HUMAN_CHECKPOINT", status: "DONE", detail: "Waiting for a person to confirm." },
  ],
  human_checkpoint:
    "Review the exact source, field changes and projected consequences before updating the internal workspace.",
  expires_in_minutes: 30,
};

const ambiguousPreview: AmendmentPreviewResponse = {
  ...clearPreview,
  preview_id: "preview-r17-ambiguous-0001",
  state: "REVIEW_REQUIRED",
  apply_allowed: false,
  block_reason: "The amendment does not provide a measurable replacement obligation.",
  source: {
    ...source,
    exact_excerpt:
      "R17 now requires adequate suitably qualified standby resources as needed. Further details will be advised separately.",
  },
  proposed: null,
  change_type: "UNCHANGED",
  changed_fields: [],
  reason_summary: "The wording is ambiguous, so the workflow stopped without proposing a record change.",
  impact: null,
  planned_tasks: [],
  clarification: {
    reason: "A precise replacement count or qualification was not supplied.",
    question:
      "Please confirm the exact minimum personnel count, required certification and effective clause wording for R17.",
    source_reference: "DGA_ICT_2026_017_Corrigendum_2.pdf · Page 2",
    external_action: "COPY_ONLY",
  },
  workflow_trace: [
    { step: 1, node: "SOURCE_VALIDATION", status: "DONE", detail: "Exact source text retained." },
    { step: 2, node: "TARGET_MATCH", status: "DONE", detail: "Matched R17." },
    { step: 3, node: "INTERPRET_CHANGE", status: "BLOCKED", detail: "No precise replacement value." },
    { step: 4, node: "IMPACT_SIMULATION", status: "SKIPPED", detail: "Unsafe to simulate an unknown value." },
  ],
  human_checkpoint: "Resolve the ambiguity and run another preview. No update is available.",
};

afterEach(() => vi.restoreAllMocks());

it("previews the ripple effect and requires a checked human gate before apply", async () => {
  const onApplied = vi.fn();
  const updatedBid: BidState = {
    ...bidFixture,
    requirements: bidFixture.requirements.map((requirement) =>
      requirement.stable_key === "R17"
        ? {
            ...requirement,
            id: "REQ-R17-V2",
            version: 2,
            text: "The Tenderer shall propose not fewer than four personnel holding valid CISSP certification.",
          }
        : requirement,
    ),
    metrics: {
      ...bidFixture.metrics,
      operational_status: "RECOVERABLE",
      previous_operational_status: "FEASIBLE",
      critical_gates_verified: 7,
      submission_coverage: 84,
      deadline_risk: "MEDIUM",
    },
  };
  vi.spyOn(amendmentApi, "preview").mockResolvedValue(clearPreview);
  vi.spyOn(amendmentApi, "apply").mockResolvedValue(updatedBid);

  const { rerender } = render(
    <AmendmentReviewDrawer
      bid={bidFixture}
      onApplied={onApplied}
      onClose={vi.fn()}
      open
    />,
  );

  fireEvent.change(screen.getByLabelText("Exact amendment wording"), {
    target: { value: clearPreview.source.exact_excerpt },
  });
  fireEvent.click(screen.getByRole("button", { name: "Analyse amendment" }));

  expect(await screen.findByText("Preview ready")).toBeInTheDocument();
  expect(screen.getByText("R17 v1 → v2")).toBeInTheDocument();
  expect(screen.getByText("91%")).toBeInTheDocument();
  expect(screen.getByText("84%")).toBeInTheDocument();
  expect(screen.getByText("2 dependency-aware tasks")).toBeInTheDocument();
  expect(screen.getByText(/No write/i)).toBeInTheDocument();

  const confirm = screen.getByRole("button", { name: "Confirm & update workspace" });
  const checkpoint = screen.getByText("Human checkpoint").closest("section")!;
  expect(confirm).toBeDisabled();
  expect(within(checkpoint).getByText(/Review the exact source/i)).toBeInTheDocument();

  fireEvent.click(
    screen.getByRole("checkbox", {
      name: "I reviewed the source and proposed field changes",
    }),
  );
  expect(confirm).toBeEnabled();
  fireEvent.click(confirm);

  await waitFor(() =>
    expect(amendmentApi.apply).toHaveBeenCalledWith("BID-DEMO-001", {
      preview_id: "preview-r17-clear-0001",
      reviewed_source_and_diff: true,
      confirmed_by: "Bid owner",
    }),
  );
  expect(onApplied).toHaveBeenCalledWith(updatedBid);
  rerender(
    <AmendmentReviewDrawer
      bid={updatedBid}
      onApplied={onApplied}
      onClose={vi.fn()}
      open
    />,
  );
  expect(await screen.findByText("Workspace updated")).toBeInTheDocument();
});

it("fails closed on ambiguous wording and exposes a clarification draft", async () => {
  vi.spyOn(amendmentApi, "preview").mockResolvedValue(ambiguousPreview);
  const apply = vi.spyOn(amendmentApi, "apply");

  render(
    <AmendmentReviewDrawer
      bid={bidFixture}
      onApplied={vi.fn()}
      onClose={vi.fn()}
      open
    />,
  );

  fireEvent.change(screen.getByLabelText("Exact amendment wording"), {
    target: { value: ambiguousPreview.source.exact_excerpt },
  });
  fireEvent.click(screen.getByRole("button", { name: "Analyse amendment" }));

  expect(await screen.findByText("Review required")).toBeInTheDocument();
  expect(screen.getByText("R17 v1 · no version proposed")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Clarification needed" })).toBeInTheDocument();
  expect(screen.getByText(/exact minimum personnel count/i)).toBeInTheDocument();
  expect(screen.getByText("Write blocked")).toBeInTheDocument();
  expect(screen.getByRole("checkbox")).toBeDisabled();
  expect(screen.getByRole("button", { name: "Confirm & update workspace" })).toBeDisabled();
  expect(apply).not.toHaveBeenCalled();
});

it("closes the review with Escape while no request is running", () => {
  const onClose = vi.fn();
  render(
    <AmendmentReviewDrawer
      bid={bidFixture}
      onApplied={vi.fn()}
      onClose={onClose}
      open
    />,
  );

  fireEvent.keyDown(document, { key: "Escape" });
  expect(onClose).toHaveBeenCalledOnce();
});

it("clears a stale preview when the workspace returns to an earlier requirement version", async () => {
  const appliedBid: BidState = {
    ...bidFixture,
    requirements: bidFixture.requirements.map((requirement) =>
      requirement.stable_key === "R17"
        ? {
            ...requirement,
            id: "REQ-R17-V2",
            version: 2,
            text: "The Tenderer shall propose not fewer than four personnel holding valid CISSP certification.",
          }
        : requirement,
    ),
  };
  vi.spyOn(amendmentApi, "preview").mockResolvedValue({
    ...ambiguousPreview,
    target: {
      ...ambiguousPreview.target,
      id: "REQ-R17-V2",
      version: 2,
      minimum_count: 4,
    },
  });

  const { rerender } = render(
    <AmendmentReviewDrawer
      bid={appliedBid}
      onApplied={vi.fn()}
      onClose={vi.fn()}
      open
    />,
  );
  fireEvent.change(screen.getByLabelText("Exact amendment wording"), {
    target: { value: ambiguousPreview.source.exact_excerpt },
  });
  fireEvent.click(screen.getByRole("button", { name: "Analyse amendment" }));
  expect(await screen.findByText("Review required")).toBeInTheDocument();

  rerender(
    <AmendmentReviewDrawer
      bid={bidFixture}
      onApplied={vi.fn()}
      onClose={vi.fn()}
      open
    />,
  );

  await waitFor(() => expect(screen.queryByText("Review required")).not.toBeInTheDocument());
  expect(
    (screen.getByRole("textbox", {
      name: "Exact amendment wording",
    }) as HTMLTextAreaElement).value,
  ).toBe("");
  expect(screen.getByRole("combobox", { name: "Tracked requirement" })).toHaveValue(
    "REQ-R17-V1",
  );
});
