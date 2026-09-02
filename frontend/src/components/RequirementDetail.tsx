import { Check, Clock3, FileText, History, Link2, ListChecks, ShieldCheck } from "lucide-react";
import type { Requirement } from "../types/bid";
import { StatusPill } from "./StatusPill";

function formatDate(value: string | null) {
  if (!value) return "Not recorded";
  return new Intl.DateTimeFormat("en-SG", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Asia/Singapore",
  }).format(new Date(value.endsWith("Z") ? value : `${value}Z`));
}
export function RequirementDetail({ requirement }: { requirement: Requirement }) {
  return (
    <aside className="panel detail-panel">
      <div className="detail-accent" />
      <div className="detail-header">
        <div>
          <span className="eyebrow">Requirement detail</span>
          <div className="detail-title-row">
            <h2>{requirement.stable_key}</h2>
            <span className="version-badge">Current v{requirement.version}</span>
          </div>
        </div>
        <StatusPill status={requirement.assessment} />
      </div>

      <p className="detail-requirement">{requirement.text}</p>
      <div className="detail-meta">
        <span>
          <ShieldCheck size={14} /> {requirement.gate_type}
        </span>
        <span>
          <ListChecks size={14} /> {requirement.assessment_method ?? "HUMAN"}
        </span>
        <span>
          <Clock3 size={14} /> {formatDate(requirement.assessed_at)}
        </span>
      </div>

      <section className={`reason-box reason-${requirement.assessment.toLowerCase()}`}>
        <strong>Assessment rationale</strong>
        <p>{requirement.assessment_reason}</p>
      </section>

      <section className="detail-section">
        <div className="detail-section-heading">
          <span>
            <Link2 size={15} /> Evidence used
          </span>
          <small>{requirement.evidence_count} verified</small>
        </div>
        <div className="evidence-list">
          {requirement.evidence.length ? (
            requirement.evidence.map((evidence) => (
              <div className="evidence-row" key={evidence.id}>
                <span className="evidence-check">
                  <Check size={13} />
                </span>
                <div>
                  <strong>{evidence.title}</strong>
                  <small>{evidence.subject_name ?? evidence.type.replaceAll("_", " ")}</small>
                </div>
                <StatusPill status={evidence.status} compact />
              </div>
            ))
          ) : (
            <p className="muted-copy">No evidence is linked to this assessment.</p>
          )}
        </div>
      </section>

      <section className="source-box">
        <FileText size={17} />
        <div>
          <span>Source reference</span>
          <strong>{requirement.source.document}</strong>
          <small>
            Page {requirement.source.page} · Section {requirement.source.section}
          </small>
        </div>
      </section>

      {requirement.history.length > 1 && (
        <section className="detail-section history-section">
          <div className="detail-section-heading">
            <span>
              <History size={15} /> Version history
            </span>
            <small>Previous versions retained</small>
          </div>
          {requirement.history.map((version, index) => (
            <div className="history-row" key={version.id}>
              <span className={`history-marker ${index === 0 ? "current" : ""}`} />
              <div>
                <div className="history-topline">
                  <strong>v{version.version}</strong>
                  <StatusPill status={version.assessment} compact />
                </div>
                <p>{version.text}</p>
              </div>
            </div>
          ))}
        </section>
      )}
    </aside>
  );
}
