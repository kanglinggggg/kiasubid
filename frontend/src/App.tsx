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
  ClipboardCheck,
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
  RefreshCcw,
  RotateCcw,
  Shield,
  ShieldAlert,
  Sparkles,
  UserRoundCheck,
  Users,
  X,
  Zap,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { bidApi } from "./api/client";
import { ActivityDrawer } from "./components/ActivityDrawer";
import { MetricCard } from "./components/MetricCard";
import { RequirementDetail } from "./components/RequirementDetail";
import { RequirementTable } from "./components/RequirementTable";
import { StatusPill } from "./components/StatusPill";
import type { BidState, BidTask, DemoFixture, Requirement } from "./types/bid";

const workflowStages = [
  "Reading Corrigendum #2",
  "Matching changed obligation",
  "Versioning R17 and superseding prior assessment",
  "Rechecking the Evidence Registry",
  "Planning recovery actions and deadlines",
];

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
  const [workflowRunning, setWorkflowRunning] = useState(false);
  const [workflowStage, setWorkflowStage] = useState(0);
  const [activityOpen, setActivityOpen] = useState(false);
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

  async function applyCorrigendum() {
    setMutating(true);
    setWorkflowRunning(true);
    setWorkflowStage(0);
    setError(null);
    const timer = window.setInterval(
      () => setWorkflowStage((stage) => Math.min(stage + 1, workflowStages.length - 1)),
      360,
    );
    try {
      const [result] = await Promise.all([
        bidApi.applyCorrigendum(),
        new Promise((resolve) => window.setTimeout(resolve, 1900)),
      ]);
      setData(result);
      setSelectedId(preferredRequirement(result));
      setChanged(true);
      window.setTimeout(() => setChanged(false), 1900);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The corrigendum workflow failed.");
    } finally {
      window.clearInterval(timer);
      setWorkflowRunning(false);
      setMutating(false);
    }
  }

  async function resetDemo() {
    setMutating(true);
    setError(null);
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

  async function approvePackage() {
    setMutating(true);
    setError(null);
    try {
      setData(await bidApi.approve());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to record approval.");
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
        <span>Loading trustworthy bid state</span>
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
                : "Canonical rule-based fallback"
            }
          >
            <Sparkles size={12} /> Interpretation: {data.interpretation.label}
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
              Live obligation state for <strong>{data.company.name}</strong>
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
              <button className="corrigendum-button" onClick={applyCorrigendum} disabled={mutating}>
                <Zap size={18} fill="currentColor" />
                <span>
                  Apply Corrigendum #2
                  <small>Run impact workflow</small>
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
              <span className="eyebrow">Deterministic calculation</span>
              <h2>Submission Coverage breakdown</h2>
            </div>
            <span className="trace-badge">
              <CheckCircle2 size={13} /> Backend state traced
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
                    {task.depends_on.length > 0 && <small>{task.depends_on.length} dependencies</small>}
                  </div>
                </div>
              ))}
            </div>
            {hasChange && recoveryTasks.length > 0 && (
              <div className="safe-date">
                <CalendarClock size={16} />
                <span>
                  Latest safe verification
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
                    <span>Previous · {data.latest_change.stable_key} v1</span>
                    <strong>{data.latest_change.old_count}</strong>
                    <p>CISSP-certified engineers</p>
                    <StatusPill status={data.latest_change.old_assessment} compact />
                  </div>
                  <div className="diff-arrow">
                    <ArrowRight size={20} />
                  </div>
                  <div className="diff-new">
                    <span>Current · {data.latest_change.stable_key} v2</span>
                    <strong>{data.latest_change.new_count}</strong>
                    <p>CISSP-certified engineers</p>
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
              </>
            ) : (
              <div className="no-change-state">
                <span className="no-change-icon">
                  <Check size={18} />
                </span>
                <div>
                  <strong>Bid truth is current</strong>
                  <p>No later document has invalidated a verified assessment.</p>
                </div>
              </div>
            )}
          </article>

          {data.recovery_candidate && (
            <article className="panel candidate-panel">
              <div className="panel-heading">
                <div>
                  <span className="eyebrow">Evidence Registry match</span>
                  <h2>Recovery Candidate</h2>
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
                    <BadgeCheck size={15} /> CISSP
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
                <AlertCircle size={15} /> Candidate found does not equal requirement satisfied.
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

        <section className={`human-review ${data.human_review.approved ? "approved" : ""}`}>
          <div className="human-icon">
            {data.human_review.approved ? <CheckCircle2 size={23} /> : <UserRoundCheck size={23} />}
          </div>
          <div className="human-copy">
            <span className="eyebrow">Final Human Review</span>
            <h2>
              {data.human_review.approved
                ? `Internal package approved by ${data.human_review.approved_by}`
                : "Automated analysis completed. Submission remains human-controlled."}
            </h2>
            <p>{data.disclaimer}</p>
          </div>
          <button
            className="approval-button"
            disabled={
              metrics.operational_status !== "FEASIBLE" || data.human_review.approved || mutating
            }
            onClick={approvePackage}
          >
            {data.human_review.approved ? <Check size={16} /> : <ClipboardCheck size={16} />}
            {data.human_review.approved ? "Approval recorded" : "Approve Internal Bid Package"}
          </button>
          {metrics.operational_status !== "FEASIBLE" && (
            <small className="approval-lock">
              <LockKeyhole size={12} /> Resolve the mandatory gate before approval
            </small>
          )}
        </section>
      </main>

      <footer className="app-footer">
        <div className="page-width">
          <span>
            <Shield size={14} /> GeBIZ BidOps
          </span>
          <p>LLM interpretation is bounded. Versioning, evidence, gates, recovery, and deadlines remain deterministic.</p>
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

      {workflowRunning && workflowStage >= 0 && (
        <div className="workflow-overlay" aria-live="polite">
          <div className="workflow-card">
            <div className="workflow-orbit">
              <span />
              <Zap size={20} fill="currentColor" />
            </div>
            <span className="eyebrow">LangGraph workflow running</span>
            <h2>{workflowStages[workflowStage]}</h2>
            <p>Updating persistent bid state and downstream obligations…</p>
            <div className="workflow-progress">
              {workflowStages.map((stage, index) => (
                <span
                  key={stage}
                  className={index < workflowStage ? "done" : index === workflowStage ? "active" : ""}
                />
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
