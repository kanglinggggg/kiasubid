import {
  AlertTriangle,
  ArrowRight,
  Check,
  CheckCircle2,
  Clipboard,
  Copy,
  FileCheck2,
  FileDiff,
  Fingerprint,
  GitCompareArrows,
  ListTree,
  LoaderCircle,
  LockKeyhole,
  RotateCcw,
  ShieldCheck,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { amendmentApi } from "../api/client";
import type { AmendmentPreviewResponse } from "../types/amendment";
import type { BidState } from "../types/bid";

function labelField(value: string) {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-SG", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Asia/Singapore",
    timeZoneName: "short",
  }).format(new Date(value.endsWith("Z") ? value : `${value}Z`));
}

function stateLabel(state: AmendmentPreviewResponse["state"]) {
  if (state === "PREVIEW_READY") return "Preview ready";
  if (state === "NO_TRACKED_CHANGE") return "No tracked change";
  return "Review required";
}

interface AmendmentReviewDrawerProps {
  open: boolean;
  bid: BidState;
  onClose: () => void;
  onApplied: (bid: BidState) => void;
}

export function AmendmentReviewDrawer({
  open,
  bid,
  onClose,
  onApplied,
}: AmendmentReviewDrawerProps) {
  const defaultRequirement = useMemo(
    () => bid.requirements.find((item) => item.stable_key === "R17") ?? bid.requirements[0],
    [bid.requirements],
  );
  const [requirementId, setRequirementId] = useState(defaultRequirement?.id ?? "");
  const [documentName, setDocumentName] = useState("");
  const [documentVersion, setDocumentVersion] = useState(1);
  const [page, setPage] = useState(1);
  const [section, setSection] = useState("");
  const [text, setText] = useState("");
  const [preview, setPreview] = useState<AmendmentPreviewResponse | null>(null);
  const [analysing, setAnalysing] = useState(false);
  const [applying, setApplying] = useState(false);
  const [reviewed, setReviewed] = useState(false);
  const [confirmedBy, setConfirmedBy] = useState("Bid owner");
  const [copied, setCopied] = useState(false);
  const [workspaceUpdated, setWorkspaceUpdated] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    const currentIds = new Set(bid.requirements.map((item) => item.id));
    if (!currentIds.has(requirementId)) {
      setRequirementId(defaultRequirement?.id ?? "");
      if (!workspaceUpdated) {
        setText("");
        setPreview(null);
        setReviewed(false);
        setCopied(false);
        setError(null);
      }
    }
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !analysing && !applying) onClose();
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [
    analysing,
    applying,
    bid.requirements,
    defaultRequirement?.id,
    onClose,
    open,
    requirementId,
    workspaceUpdated,
  ]);

  function invalidatePreview() {
    setPreview(null);
    setReviewed(false);
    setWorkspaceUpdated(false);
    setCopied(false);
    setError(null);
  }

  async function analyse() {
    if (!requirementId || !text.trim()) return;
    setAnalysing(true);
    setError(null);
    setPreview(null);
    setReviewed(false);
    setWorkspaceUpdated(false);
    try {
      const result = await amendmentApi.preview(bid.bid.id, {
        requirement_id: requirementId,
        source: {
          document_name: documentName.trim(),
          document_version: documentVersion,
          page,
          section: section.trim(),
          text: text.trim(),
        },
      });
      setPreview(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to analyse this amendment.");
    } finally {
      setAnalysing(false);
    }
  }

  async function applyPreview() {
    if (!preview || !preview.apply_allowed || !reviewed || !confirmedBy.trim()) return;
    setApplying(true);
    setError(null);
    try {
      const result = await amendmentApi.apply(bid.bid.id, {
        preview_id: preview.preview_id,
        reviewed_source_and_diff: true,
        confirmed_by: confirmedBy.trim(),
      });
      setWorkspaceUpdated(true);
      onApplied(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to update the workspace.");
    } finally {
      setApplying(false);
    }
  }

  async function copyClarification() {
    if (!preview?.clarification) return;
    await navigator.clipboard.writeText(preview.clarification.question);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  }

  if (!open) return null;

  return (
    <div className="amendment-backdrop" role="presentation">
      <section
        aria-label="Amendment review"
        aria-modal="true"
        className="amendment-drawer"
        role="dialog"
      >
        <header className="amendment-header">
          <div className="amendment-title-lockup">
            <span className="amendment-logo">
              <FileDiff size={18} />
            </span>
            <div>
              <span>Versioned bid workspace</span>
              <h2>Amendment Review</h2>
            </div>
          </div>
          <div className="amendment-header-context">
            <span>{bid.bid.reference_number}</span>
            <strong>{bid.company.name}</strong>
          </div>
          <button aria-label="Close amendment review" className="amendment-close" onClick={onClose}>
            <X size={19} />
          </button>
        </header>

        <div className="amendment-boundary">
          <ShieldCheck size={14} />
          <span>
            <strong>Preview first</strong>
            No record changes until a person confirms  No GeBIZ action or submission
          </span>
        </div>

        <div className="amendment-workspace">
          <aside className="amendment-inputs">
            <div className="amendment-input-heading">
              <span>Source and target</span>
              <h3>What changed</h3>
              <p>Select the tracked obligation and paste the exact amendment wording.</p>
            </div>

            <label className="amendment-field">
              <span>Tracked requirement</span>
              <select
                aria-label="Tracked requirement"
                onChange={(event) => {
                  setRequirementId(event.target.value);
                  invalidatePreview();
                }}
                value={requirementId}
              >
                {bid.requirements.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.stable_key} v{item.version} · {item.text}
                  </option>
                ))}
              </select>
            </label>

            <div className="amendment-field-grid amendment-field-grid-source">
              <label className="amendment-field amendment-field-wide">
                <span>Source document</span>
                <input
                  aria-label="Source document"
                  onChange={(event) => {
                    setDocumentName(event.target.value);
                    invalidatePreview();
                  }}
                  value={documentName}
                />
              </label>
              <label className="amendment-field">
                <span>Version</span>
                <input
                  aria-label="Document version"
                  min={1}
                  onChange={(event) => {
                    setDocumentVersion(Number(event.target.value));
                    invalidatePreview();
                  }}
                  type="number"
                  value={documentVersion}
                />
              </label>
              <label className="amendment-field">
                <span>Page</span>
                <input
                  aria-label="Source page"
                  min={1}
                  onChange={(event) => {
                    setPage(Number(event.target.value));
                    invalidatePreview();
                  }}
                  type="number"
                  value={page}
                />
              </label>
            </div>

            <label className="amendment-field">
              <span>Section</span>
              <input
                aria-label="Source section"
                onChange={(event) => {
                  setSection(event.target.value);
                  invalidatePreview();
                }}
                value={section}
              />
            </label>

            <label className="amendment-field amendment-source-text">
              <span>Exact amendment wording</span>
              <textarea
                aria-label="Exact amendment wording"
                onChange={(event) => {
                  setText(event.target.value);
                  invalidatePreview();
                }}
                value={text}
              />
              <small>{text.length.toLocaleString()} characters  User supplied</small>
            </label>

            {error && !preview && (
              <div className="amendment-error">
                <AlertTriangle size={15} /> {error}
              </div>
            )}

            <button
              className="amendment-analyse"
              disabled={analysing || !text.trim() || !requirementId}
              onClick={() => void analyse()}
              type="button"
            >
              {analysing ? <LoaderCircle className="spin" size={16} /> : <GitCompareArrows size={16} />}
              <span>{analysing ? "Analysing amendment" : "Analyse amendment"}</span>
              {!analysing && <ArrowRight size={15} />}
            </button>

            <p className="amendment-input-note">
              <LockKeyhole size={13} /> Preview reads current workspace data only and expires after 30 minutes.
            </p>
          </aside>

          <main aria-live="polite" className="amendment-results">
            {!preview ? (
              <div className="amendment-empty">
                <div className="amendment-empty-mark">
                  <GitCompareArrows size={28} />
                </div>
                <span>Preview workspace</span>
                <h3>See the ripple effect before changing the bid</h3>
                <p>
                  The workflow matches the selected obligation  validates an exact source  rechecks evidence  predicts internal metrics  and plans recovery tasks
                </p>
                <div className="amendment-empty-flow">
                  {[
                    "Source",
                    "Match",
                    "Diff",
                    "Impact",
                    "Human confirm",
                  ].map((item, index) => (
                    <div key={item}>
                      <span>{index + 1}</span>
                      <strong>{item}</strong>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="amendment-preview">
                <div className={`amendment-result-head state-${preview.state.toLowerCase()}`}>
                  <div>
                    <span className="amendment-state-label">
                      {preview.state === "PREVIEW_READY" ? (
                        <CheckCircle2 size={14} />
                      ) : (
                        <AlertTriangle size={14} />
                      )}
                      {stateLabel(preview.state)}
                    </span>
                    <h3>{preview.reason_summary}</h3>
                    <p>
                      {preview.interpretation_mode === "DEMO_FALLBACK"
                        ? "Rules-based interpretation"
                        : `AI-assisted interpretation · ${preview.model_id ?? "configured model"}`}
                      {"  "}Preview {preview.preview_id.slice(0, 8)}
                    </p>
                  </div>
                  <span className="amendment-write-state">
                    {preview.apply_allowed ? <FileCheck2 size={15} /> : <LockKeyhole size={15} />}
                    {preview.apply_allowed ? "Write locked until confirmation" : "Write blocked"}
                  </span>
                </div>

                <div className="amendment-result-body">
                  <section className="amendment-card amendment-source-proof">
                    <div className="amendment-card-heading">
                      <span className="amendment-card-icon"><Fingerprint size={16} /></span>
                      <div>
                        <span>Source evidence</span>
                        <h4>{preview.source.document_name}</h4>
                      </div>
                      <code>{preview.source.sha256.slice(0, 12)}…</code>
                    </div>
                    <div className="amendment-source-meta">
                      <span>Version {preview.source.document_version}</span>
                      <span>Page {preview.source.page}</span>
                      <span>{preview.source.section}</span>
                      <strong>User-supplied exact text</strong>
                    </div>
                    <blockquote>{preview.source.exact_excerpt}</blockquote>
                  </section>

                  <section className="amendment-card">
                    <div className="amendment-card-heading">
                      <span className="amendment-card-icon"><GitCompareArrows size={16} /></span>
                      <div>
                        <span>Proposed internal update</span>
                        <h4>
                          {preview.proposed
                            ? `${preview.target.stable_key} v${preview.target.version} → v${preview.proposed.version}`
                            : `${preview.target.stable_key} v${preview.target.version} · no version proposed`}
                        </h4>
                      </div>
                      <strong className="amendment-change-type">{preview.change_type}</strong>
                    </div>
                    {preview.changed_fields.length > 0 ? (
                      <div className="amendment-diffs">
                        {preview.changed_fields.map((field) => (
                          <article key={field.field}>
                            <span>{labelField(field.field)}</span>
                            <div className="amendment-diff-values">
                              <p>{field.old_value}</p>
                              <ArrowRight size={15} />
                              <p>{field.new_value}</p>
                            </div>
                          </article>
                        ))}
                      </div>
                    ) : (
                      <p className="amendment-no-diff">No validated field change is available.</p>
                    )}
                  </section>

                  {preview.impact && (
                    <section className="amendment-card">
                      <div className="amendment-card-heading">
                        <span className="amendment-card-icon"><ListTree size={16} /></span>
                        <div>
                          <span>Projected consequences</span>
                          <h4>Current workspace → projected workspace</h4>
                        </div>
                        <strong className="amendment-simulation-badge">No write</strong>
                      </div>
                      <div className="amendment-impact-grid">
                        {[
                          ["Assessment", preview.impact.assessment_before, preview.impact.assessment_after],
                          ["Bid status", preview.impact.operational_status_before, preview.impact.operational_status_after],
                          ["Critical gates", preview.impact.critical_gates_before, preview.impact.critical_gates_after],
                          ["Coverage", `${preview.impact.submission_coverage_before}%`, `${preview.impact.submission_coverage_after}%`],
                          ["Deadline risk", preview.impact.deadline_risk_before, preview.impact.deadline_risk_after],
                        ].map(([label, before, after]) => (
                          <article key={label}>
                            <span>{label}</span>
                            <div>
                              <strong>{before}</strong>
                              <ArrowRight size={13} />
                              <strong>{after}</strong>
                            </div>
                          </article>
                        ))}
                      </div>
                      <p className="amendment-calculation-note">{preview.impact.calculation_note}</p>
                    </section>
                  )}

                  {preview.planned_tasks.length > 0 && (
                    <section className="amendment-card">
                      <div className="amendment-card-heading">
                        <span className="amendment-card-icon"><ListTree size={16} /></span>
                        <div>
                          <span>Proposed recovery plan</span>
                          <h4>{preview.planned_tasks.length} dependency-aware tasks</h4>
                        </div>
                      </div>
                      <div className="amendment-task-plan">
                        {preview.planned_tasks.map((task, index) => (
                          <article key={task.key}>
                            <span className="amendment-task-index">{index + 1}</span>
                            <div>
                              <strong>{task.title}</strong>
                              <p>{task.description}</p>
                              <small>
                                {task.owner}  {formatDate(task.due_at)}
                                {task.depends_on.length > 0 && `  after ${task.depends_on.join(" + ")}`}
                              </small>
                            </div>
                            <span className={`amendment-task-status status-${task.status.toLowerCase()}`}>
                              {task.status}
                            </span>
                          </article>
                        ))}
                      </div>
                    </section>
                  )}

                  {preview.clarification && (
                    <section className="amendment-card amendment-clarification">
                      <div className="amendment-card-heading">
                        <span className="amendment-card-icon"><AlertTriangle size={16} /></span>
                        <div>
                          <span>Safe stop</span>
                          <h4>Clarification needed</h4>
                        </div>
                        <strong>Copy only</strong>
                      </div>
                      <p>{preview.clarification.reason}</p>
                      <blockquote>{preview.clarification.question}</blockquote>
                      <button onClick={() => void copyClarification()} type="button">
                        {copied ? <Check size={14} /> : <Copy size={14} />}
                        {copied ? "Copied" : "Copy clarification draft"}
                      </button>
                    </section>
                  )}

                  <section className="amendment-card amendment-trace-card">
                    <div className="amendment-card-heading">
                      <span className="amendment-card-icon"><Clipboard size={16} /></span>
                      <div>
                        <span>Workflow trace</span>
                        <h4>Why the workflow stopped here</h4>
                      </div>
                    </div>
                    <div className="amendment-trace">
                      {preview.workflow_trace.map((item) => (
                        <article key={`${item.step}-${item.node}`}>
                          <span className={`trace-${item.status.toLowerCase()}`}>
                            {item.status === "DONE" ? <Check size={12} /> : item.status === "BLOCKED" ? <X size={12} /> : "–"}
                          </span>
                          <div>
                            <strong>{item.node.replaceAll("_", " ")}</strong>
                            <p>{item.detail}</p>
                          </div>
                        </article>
                      ))}
                    </div>
                  </section>

                  <section className={`amendment-checkpoint ${preview.apply_allowed ? "ready" : "blocked"}`}>
                    <div className="amendment-checkpoint-copy">
                      <span>{preview.apply_allowed ? <ShieldCheck size={18} /> : <LockKeyhole size={18} />}</span>
                      <div>
                        <strong>{workspaceUpdated ? "Workspace updated" : "Human checkpoint"}</strong>
                        <p>
                          {workspaceUpdated
                            ? "The new requirement version  reassessment  tasks and audit events are now in the internal workspace"
                            : preview.human_checkpoint}
                        </p>
                      </div>
                    </div>

                    {error && (
                      <div className="amendment-error">
                        <AlertTriangle size={15} /> {error}
                      </div>
                    )}

                    {workspaceUpdated ? (
                      <button className="amendment-return" onClick={onClose} type="button">
                        <CheckCircle2 size={16} /> Return to updated workspace
                      </button>
                    ) : (
                      <>
                        <label className="amendment-review-check">
                          <input
                            checked={reviewed}
                            disabled={!preview.apply_allowed}
                            onChange={(event) => setReviewed(event.target.checked)}
                            type="checkbox"
                          />
                          <span>I reviewed the source and proposed field changes</span>
                        </label>
                        <div className="amendment-confirm-row">
                          <label>
                            <span>Confirmed by</span>
                            <input
                              aria-label="Confirmed by"
                              disabled={!preview.apply_allowed}
                              onChange={(event) => setConfirmedBy(event.target.value)}
                              value={confirmedBy}
                            />
                          </label>
                          <button
                            disabled={!preview.apply_allowed || !reviewed || !confirmedBy.trim() || applying}
                            onClick={() => void applyPreview()}
                            type="button"
                          >
                            {applying ? <LoaderCircle className="spin" size={16} /> : <FileCheck2 size={16} />}
                            {applying ? "Updating workspace" : "Confirm & update workspace"}
                          </button>
                        </div>
                      </>
                    )}
                  </section>

                  <button className="amendment-run-again" onClick={invalidatePreview} type="button">
                    <RotateCcw size={14} /> Edit source and run another preview
                  </button>
                </div>
              </div>
            )}
          </main>
        </div>
      </section>
    </div>
  );
}
