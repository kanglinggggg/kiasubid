import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { bidFixture, portfolioImpactFixture } from "./test/bidFixture";

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  listFixtures: vi.fn(),
  reset: vi.fn(),
  loadFixture: vi.fn(),
  applyCorrigendum: vi.fn(),
  completeTask: vi.fn(),
  approve: vi.fn(),
}));

const amendmentMocks = vi.hoisted(() => ({
  preview: vi.fn(),
  apply: vi.fn(),
}));

const tenderLabMocks = vi.hoisted(() => ({
  sample: vi.fn(),
  analyze: vi.fn(),
  extract: vi.fn(),
  awardContext: vi.fn(),
}));

vi.mock("./api/client", () => ({
  bidApi: mocks,
  amendmentApi: amendmentMocks,
  tenderLabApi: tenderLabMocks,
}));

describe("Bid Control Room", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.get.mockResolvedValue(bidFixture);
    mocks.listFixtures.mockResolvedValue([
      {
        id: "main-corrigendum",
        label: "Main corrigendum",
        description: "Baseline demo",
        expected_status: "FEASIBLE",
      },
    ]);
  });

  it("renders the deterministic hero state", async () => {
    render(<App />);

    expect(await screen.findByRole("heading", { name: bidFixture.bid.title })).toBeInTheDocument();
    expect(screen.getAllByText("8 / 8").length).toBeGreaterThan(0);
    expect(screen.getAllByText("91%").length).toBeGreaterThan(0);
    expect(screen.getByText(/Assessed 21 Aug 2026/i)).toBeInTheDocument();
    const amendmentButton = screen.getByRole("button", { name: /Review Corrigendum #2/i });
    expect(amendmentButton).toBeEnabled();
    expect(screen.queryByRole("button", { name: /Compare .* routes/i })).not.toBeInTheDocument();

    fireEvent.click(amendmentButton);
    expect(screen.getByRole("dialog", { name: "Amendment review" })).toBeInTheDocument();
    expect(screen.getByText(/No record changes until a person confirms/i)).toBeInTheDocument();
  });

  it("reveals a simulation-only portfolio collision after the R17 change", async () => {
    mocks.get.mockResolvedValue({
      ...bidFixture,
      metrics: {
        ...bidFixture.metrics,
        operational_status: "RECOVERABLE",
        previous_operational_status: "FEASIBLE",
        critical_gates_verified: 7,
        submission_coverage: 84,
        deadline_risk: "MEDIUM",
      },
      latest_change: {
        id: "CHANGE-CORR-2",
        title: "Corrigendum #2",
        summary: "R17 minimum count changed from 3 to 4.",
        stable_key: "R17",
        old: "Minimum 3 valid CISSP-certified engineers.",
        new: "Minimum 4 valid CISSP-certified engineers.",
        old_count: 3,
        new_count: 4,
        old_requirement_id: "REQ-R17-V1",
        new_requirement_id: "REQ-R17-V2",
        old_assessment: "SUPERSEDED",
        new_assessment: "PARTIAL",
        impact: {
          critical_gates_broken: 1,
          assessments_superseded: 1,
          recovery_paths_found: 1,
        },
        detected_at: "2026-08-21T15:00:00",
      },
      portfolio_impact: portfolioImpactFixture,
    });
    render(<App />);

    const trigger = await screen.findByRole("button", { name: "Compare 3 routes" });
    expect(screen.getByText("Cross-bid impact")).toBeInTheDocument();
    expect(screen.getByText(/5 required across 2 pursuits/i)).toBeInTheDocument();

    fireEvent.click(trigger);

    expect(await screen.findByRole("dialog", { name: "Portfolio impact" })).toBeInTheDocument();
    expect(screen.getByText("No bid, staffing allocation, or external action has been changed.")).toBeInTheDocument();
    expect(screen.getByText("Bid-level readiness and cross-bid capacity are separate decisions.")).toBeInTheDocument();
    expect(screen.getByText(/does not use market prices, calculate win probability/i)).toBeInTheDocument();
  });

  it("keeps provider metadata out of the recording-first navigation", async () => {
    mocks.get.mockResolvedValue({
      ...bidFixture,
      interpretation: {
        mode: "GROQ",
        label: "Groq",
        model_id: "configured/model",
        source: "persisted_activity",
        event_id: "EVENT-1",
      },
    });
    render(<App />);

    expect(await screen.findByRole("heading", { name: bidFixture.bid.title })).toBeInTheDocument();
    expect(screen.queryByText(/Interpretation:/i)).not.toBeInTheDocument();
  });

  it("surfaces a backend startup failure instead of rendering stale values", async () => {
    mocks.get.mockRejectedValue(new Error("Backend unavailable"));
    render(<App />);

    expect(await screen.findByText("Bid state unavailable")).toBeInTheDocument();
    expect(screen.getByText("Backend unavailable")).toBeInTheDocument();
  });
});
