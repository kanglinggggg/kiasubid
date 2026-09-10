import {
  ArrowRight,
  CalendarRange,
  FlaskConical,
  Network,
  Route,
  ShieldAlert,
  Users,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type {
  OperationalStatus,
  PortfolioAffectedBid,
  PortfolioImpact,
  PortfolioRoute,
} from "../types/bid";
import { StatusPill } from "./StatusPill";

function parseUtc(value: string) {
  const alreadyHasZone = /(?:Z|[+-]\d{2}:\d{2})$/i.test(value);
  return new Date(alreadyHasZone ? value : `${value}Z`);
}

function formatWindow(start: string, end: string) {
  const format = new Intl.DateTimeFormat("en-SG", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "Asia/Singapore",
  });
  return `${format.format(parseUtc(start))} – ${format.format(parseUtc(end))}`;
}

function bidLabel(bid: PortfolioAffectedBid) {
  return bid.relationship === "CURRENT" ? "This tender" : bid.reference_number;
}

function outcomeFor(route: PortfolioRoute, bidId: string): OperationalStatus | null {
  return route.outcomes.find((outcome) => outcome.bid_id === bidId)?.status ?? null;
}

interface PortfolioSimulationDrawerProps {
  open: boolean;
  onClose: () => void;
  impact: PortfolioImpact | null;
  bidStatus: OperationalStatus;
}

export function PortfolioSimulationDrawer({
  open,
  onClose,
  impact,
  bidStatus,
}: PortfolioSimulationDrawerProps) {
  const [selectedRouteId, setSelectedRouteId] = useState<string | null>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const onCloseRef = useRef(onClose);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!open || !impact) return;

    const dialog = dialogRef.current;
    if (!dialog) return;
    const activeDialog: HTMLDialogElement = dialog;

    setSelectedRouteId(impact.routes[0]?.id ?? null);
    previousFocusRef.current = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    const fallbackSiblings: Array<{
      element: HTMLElement;
      inert: boolean;
      ariaHidden: string | null;
    }> = [];
    let modalFallback = false;
    document.body.style.overflow = "hidden";
    if (!dialog.open) {
      try {
        dialog.showModal();
      } catch {
        modalFallback = true;
        dialog.setAttribute("open", "");
        dialog.setAttribute("aria-modal", "true");
        for (const sibling of Array.from(dialog.parentElement?.children ?? [])) {
          if (sibling === dialog || !(sibling instanceof HTMLElement)) continue;
          fallbackSiblings.push({
            element: sibling,
            inert: sibling.inert,
            ariaHidden: sibling.getAttribute("aria-hidden"),
          });
          sibling.inert = true;
          sibling.setAttribute("aria-hidden", "true");
        }
      }
    }
    window.setTimeout(() => closeButtonRef.current?.focus(), 0);

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (modalFallback && event.key === "Tab") {
        const focusable = Array.from(
          activeDialog.querySelectorAll<HTMLElement>(
            'button:not([disabled]), summary, [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
          ),
        );
        if (focusable.length === 0) {
          event.preventDefault();
          return;
        }
        const first = focusable[0];
        const last = focusable.at(-1)!;
        const active = document.activeElement;
        if (event.shiftKey && (active === first || !activeDialog.contains(active))) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && (active === last || !activeDialog.contains(active))) {
          event.preventDefault();
          first.focus();
        }
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
      for (const sibling of fallbackSiblings) {
        sibling.element.inert = sibling.inert;
        if (sibling.ariaHidden === null) sibling.element.removeAttribute("aria-hidden");
        else sibling.element.setAttribute("aria-hidden", sibling.ariaHidden);
      }
      if (dialog.open) {
        try {
          dialog.close();
        } catch {
          dialog.removeAttribute("open");
        }
      }
      dialog.removeAttribute("aria-modal");
      previousFocusRef.current?.focus();
    };
  }, [impact, open]);

  const selectedRoute = useMemo(
    () => impact?.routes.find((route) => route.id === selectedRouteId) ?? impact?.routes[0] ?? null,
    [impact, selectedRouteId],
  );

  if (!open || !impact) return null;

  return (
      <dialog
        aria-labelledby="portfolio-drawer-title"
        className="portfolio-drawer"
        onCancel={(event) => {
          event.preventDefault();
          onClose();
        }}
        onClick={(event) => {
          if (event.target === event.currentTarget) onClose();
        }}
        ref={dialogRef}
      >
        <header className="drawer-header portfolio-drawer-header">
          <div>
            <span className="eyebrow">Decision simulation</span>
            <h2 id="portfolio-drawer-title">Portfolio impact</h2>
          </div>
          <button
            aria-label="Close"
            className="icon-button"
            onClick={onClose}
            ref={closeButtonRef}
          >
            <X size={19} />
          </button>
        </header>

        <div className="portfolio-drawer-content">
          <section className="simulation-boundary">
            <span className="simulation-icon">
              <FlaskConical size={17} />
            </span>
            <div>
              <div className="simulation-labels">
                <strong>Simulation only</strong>
                {impact.synthetic && <span>Synthetic demo</span>}
              </div>
              <p>No bid, staffing allocation, or external action has been changed.</p>
            </div>
          </section>

          <section className="portfolio-trigger-summary">
            <div className="portfolio-trigger-title">
              <span>
                <Network size={16} /> {impact.trigger.stable_key}
              </span>
              <small>{impact.trigger.change_summary}</small>
            </div>
            <h3>{impact.summary}</h3>
            <div className="state-boundary-row">
              <div>
                <small>Current bid</small>
                <StatusPill status={bidStatus} compact />
              </div>
              <div>
                <small>Portfolio before change</small>
                <StatusPill status={impact.before_state} compact />
              </div>
              <ArrowRight aria-hidden="true" size={15} />
              <div>
                <small>Portfolio after change</small>
                <StatusPill status={impact.after_state} compact />
              </div>
            </div>
            <p className="state-boundary-note">
              Bid-level readiness and cross-bid capacity are separate decisions.
            </p>
          </section>

          <section className="portfolio-section">
            <div className="portfolio-section-heading">
              <div>
                <span className="eyebrow">Shared capability</span>
                <h3>{impact.capacity.capability}</h3>
              </div>
              <span className="capacity-window">
                <CalendarRange size={13} />
                {formatWindow(impact.capacity.window_start, impact.capacity.window_end)}
              </span>
            </div>
            <div className="capacity-grid">
              <article>
                <span>Proven now</span>
                <strong>{impact.capacity.proven_now}</strong>
              </article>
              <article>
                <span>Potential after recovery</span>
                <strong>{impact.capacity.potential_after_recovery}</strong>
              </article>
              <article>
                <span>Concurrent demand</span>
                <strong>{impact.capacity.concurrent_required}</strong>
              </article>
              <article className="capacity-shortfall">
                <span>Remaining shortfall</span>
                <strong>{impact.capacity.shortfall}</strong>
              </article>
            </div>
            <p className="capacity-unit">Measured as {impact.capacity.unit} during the overlap.</p>
          </section>

          <section className="portfolio-section">
            <div className="portfolio-section-heading">
              <div>
                <span className="eyebrow">Affected pursuits</span>
                <h3>{impact.affected_bids.length} overlapping pursuits</h3>
              </div>
              <Users size={18} />
            </div>
            <div className="affected-bid-list">
              {impact.affected_bids.map((bid) => (
                <article key={bid.bid_id}>
                  <span className={`bid-relationship relationship-${bid.relationship.toLowerCase()}`}>
                    {bid.relationship === "CURRENT" ? "Current tender" : "Companion commitment"}
                  </span>
                  <div>
                    <strong>{bid.title}</strong>
                    <small>{bid.reference_number}</small>
                  </div>
                  <span className="bid-capacity">
                    <strong>{bid.required_capacity}</strong>
                    <small>required</small>
                  </span>
                </article>
              ))}
            </div>
          </section>

          <section className="portfolio-section">
            <div className="portfolio-section-heading">
              <div>
                <span className="eyebrow">Human-controlled options</span>
                <h3>Compare decision routes</h3>
              </div>
              <Route size={18} />
            </div>
            <p className="route-intro">
              These are deterministic consequences under stated assumptions, not recommendations.
            </p>
            <div aria-label="Portfolio decision routes" className="route-selector" role="group">
              {impact.routes.map((route) => (
                <button
                  aria-pressed={selectedRoute?.id === route.id}
                  className={selectedRoute?.id === route.id ? "selected" : ""}
                  key={route.id}
                  onClick={() => setSelectedRouteId(route.id)}
                >
                  <span className={`route-action action-${route.action.toLowerCase()}`}>
                    {route.action.replaceAll("_", " ")}
                  </span>
                  <strong>{route.label}</strong>
                  <span className="route-mini-outcomes">
                    {impact.affected_bids.map((bid) => {
                      const status = outcomeFor(route, bid.bid_id);
                      return (
                        <span key={bid.bid_id}>
                          <small>{bidLabel(bid)}</small>
                          {status && <StatusPill status={status} compact />}
                        </span>
                      );
                    })}
                  </span>
                </button>
              ))}
            </div>

            {selectedRoute && (
              <article aria-live="polite" className="selected-route-detail">
                <strong>{selectedRoute.label}</strong>
                <p>{selectedRoute.rationale}</p>
                <div className="selected-route-outcomes">
                  {impact.affected_bids.map((bid) => {
                    const status = outcomeFor(selectedRoute, bid.bid_id);
                    return (
                      <div key={bid.bid_id}>
                        <span>
                          <small>{bidLabel(bid)}</small>
                          <strong>{bid.reference_number}</strong>
                        </span>
                        {status && <StatusPill status={status} />}
                      </div>
                    );
                  })}
                </div>
                <div className="unresolved-facts">
                  <span>Facts still required</span>
                  {selectedRoute.unresolved_facts.length > 0 ? (
                    <ul>
                      {selectedRoute.unresolved_facts.map((fact) => (
                        <li key={fact}>{fact}</li>
                      ))}
                    </ul>
                  ) : (
                    <p>No unresolved external fact changes this simulated consequence.</p>
                  )}
                </div>
              </article>
            )}
          </section>

          {impact.capability_roadmap.length > 0 && (
            <section className="portfolio-section roadmap-section">
              <div className="portfolio-section-heading">
                <div>
                  <span className="eyebrow">Recurring capability gaps</span>
                  <h3>Capability next steps</h3>
                </div>
                <ShieldAlert size={18} />
              </div>
              <p className="route-intro">
                Based only on the supplied opportunities; these steps could address known eligibility
                checks, not predict awards or revenue.
              </p>
              <div className="roadmap-list">
                {impact.capability_roadmap.map((item) => (
                  <article key={`${item.priority}-${item.action}`}>
                    <span>{item.priority}</span>
                    <div>
                      <strong>{item.action}</strong>
                      <p>{item.effect}</p>
                      <small>{item.basis}</small>
                    </div>
                  </article>
                ))}
              </div>
            </section>
          )}

          <details className="simulation-trace">
            <summary>Assumptions and calculation</summary>
            <div>
              <strong>Assumptions</strong>
              <ul>
                {impact.assumptions.map((assumption) => (
                  <li key={assumption}>{assumption}</li>
                ))}
              </ul>
              <strong>Deterministic rule</strong>
              <p>{impact.calculation.rule}</p>
            </div>
          </details>

          <section className="simulation-scope-boundary">
            <ShieldAlert size={16} />
            <p>
              The companion commitment, service windows, and capability counts are synthetic demo
              inputs. This simulation does not use market prices, calculate win probability, or make
              an automatic bid decision.
            </p>
          </section>

          <section className="human-decision-boundary">
            <strong>Human decision required</strong>
            <p>BidOps compares operational consequences. Your team decides which pursuit to protect.</p>
          </section>
        </div>
      </dialog>
  );
}
