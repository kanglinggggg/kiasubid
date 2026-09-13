import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { portfolioImpactFixture } from "../test/bidFixture";
import { PortfolioSimulationDrawer } from "./PortfolioSimulationDrawer";

it("compares deterministic routes without presenting them as recommendations", () => {
  render(
    <PortfolioSimulationDrawer
      bidStatus="RECOVERABLE"
      impact={portfolioImpactFixture}
      onClose={vi.fn()}
      open
    />,
  );

  expect(screen.getByText("Simulation only")).toBeInTheDocument();
  expect(screen.getByText("Planning assumptions")).toBeInTheDocument();
  expect(screen.getByText(/not recommendations/i)).toBeInTheDocument();
  expect(screen.getByText("Human decision required")).toBeInTheDocument();

  const protectCurrent = screen.getByRole("button", { name: /Protect this tender/i });
  const protectExisting = screen.getByRole("button", { name: /Protect existing commitment/i });
  expect(protectCurrent).toHaveAttribute("aria-pressed", "true");
  expect(protectExisting).toHaveAttribute("aria-pressed", "false");

  fireEvent.click(protectExisting);

  expect(protectExisting).toHaveAttribute("aria-pressed", "true");
  expect(
    screen.getByText(/Keep one CISSP assignment for the companion bid/i),
  ).toBeInTheDocument();
  expect(
    screen.getByText("No unresolved external fact changes this simulated consequence."),
  ).toBeInTheDocument();
});

it("closes the decision simulation with Escape", () => {
  const onClose = vi.fn();
  render(
    <PortfolioSimulationDrawer
      bidStatus="RECOVERABLE"
      impact={portfolioImpactFixture}
      onClose={onClose}
      open
    />,
  );

  fireEvent.keyDown(document, { key: "Escape" });
  expect(onClose).toHaveBeenCalledOnce();
});

it("uses a native modal dialog and restores focus when it closes", async () => {
  const trigger = document.createElement("button");
  trigger.textContent = "Open simulation";
  document.body.appendChild(trigger);
  trigger.focus();

  const { rerender } = render(
    <PortfolioSimulationDrawer
      bidStatus="RECOVERABLE"
      impact={portfolioImpactFixture}
      onClose={vi.fn()}
      open
    />,
  );

  const dialog = screen.getByRole("dialog");
  await waitFor(() => expect(dialog).toHaveAttribute("open"));
  expect(dialog.tagName).toBe("DIALOG");

  rerender(
    <PortfolioSimulationDrawer
      bidStatus="RECOVERABLE"
      impact={portfolioImpactFixture}
      onClose={vi.fn()}
      open={false}
    />,
  );

  expect(trigger).toHaveFocus();
  trigger.remove();
});

it("keeps the background inert when native modal creation is unavailable", async () => {
  const { rerender } = render(
    <>
      <button>Background action</button>
      <PortfolioSimulationDrawer
        bidStatus="RECOVERABLE"
        impact={portfolioImpactFixture}
        onClose={vi.fn()}
        open
      />
    </>,
  );

  const background = screen.getByText("Background action").closest("button")!;
  const dialog = screen.getByRole("dialog");
  await waitFor(() => expect(dialog).toHaveAttribute("open"));
  expect(dialog).toHaveAttribute("aria-modal", "true");
  expect(background).toHaveAttribute("aria-hidden", "true");
  expect(background).toHaveProperty("inert", true);

  const close = screen.getByRole("button", { name: "Close" });
  const trace = screen.getByText("Assumptions and calculation").closest("summary")!;
  trace.focus();
  fireEvent.keyDown(document, { key: "Tab" });
  expect(close).toHaveFocus();
  close.focus();
  fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
  expect(trace).toHaveFocus();

  rerender(
    <>
      <button>Background action</button>
      <PortfolioSimulationDrawer
        bidStatus="RECOVERABLE"
        impact={portfolioImpactFixture}
        onClose={vi.fn()}
        open={false}
      />
    </>,
  );
  expect(background).not.toHaveAttribute("aria-hidden");
  expect(background.inert).not.toBe(true);
});

it("renders nothing when no portfolio simulation is active", () => {
  render(
    <PortfolioSimulationDrawer
      bidStatus="FEASIBLE"
      impact={null}
      onClose={vi.fn()}
      open={false}
    />,
  );

  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});
