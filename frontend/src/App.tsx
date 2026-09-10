import {
  Activity,
  AlertCircle,
  ArrowDown,
  ArrowRight,
  BadgeCheck,
  CalendarClock,
  Check,
  CheckCircle2,
  CircleDot,
  Clock3,
  Database,
  FileDiff,
  FileSearch,
  Gauge,
  History,
  Info,
  ListChecks,
  LoaderCircle,
  LockKeyhole,
  Network,
  RefreshCcw,
  RotateCcw,
  ScanSearch,
  Shield,
  ShieldAlert,
  UserRoundCheck,
  Users,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { bidApi } from "./api/client";
import { ActivityDrawer } from "./components/ActivityDrawer";
import { AmendmentReviewDrawer } from "./components/AmendmentReviewDrawer";
import { MetricCard } from "./components/MetricCard";
import { PortfolioSimulationDrawer } from "./components/PortfolioSimulationDrawer";
import { RequirementDetail } from "./components/RequirementDetail";
import { RequirementTable } from "./components/RequirementTable";
import { StatusPill } from "./components/StatusPill";
import { TenderLabDrawer } from "./components/TenderLabDrawer";
import type { BidState, BidTask, DemoFixture, Requirement } from "./types/bid";

function parseUtc(value: string) {
  return new Date(value.endsWith("Z") ? value : `${value}Z`);
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-SG", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Asia/Singapore",
    timeZoneName: "short",
  }).format(parseUtc(value));
}

function formatShortDate(value: string) {
  return new Intl.DateTimeFormat("en-SG", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Asia/Singapore",
  }).format(parseUtc(value));
}

function formatCountdown(value: string, calculatedAt: string) {
  const diff = Math.max(0, parseUtc(value).getTime() - parseUtc(calculatedAt).getTime());
  const days = Math.floor(diff / 86_400_000);
  const hours = Math.floor((diff % 86_400_000) / 3_600_000);
  return `${days}d ${hours}h`;
}

function taskDateLabel(task: BidTask) {
  return formatShortDate(task.due_at);
}

function preferredRequirement(result: BidState) {
  const preferredKey = result.bid.fixture_id === "uncertain-ambiguous-clause" ? "R19" : "R17";
  return result.requirements.find((item) => item.stable_key === preferredKey)?.id ?? null;
}

function App() {
  const [data, setData] = useState<BidState | null>(null);
  const [fixtures, setFixtures] = useState<DemoFixture[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [mutating, setMutating] = useState(false);
  const [activityOpen, setActivityOpen] = useState(false);
  const [portfolioOpen, setPortfolioOpen] = useState(false);
  const [tenderLabOpen, setTenderLabOpen] = useState(false);
  const [amendmentOpen, setAmendmentOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [changed, setChanged] = useState(false);

  useEffect(() => {
    Promise.all([bidApi.get(), bidApi.listFixtures()])
      .then(([result, availableFixtures]) => {
        setData(result);
        setFixtures(availableFixtures);
        setSelectedId(preferredRequirement(result) ?? result.requirements[0]?.id ?? null);
      })
      .catch((reason: unknown) =>
        setError(reason instanceof Error ? reason.message : "Unable to load the bid."),
      )
      .finally(() => setLoading(false));
  }, []);

  const selected = useMemo(
    () => data?.requirements.find((item) => item.id === selectedId) ?? null,
    [data, selectedId],
  );

  async function resetDemo() {
    setMutating(true);
    setError(null);
    setPortfolioOpen(false);
    setAmendmentOpen(false);
    try {
      const result = await bidApi.reset();
      setData(result);
      setSelectedId(preferredRequirement(result));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to reset the demo.");
    } finally {
      setMutating(false);
    }
  }

  async function loadFixture(fixtureId: string) {
    setMutating(true);
    setError(null);
    setPortfolioOpen(false);
    setAmendmentOpen(false);
    try {
      const result = await bidApi.loadFixture(fixtureId);
      setData(result);
      setSelectedId(preferredRequirement(result));
      setChanged(true);
      window.setTimeout(() => setChanged(false), 1400);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load the demo fixture.");
    } finally {
      setMutating(false);
    }
  }

  if (loading) {
    return (
      <main className="loading-screen">
        <div className="brand-mark brand-mark-large">
          <Shield size={25} />
        </div>
        <strong>GeBIZ BidOps</strong>
        <span>Loading bid state</span>
        <LoaderCircle className="spin" size={20} />
      </main>
    );
  }

  if (!data) {
    return (
      <main className="loading-screen error-screen">
        <AlertCircle size={32} />
        <strong>Bid state unavailable</strong>
        <span>{error ?? "Start the FastAPI backend and refresh this page."}</span>
        <button onClick={() => window.location.reload()}>Try again</button>
      </main>
    );
  }

  const { metrics } = data;
  const coverage = data.calculations.submission_coverage;
  const deadline = data.calculations.deadline_risk;
  const activeFixture = fixtures.find((fixture) => fixture.id === data.bid.fixture_id);
  const hasChange = Boolean(data.latest_change);
  const recoveryTasks = data.tasks.filter((task) => task.recovery_path);
  const statusTone =
    metrics.operational_status === "FEASIBLE"
      ? "green"
      : metrics.operational_status === "RECOVERABLE"
        ? "amber"
        : metrics.operational_status === "BLOCKED"
          ? "red"
          : "slate";

  return (
    <div className="app-shell">
      <nav className="topbar">
        <div className="brand-lockup">
          <span className="brand-mark">
            <Shield size={18} />
          </span>
          <div>
            <strong>GeBIZ BidOps</strong>
            <small>Supplier-side bid control</small>
          </div>
        </div>
        <div className="topbar-context">
          <span
            className={`synthetic-badge interpretation-${data.interpretation.mode.toLowerCase()}`}
            title={
              data.interpretation.model_id
                ? `Live model: ${data.interpretation.model_id}`
                : "Built-in demo interpretation"
            }
          >
            <FileSearch size={12} /> Interpretation: {data.interpretation.label}
          </span>
          <span className="company-context">{data.company.name}</span>
          <label className="scenario-switcher" title={activeFixture?.description}>
            <span>Scenario</span>
            <select
              aria-label="Select demo scenario"
              value={data.bid.fixture_id}
              disabled={mutating}
              onChange={(event) => void loadFixture(event.target.value)}
            >
              {fixtures.map((fixture) => (
                <option key={fixture.id} value={fixture.id}>
                  {fixture.label}
                </option>
              ))}
            </select>
          </label>
          <button className="nav-button tender-lab-nav" onClick={() => setTenderLabOpen(true)}>
            <ScanSearch size={16} /> Tender Lab
          </button>
          <button className="nav-button" onClick={() => setActivityOpen(true)}>
            <Activity size={16} /> Activity
            <span>{data.activity_events.length}</span>
          </button>
          <button
            className="icon-button dark"
            onClick={resetDemo}
            disabled={mutating}
            title="Reset demo"
          >
            <RotateCcw size={17} />
          </button>
        </div>
      </nav>

      <header className="bid-hero">
        <div className="hero-grid-glow" />
        <div className="hero-content page-width">
          <div className="hero-main">
            <div className="hero-kicker">
              <span>{data.bid.agency}</span>
              <CircleDot size={10} />
              <span>{data.bid.reference_number}</span>
            </div>
            <h1>{data.bid.title}</h1>
            <p>
              Bid readiness for <strong>{data.company.name}</strong>
            </p>
          </div>
          <div className="hero-deadline">
            <span>Submission closes in</span>
            <strong>
              {formatCountdown(data.bid.closing_at, data.calculations.deadline_risk.calculated_at)}
            </strong>
            <small>
              <CalendarClock size={13} /> {formatDate(data.bid.closing_at)}
            </small>
          </div>
          <div className="hero-action">
            {hasChange ? (
              <button className="corrigendum-button applied" onClick={resetDemo} disabled={mutating}>
                <CheckCircle2 size={18} />
                <span>
                  Corrigendum #2 applied
                  <small>Reset to replay the state change</small>
                </span>
                <RefreshCcw size={15} />
              </button>
            ) : data.bid.fixture_id === "main-corrigendum" ? (
              <button
                className="corrigendum-button"
                onClick={() => setAmendmentOpen(true)}
                disabled={mutating}
              >
                <FileDiff size={18} />
                <span>
                  Review Corrigendum #2
                  <small>Preview impact before update</small>
                </span>
                <ArrowRight size={17} />
              </button>
            ) : (
              <button
                className="corrigendum-button fixture-active"
                onClick={() => void loadFixture("main-corrigendum")}
                disabled={mutating}
              >
                <ShieldAlert size={18} />
                <span>
                  {metrics.operational_status} fixture active
                  <small>Return to the main scenario</small>
                </span>
                <RefreshCcw size={15} />
              </button>
            )}
          </div>
        </div>
      </header>

      <main className="page-width main-content">
        {error && (
          <div className="error-banner">
            <AlertCircle size={17} />
            <span>{error}</span>
            <button onClick={() => setError(null)} aria-label="Dismiss error">
              <X size={15} />
            </button>
          </div>
        )}

        <section className={`metrics-grid ${changed ? "state-changed" : ""}`}>
          <MetricCard
            label="Operational Feasibility"
            value={metrics.operational_status}
            previous={metrics.previous_operational_status}
            caption={data.calculations.operational_feasibility.reason}
            icon={metrics.operational_status === "FEASIBLE" ? Shield : ShieldAlert}
            tone={statusTone}
            hero
          />
          <MetricCard
            label="Critical Gates"
            value={`${metrics.critical_gates_verified} / ${metrics.critical_gates_total}`}
            caption={
              metrics.critical_gates_verified === metrics.critical_gates_total
                ? "Every mandatory obligation is verified"
                : metrics.operational_status === "UNCERTAIN"
                  ? `${metrics.critical_gates_total - metrics.critical_gates_verified} mandatory gate requires clarification`
                  : metrics.operational_status === "BLOCKED"
                    ? `${metrics.critical_gates_total - metrics.critical_gates_verified} mandatory gate is blocked`
                    : `${metrics.critical_gates_total - metrics.critical_gates_verified} mandatory gate requires recovery`
            }
            icon={BadgeCheck}
            tone={metrics.critical_gates_verified === metrics.critical_gates_total ? "green" : "amber"}
          />
          <MetricCard
            label="Submission Coverage"
            value={`${metrics.submission_coverage}%`}
            caption="Preparation completeness · not a compliance score"
            icon={Gauge}
            tone="blue"
          />
          <MetricCard
            label="Deadline Risk"
            value={metrics.deadline_risk}
            caption={
              deadline.driver_task_title && deadline.minimum_slack_hours !== null
                ? `${deadline.driver_task_title} · ${deadline.minimum_slack_hours}h slack`
                : "No open task currently drives deadline risk"
            }
            icon={Clock3}
            tone={metrics.deadline_risk === "LOW" ? "green" : metrics.deadline_risk === "MEDIUM" ? "amber" : "red"}
          />
        </section>

        <section className="panel coverage-breakdown">
          <div className="coverage-heading">
            <div>
              <span className="eyebrow">How the score is built</span>
              <h2>Submission Coverage</h2>
            </div>
            <span className="trace-badge">
              <CheckCircle2 size={13} /> Calculated from current bid data
            </span>
          </div>
          <div className="coverage-components">
            {(
              [
                ["requirements", Shield],
                ["evidence", Database],
                ["tasks", ListChecks],
              ] as const
            ).map(([key, Icon]) => {
              const component = coverage.components[key];
              return (
                <article className="coverage-component" key={key} title={component.rule}>
                  <span className="coverage-icon">
                    <Icon size={15} />
                  </span>
                  <div>
                    <strong>{component.label}</strong>
                    <small>
                      {component.completed_units} / {component.total_units} {component.unit_label}
                    </small>
                    <span className="coverage-track">
                      <i style={{ width: `${component.percent}%` }} />
                    </span>
                  </div>
                  <div className="coverage-math">
                    <span>
                      {component.percent}% × {component.weight * 100}%
                    </span>
                    <strong>{component.weighted_points} pts</strong>
                  </div>
                </article>
              );
            })}
          </div>
          <div className="coverage-total">
            <Info size={14} />
            <span>{coverage.formula}</span>
            <strong>
              {coverage.raw_percent}% → {coverage.display_percent}%
            </strong>
          </div>
          <p>{coverage.warning}</p>
        </section>

        <section className="summary-grid">
          <article className="panel actions-panel">
            <div className="panel-heading">
              <div>
                <span className="eyebrow">What needs attention</span>
                <h2>{hasChange ? "Recovery Actions" : "Critical Actions"}</h2>
              </div>
              <span className={`action-count ${hasChange ? "urgent" : ""}`}>
                {hasChange ? recoveryTasks.length : data.critical_actions.length} open
              </span>
            </div>
            <div className="action-list">
              {(hasChange ? recoveryTasks : data.critical_actions).slice(0, 4).map((task, index) => (
                <div className="action-row" key={task.id}>
                  <span className={`action-index priority-${task.priority.toLowerCase()}`}>
                    {task.status === "WAITING" ? <LockKeyhole size={14} /> : index + 1}
                  </span>
                  <div>
                    <strong>{task.title}</strong>
                    <small>
                      {task.owner} · {taskDateLabel(task)}
                    </small>
                  </div>
                  <div className="action-status">
                    <span>{task.priority}</span>
                    {task.depends_on.length > 0 && (
                      <small>
                        {task.depends_on.length} {task.depends_on.length === 1 ? "dependency" : "dependencies"}
                      </small>
                    )}
                  </div>
                </div>
              ))}
            </div>
            {hasChange && recoveryTasks.length > 0 && (
              <div className="safe-date">
                <CalendarClock size={16} />
                <span>
                  Complete verification by
                  <strong>{formatDate(recoveryTasks.at(-1)?.latest_safe_at ?? recoveryTasks.at(-1)!.due_at)}</strong>
                </span>
              </div>
            )}
          </article>

          <article className={`panel change-panel ${hasChange ? "active-change" : ""}`}>
            <div className="panel-heading">
              <div>
                <span className="eyebrow">Latest change</span>
                <h2>{data.latest_change?.title ?? "No unresolved amendments"}</h2>
              </div>
              {hasChange ? <FileDiff size={21} /> : <CheckCircle2 size={21} />}
            </div>
            {data.latest_change ? (
              <>
                <div className="diff-grid">
                  <div className="diff-old">
                    <span>
                      Previous · {data.latest_change.stable_key} v
                      {data.latest_change.old_version ?? 1}
                    </span>
                    {data.latest_change.display_kind === "TEXT" ? (
                      <p className="diff-requirement-text">{data.latest_change.old}</p>
                    ) : (
                      <>
                        <strong>{data.latest_change.old_count}</strong>
                        <p>{data.latest_change.subject_label ?? "CISSP-certified engineers"}</p>
                      </>
                    )}
                    <StatusPill status={data.latest_change.old_assessment} compact />
                  </div>
                  <div className="diff-arrow">
                    <ArrowRight size={20} />
                  </div>
                  <div className="diff-new">
                    <span>
                      Current · {data.latest_change.stable_key} v
                      {data.latest_change.new_version ?? 2}
                    </span>
                    {data.latest_change.display_kind === "TEXT" ? (
                      <p className="diff-requirement-text">{data.latest_change.new}</p>
                    ) : (
                      <>
                        <strong>{data.latest_change.new_count}</strong>
                        <p>{data.latest_change.subject_label ?? "CISSP-certified engineers"}</p>
                      </>
                    )}
                    <StatusPill status={data.latest_change.new_assessment} compact />
                  </div>
                </div>
                <div className="impact-stats">
                  <span>
                    <strong>{data.latest_change.impact.critical_gates_broken}</strong> gate broken
                  </span>
                  <span>
                    <strong>{data.latest_change.impact.assessments_superseded}</strong> assessment superseded
                  </span>
                  <span>
                    <strong>{data.latest_change.impact.recovery_paths_found}</strong> recovery path
                  </span>
                </div>
                {data.portfolio_impact && (
                  <div className="portfolio-impact-trigger">
                    <span className="portfolio-trigger-icon">
                      <Network size={16} />
                    </span>
                    <div>
                      <span className="portfolio-trigger-kicker">
                        Cross-bid impact
                        {data.portfolio_impact.synthetic && <em>Synthetic demo</em>}
                      </span>
                      <strong>{data.portfolio_impact.summary}</strong>
                      <small>
                        {data.portfolio_impact.capacity.concurrent_required} required across{" "}
                        {data.portfolio_impact.affected_bids.length} pursuits ·{" "}
                        {data.portfolio_impact.capacity.potential_after_recovery} potential · shortfall{" "}
                        {data.portfolio_impact.capacity.shortfall}
                      </small>
                    </div>
                    <button onClick={() => setPortfolioOpen(true)}>
                      Compare {data.portfolio_impact.routes.length} routes
                      <ArrowRight size={14} />
                    </button>
                  </div>
                )}
              </>
            ) : (
              <div className="no-change-state">
                <span className="no-change-icon">
                  <Check size={18} />
                </span>
                <div>
                  <strong>Assessments are current</strong>
                  <p>No later amendment has changed a verified requirement.</p>
                </div>
              </div>
            )}
          </article>

          {data.recovery_candidate && (
            <article className="panel candidate-panel">
              <div className="panel-heading">
                <div>
                  <span className="eyebrow">Potential recovery candidate</span>
                  <h2>Evidence gap review</h2>
                </div>
                <Users size={21} />
              </div>
              <div className="candidate-person">
                <span className="avatar">
                  {data.recovery_candidate.name
                    .split(" ")
                    .slice(0, 2)
                    .map((part) => part[0])
                    .join("")}
                </span>
                <div>
                  <strong>{data.recovery_candidate.name}</strong>
                  <small>{data.recovery_candidate.role}</small>
                </div>
                <StatusPill status={metrics.operational_status} compact />
              </div>
              <div className="candidate-checks">
                <div>
                  <span>
                    <BadgeCheck size={15} />
                    {data.recovery_candidate.certification_name ?? "Certification"}
                  </span>
                  <StatusPill status={data.recovery_candidate.certification} compact />
                </div>
                <div>
                  <span>
                    <FileSearch size={15} /> Current CV
                  </span>
                  <StatusPill status={data.recovery_candidate.cv} compact />
                </div>
                <div>
                  <span>
                    <UserRoundCheck size={15} /> Availability
                  </span>
                  <StatusPill status={data.recovery_candidate.availability} compact />
                </div>
              </div>
              <p className="candidate-warning">
                <AlertCircle size={15} /> This candidate counts only after every evidence gap is closed.
              </p>
            </article>
          )}
        </section>

        {data.impact_chain.length > 0 && (
          <section className="panel impact-panel">
            <div className="impact-title">
              <span className="eyebrow">Change propagation</span>
              <h2>Impact Chain</h2>
            </div>
            <div className="impact-chain">
              {data.impact_chain.map((item, index) => (
                <div className="impact-segment" key={item.label}>
                  <div className={`impact-node impact-node-${index}`}>
                    <span>{index + 1}</span>
                    <div>
                      <strong>{item.label}</strong>
                      <small>{item.detail}</small>
                    </div>
                  </div>
                  {index < data.impact_chain.length - 1 && (
                    <span className="impact-arrow">
                      <ArrowRight size={18} />
                      <ArrowDown size={18} />
                    </span>
                  )}
                </div>
              ))}
            </div>
          </section>
        )}

        <section className="requirements-layout">
          <RequirementTable
            requirements={data.requirements}
            selectedId={selectedId}
            onSelect={(requirement: Requirement) => setSelectedId(requirement.id)}
          />
          {selected && <RequirementDetail requirement={selected} />}
        </section>

      </main>

      <footer className="app-footer">
        <div className="page-width">
          <span>
            <Shield size={14} /> GeBIZ BidOps
          </span>
          <button onClick={() => setActivityOpen(true)}>
            <History size={14} /> View audit activity
          </button>
        </div>
      </footer>

      <ActivityDrawer
        open={activityOpen}
        onClose={() => setActivityOpen(false)}
        events={data.activity_events}
      />

      <PortfolioSimulationDrawer
        open={portfolioOpen}
        onClose={() => setPortfolioOpen(false)}
        impact={data.portfolio_impact}
        bidStatus={metrics.operational_status}
      />

      <TenderLabDrawer open={tenderLabOpen} onClose={() => setTenderLabOpen(false)} />

      {amendmentOpen && (
        <AmendmentReviewDrawer
          bid={data}
          onApplied={(result) => {
            setData(result);
            setSelectedId(preferredRequirement(result));
            setChanged(true);
            window.setTimeout(() => setChanged(false), 1900);
          }}
          onClose={() => setAmendmentOpen(false)}
          open
        />
      )}
    </div>
  );
}

export default App;
