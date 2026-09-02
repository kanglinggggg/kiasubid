import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { bidFixture } from "./test/bidFixture";

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  listFixtures: vi.fn(),
  reset: vi.fn(),
  loadFixture: vi.fn(),
  applyCorrigendum: vi.fn(),
  completeTask: vi.fn(),
  approve: vi.fn(),
}));

vi.mock("./api/client", () => ({ bidApi: mocks }));

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

  it("renders the deterministic hero state and honest fallback label", async () => {
    render(<App />);

    expect(await screen.findByRole("heading", { name: bidFixture.bid.title })).toBeInTheDocument();
    expect(screen.getByText("Interpretation: Demo fallback")).toBeInTheDocument();
    expect(screen.getByText("8 / 8")).toBeInTheDocument();
    expect(screen.getByText("91%")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Apply Corrigendum #2/i })).toBeEnabled();
  });

  it("shows Groq only when the returned backend state records Groq", async () => {
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

    expect(await screen.findByText("Interpretation: Groq")).toHaveAttribute(
      "title",
      "Live model: configured/model",
    );
  });

  it("surfaces a backend startup failure instead of rendering stale values", async () => {
    mocks.get.mockRejectedValue(new Error("Backend unavailable"));
    render(<App />);

    expect(await screen.findByText("Bid state unavailable")).toBeInTheDocument();
    expect(screen.getByText("Backend unavailable")).toBeInTheDocument();
  });
});
