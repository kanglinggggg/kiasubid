import {
  AlertTriangle,
  ArrowRight,
  BookOpenCheck,
  BriefcaseBusiness,
  CalendarPlus,
  Check,
  ChevronRight,
  Clipboard,
  Database,
  ExternalLink,
  FileText,
  FlaskConical,
  GitCompareArrows,
  GraduationCap,
  LoaderCircle,
  Route,
  ScanSearch,
  Search,
  ShieldCheck,
  Sparkles,
  Upload,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { tenderLabApi } from "../api/client";
import type {
  AgentLoopResponse,
  AgentTask,
  AwardContextResponse,
  BusinessProfileIngestionResult,
  PartnerRoutePackage,
  TenderChangeSimulation,
  TenderLabMode,
  TenderLabRequest,
  TenderLabResponse,
} from "../types/tenderLab";

type ResultTab = "overview" | "agents" | "checks" | "decision" | "history" | "change" | "plan";

interface TenderLabDrawerProps {
  open: boolean;
  onClose: () => void;
}

const resultTabs: Array<{ id: ResultTab; label: string }> = [
  { id: "overview", label: "Brief" },
  { id: "agents", label: "Agent room" },
  { id: "checks", label: "Checks" },
  { id: "decision", label: "Decision" },
  { id: "history", label: "Award history" },
  { id: "change", label: "Change rehearsal" },
  { id: "plan", label: "Plan" },
];

const agentLabels: Record<AgentTask, string> = {
  COMPLIANCE: "Compliance specialist",
  COMMERCIAL: "Commercial specialist",
  TIMELINE: "Timeline specialist",
};

const CHANGE_SAMPLE = `[Page 2]
The supplier must maintain disaster recovery with a four-hour recovery time objective.
The service adds three locations, but expected event volume remains TBC.
Tender submission closes on 20 September 2026 at 12:00 SGT.`;

function money(value: number | null) {
  if (value === null) return "—";
  return new Intl.NumberFormat("en-SG", {
    style: "currency",
    currency: "SGD",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatMilestone(value: string) {
  const date = new Date(`${value}:00+08:00`);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-SG", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Asia/Singapore",
  }).format(date);
}

function googleCalendarUrl(
  title: string,
  milestone: TenderLabResponse["milestones"][number],
): string | null {
  const start = new Date(`${milestone.starts_at}:00+08:00`);
  if (Number.isNaN(start.getTime())) return null;
  const end = new Date(start.getTime() + 30 * 60 * 1000);
  const stamp = (date: Date) => date.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z");
  const params = new URLSearchParams({
    action: "TEMPLATE",
    text: `${title} — ${milestone.label}`,
    dates: `${stamp(start)}/${stamp(end)}`,
    details: `Review source: ${milestone.tender_source.source_label}, ${milestone.tender_source.location}\n${milestone.tender_source.excerpt}`,
  });
  return `https://calendar.google.com/calendar/render?${params.toString()}`;
}

function asNumber(value: string): number | null {
  if (!value.trim()) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function userSupplied(payload: TenderLabRequest): TenderLabRequest {
  return {
    ...payload,
    source_type: "USER_SUPPLIED",
    source_label:
      payload.source_type === "SYNTHETIC_SAMPLE" ? "Edited workspace input" : payload.source_label,
    company: {
      ...payload.company,
      source_type: "USER_SUPPLIED",
      verification_status: "DECLARED",
    },
    pricing: payload.pricing
      ? {
          ...payload.pricing,
          comparables_source:
            payload.pricing.comparables_source === "SYNTHETIC_SAMPLE"
              ? "USER_SUPPLIED"
              : payload.pricing.comparables_source,
        }
      : null,
  };
}

export function TenderLabDrawer({ open, onClose }: TenderLabDrawerProps) {
  const [payload, setPayload] = useState<TenderLabRequest | null>(null);
  const [result, setResult] = useState<TenderLabResponse | null>(null);
  const [tab, setTab] = useState<ResultTab>("overview");
  const [loadingSample, setLoadingSample] = useState(false);
  const [running, setRunning] = useState(false);
  const [extracting, setExtracting] = useState<"tender" | "proposal" | "company" | "amendment" | null>(null);
  const [companyProfile, setCompanyProfile] = useState<BusinessProfileIngestionResult | null>(null);
  const [awardQuery, setAwardQuery] = useState("cybersecurity");
  const [awardAgency, setAwardAgency] = useState("");
  const [awardContext, setAwardContext] = useState<AwardContextResponse | null>(null);
  const [loadingAwards, setLoadingAwards] = useState(false);
  const [partnerPackage, setPartnerPackage] = useState<PartnerRoutePackage | null>(null);
  const [buildingPartnerPackage, setBuildingPartnerPackage] = useState(false);
  const [changeSourceLabel, setChangeSourceLabel] = useState("Corrigendum 3.pdf");
  const [amendmentText, setAmendmentText] = useState(CHANGE_SAMPLE);
  const [changeSimulation, setChangeSimulation] = useState<TenderChangeSimulation | null>(null);
  const [simulatingChange, setSimulatingChange] = useState(false);
  const [agentLoop, setAgentLoop] = useState<AgentLoopResponse | null>(null);
  const [runningAgents, setRunningAgents] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const initialLoadRequestedRef = useRef(false);
  const changeRunIdRef = useRef(0);
  const agentRunIdRef = useRef(0);

  async function loadSample(mode: TenderLabMode) {
    invalidateChangeSimulation();
    invalidateAgentLoop();
    setLoadingSample(true);
    setError(null);
    setNotice(null);
    setResult(null);
    try {
      setPayload(await tenderLabApi.sample(mode));
      setAwardContext(null);
      setPartnerPackage(null);
      setCompanyProfile(null);
      setTab("overview");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load the sample.");
    } finally {
      setLoadingSample(false);
    }
  }

  useEffect(() => {
    if (!open) {
      initialLoadRequestedRef.current = false;
      return;
    }
    if (!payload && !initialLoadRequestedRef.current) {
      initialLoadRequestedRef.current = true;
      void loadSample("SME");
    }
  }, [open, payload]);

  useEffect(() => {
    if (!open) return;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.setTimeout(() => closeRef.current?.focus(), 0);
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = overflow;
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open, onClose]);

  const summary = useMemo(() => {
    if (!result) return null;
    return {
      gaps: result.policy_checks.filter((item) => item.status === "GAP").length,
      supported: result.policy_checks.filter((item) => item.status === "SUPPORTED").length,
      questions: result.clarification_questions.length,
      actions: result.next_actions.length,
    };
  }, [result]);

  function invalidateChangeSimulation() {
    changeRunIdRef.current += 1;
    setChangeSimulation(null);
    setSimulatingChange(false);
  }

  function invalidateAgentLoop() {
    agentRunIdRef.current += 1;
    setAgentLoop(null);
    setRunningAgents(false);
  }

  function update(next: TenderLabRequest) {
    setPayload(userSupplied(next));
    setResult(null);
    setPartnerPackage(null);
    invalidateChangeSimulation();
    invalidateAgentLoop();
    setNotice(null);
  }

  async function uploadDocument(target: "tender" | "proposal", file?: File) {
    if (!file || !payload) return;
    invalidateChangeSimulation();
    invalidateAgentLoop();
    setExtracting(target);
    setError(null);
    setNotice(null);
    try {
      const extracted = await tenderLabApi.extract(file);
      const next = userSupplied({
        ...payload,
        tender_text: target === "tender" ? extracted.text : payload.tender_text,
        proposal_text: target === "proposal" ? extracted.text : payload.proposal_text,
        source_label: target === "tender" ? extracted.filename : payload.source_label,
      });
      setPayload(next);
      setResult(null);
      setPartnerPackage(null);
      const suffix = extracted.warnings.length ? ` ${extracted.warnings.join(" ")}` : "";
      setNotice(
        `${extracted.filename}: ${extracted.page_count} page(s), ${extracted.character_count.toLocaleString()} characters extracted.${suffix}`,
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to extract the document.");
    } finally {
      setExtracting(null);
    }
  }

  async function uploadCompanyProfile(file?: File) {
    if (!file || !payload) return;
    invalidateChangeSimulation();
    invalidateAgentLoop();
    setExtracting("company");
    setError(null);
    setNotice(null);
    try {
      const profile = await tenderLabApi.companyProfile(file);
      const paidUpCapital = profile.paid_up_capital.value;
      const paidUpCapitalSgd =
        paidUpCapital?.currency === "SGD" && Number.isFinite(Number(paidUpCapital.amount))
          ? Number(paidUpCapital.amount)
          : null;
      const next = userSupplied({
        ...payload,
        company: {
          ...payload.company,
          name: profile.entity_name.value ?? payload.company.name,
          uen: profile.uen.value ?? payload.company.uen,
          entity_type: profile.entity_type.value,
          registration_status: profile.status.value,
          registration_date: profile.registration_or_incorporation_date.value?.date ?? null,
          primary_ssic_code: profile.primary_ssic.value?.code ?? null,
          primary_ssic_description: profile.primary_ssic.value?.description ?? null,
          paid_up_capital_sgd: paidUpCapitalSgd,
          profile_source_label: profile.source_document,
        },
      });
      setPayload({
        ...next,
        company: { ...next.company, verification_status: "NOT_VERIFIED" },
      });
      setCompanyProfile(profile);
      setResult(null);
      setPartnerPackage(null);
      setNotice(
        `${profile.source_document} parsed into source-backed company facts. Review fields marked REVIEW before relying on them.`,
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to parse the company profile.");
    } finally {
      setExtracting(null);
    }
  }

  async function uploadAmendment(file?: File) {
    if (!file) return;
    invalidateChangeSimulation();
    setExtracting("amendment");
    setError(null);
    setNotice(null);
    try {
      const extracted = await tenderLabApi.extract(file);
      setChangeSourceLabel(extracted.filename);
      setAmendmentText(extracted.text);
      const suffix = extracted.warnings.length ? ` ${extracted.warnings.join(" ")}` : "";
      setNotice(
        `${extracted.filename}: ${extracted.page_count} amendment page(s) extracted for rehearsal.${suffix}`,
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to extract the amendment.");
    } finally {
      setExtracting(null);
    }
  }

  async function analyze() {
    if (!payload) return;
    invalidateAgentLoop();
    setRunning(true);
    setError(null);
    setNotice(null);
    try {
      setResult(await tenderLabApi.analyze(payload));
      setTab("overview");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to run Tender Lab.");
    } finally {
      setRunning(false);
    }
  }

  async function searchAwards() {
    if (awardQuery.trim().length < 2) return;
    setLoadingAwards(true);
    setError(null);
    setNotice(null);
    setPartnerPackage(null);
    try {
      setAwardContext(await tenderLabApi.awardContext(awardQuery.trim(), awardAgency));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load award history.");
    } finally {
      setLoadingAwards(false);
    }
  }

  function useAwardContext() {
    if (!payload?.pricing || !awardContext?.records.length) return;
    invalidateAgentLoop();
    setPayload(
      userSupplied({
        ...payload,
        pricing: {
          ...payload.pricing,
          comparable_awards_sgd: awardContext.records.map((record) => record.awarded_amt_sgd),
          comparables_source: "PUBLIC_AWARD_CONTEXT",
          comparables_note:
            `${awardContext.provenance.dataset_title} · query “${awardContext.query}”` +
            `${awardContext.agency ? ` · agency contains “${awardContext.agency}”` : ""} · ` +
            `${awardContext.provenance.status} · retrieved ${awardContext.provenance.retrieved_at}`,
        },
      }),
    );
    setResult(null);
    setPartnerPackage(null);
    setNotice(
      `${awardContext.records.length} public award value(s) attached as descriptive pricing context. Run the SME review again to recalculate.`,
    );
  }

  function downloadCalendar() {
    if (!result) return;
    const blob = new Blob([result.calendar_ics], { type: "text/calendar;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "tender-milestones.ics";
    link.click();
    URL.revokeObjectURL(url);
  }

  async function copyClarifications() {
    if (!result) return;
    const text = result.clarification_questions
      .map(
        (item, index) =>
          `${index + 1}. ${item.question}\nSource: ${item.tender_source.location} — ${item.tender_source.excerpt}`,
      )
      .join("\n\n");
    await navigator.clipboard?.writeText(text);
    setNotice("Clarification draft copied. Nothing was sent externally.");
  }

  async function copyResponseScaffold(check: TenderLabResponse["policy_checks"][number]) {
    if (!check.remediation) return;
    const text = [
      check.remediation.title,
      check.remediation.draft,
      "Evidence to attach:",
      ...check.remediation.evidence_needed.map((item) => `- ${item}`),
      `Review boundary: ${check.remediation.boundary}`,
    ].join("\n\n");
    await navigator.clipboard?.writeText(text);
    setNotice("Response scaffold copied. Fill every placeholder and verify the evidence before use.");
  }

  async function buildPartnerPackage() {
    if (!payload || !awardContext) return;
    setBuildingPartnerPackage(true);
    setError(null);
    setNotice(null);
    try {
      const packageResult = await tenderLabApi.partnerRoute(payload, awardContext);
      setPartnerPackage(packageResult);
      setTab("decision");
      setNotice(
        "Partner package prepared from tender wording, declared capabilities and public award records. No outreach was sent.",
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to build the partner package.");
    } finally {
      setBuildingPartnerPackage(false);
    }
  }

  async function copyPartnerDraft(kind: "capability" | "outreach") {
    if (!partnerPackage) return;
    await navigator.clipboard?.writeText(
      kind === "capability"
        ? partnerPackage.capability_statement_draft
        : partnerPackage.outreach_draft,
    );
    setNotice(
      `${kind === "capability" ? "Capability note" : "Outreach draft"} copied. Nothing was sent externally.`,
    );
  }

  async function simulateChange() {
    if (!payload || amendmentText.trim().length < 20 || changeSourceLabel.trim().length < 2) return;
    const requestId = changeRunIdRef.current + 1;
    changeRunIdRef.current = requestId;
    const baseline = payload;
    const sourceLabel = changeSourceLabel.trim();
    const wording = amendmentText.trim();
    setSimulatingChange(true);
    setError(null);
    setNotice(null);
    try {
      const simulation = await tenderLabApi.simulateChange(baseline, sourceLabel, wording);
      if (changeRunIdRef.current !== requestId) return;
      setChangeSimulation(simulation);
      setNotice("Change rehearsal complete. The baseline workspace was not changed.");
    } catch (reason) {
      if (changeRunIdRef.current !== requestId) return;
      setError(reason instanceof Error ? reason.message : "Unable to rehearse this amendment.");
    } finally {
      if (changeRunIdRef.current === requestId) setSimulatingChange(false);
    }
  }

  async function runAgentLoop() {
    if (!payload) return;
    const requestId = agentRunIdRef.current + 1;
    agentRunIdRef.current = requestId;
    const baseline = payload;
    setAgentLoop(null);
    setRunningAgents(true);
    setError(null);
    setNotice(null);
    try {
      const response = await tenderLabApi.agentLoop(baseline, 1);
      if (agentRunIdRef.current !== requestId) return;
      setAgentLoop(response);
      setNotice(
        `Agent loop complete in ${response.loop_iterations} review round${response.loop_iterations === 1 ? "" : "s"}. No external action was taken.`,
      );
    } catch (reason) {
      if (agentRunIdRef.current !== requestId) return;
      setError(reason instanceof Error ? reason.message : "Unable to run the agent loop.");
    } finally {
      if (agentRunIdRef.current === requestId) setRunningAgents(false);
    }
  }

  if (!open) return null;

  return (
    <div
      className="tender-lab-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
      role="presentation"
    >
      <section
        aria-labelledby="tender-lab-title"
        aria-modal="true"
        className="tender-lab-drawer"
        role="dialog"
      >
        <header className="tender-lab-header">
          <div className="tender-lab-title-lockup">
            <span className="tender-lab-logo"><ScanSearch size={20} /></span>
            <div>
              <span className="eyebrow">Separate decision workspace</span>
              <h2 id="tender-lab-title">Tender Lab</h2>
            </div>
          </div>
          <div className="tender-lab-mode" aria-label="Workspace mode">
            <button
              aria-pressed={payload?.mode === "SME"}
              disabled={loadingSample}
              onClick={() => void loadSample("SME")}
            >
              <BriefcaseBusiness size={15} /> SME review
            </button>
            <button
              aria-pressed={payload?.mode === "STARTUP"}
              disabled={loadingSample}
              onClick={() => void loadSample("STARTUP")}
            >
              <GraduationCap size={16} /> Startup guide
            </button>
          </div>
          <button aria-label="Close Tender Lab" className="icon-button" onClick={onClose} ref={closeRef}>
            <X size={19} />
          </button>
        </header>

        <div className="tender-lab-boundary">
          <FlaskConical size={15} />
          <span>
            <strong>{payload?.source_type === "USER_SUPPLIED" ? "User-supplied workspace" : "Synthetic sample"}</strong>
            Stateless analysis  no operational bid data is changed
          </span>
        </div>

        {error && (
          <div className="tender-lab-alert error" role="alert">
            <AlertTriangle size={16} /><span>{error}</span><button onClick={() => setError(null)}>Dismiss</button>
          </div>
        )}
        {notice && (
          <div className="tender-lab-alert notice" role="status">
            <Check size={16} /><span>{notice}</span><button onClick={() => setNotice(null)}>Dismiss</button>
          </div>
        )}

        {loadingSample || !payload ? (
          <div className="tender-lab-loading"><LoaderCircle className="spin" /> Loading workspace</div>
        ) : (
          <div className="tender-lab-workspace">
            <aside className="tender-lab-inputs">
              <div className="tender-lab-input-heading">
                <div><span className="eyebrow">Inputs</span><h3>What we know</h3></div>
                <span className={`tender-lab-source ${payload.source_type.toLowerCase()}`}>
                  {payload.source_type === "SYNTHETIC_SAMPLE" ? "Sample" : "Supplied"}
                </span>
              </div>

              <label className="tender-lab-field">
                <span>Tender title</span>
                <input value={payload.tender_title} onChange={(event) => update({ ...payload, tender_title: event.target.value })} />
              </label>
              <label className="tender-lab-field">
                <span>Agency</span>
                <input value={payload.agency} onChange={(event) => update({ ...payload, agency: event.target.value })} />
              </label>

              <div className="tender-lab-file-row">
                <div>
                  <strong>Tender source</strong>
                  <small>Selectable-text PDF  TXT or Markdown</small>
                </div>
                <label className="tender-lab-upload">
                  {extracting === "tender" ? <LoaderCircle className="spin" size={15} /> : <Upload size={15} />}
                  Replace
                  <input
                    accept=".pdf,.txt,.md,text/plain,application/pdf"
                    disabled={extracting !== null}
                    onChange={(event) => void uploadDocument("tender", event.target.files?.[0])}
                    type="file"
                  />
                </label>
              </div>
              <label className="tender-lab-field tender-lab-textarea">
                <span>Tender text  page markers are retained</span>
                <textarea value={payload.tender_text} onChange={(event) => update({ ...payload, tender_text: event.target.value })} />
              </label>

              <div className="tender-lab-file-row">
                <div><strong>Proposal draft</strong><small>Used only for text coverage matching</small></div>
                <label className="tender-lab-upload">
                  {extracting === "proposal" ? <LoaderCircle className="spin" size={15} /> : <Upload size={15} />}
                  Replace
                  <input
                    accept=".pdf,.txt,.md,text/plain,application/pdf"
                    disabled={extracting !== null}
                    onChange={(event) => void uploadDocument("proposal", event.target.files?.[0])}
                    type="file"
                  />
                </label>
              </div>
              <label className="tender-lab-field tender-lab-textarea compact">
                <span>Proposal text</span>
                <textarea value={payload.proposal_text} onChange={(event) => update({ ...payload, proposal_text: event.target.value })} />
              </label>

              <div className="tender-lab-section-label">Company facts</div>
              <div className="tender-lab-profile-upload">
                <div>
                  <strong>ACRA Business Profile</strong>
                  <small>Selectable-text PDF  parsed locally  not an ACRA verification</small>
                </div>
                <label className="tender-lab-upload">
                  {extracting === "company" ? <LoaderCircle className="spin" size={15} /> : <Upload size={15} />}
                  {companyProfile ? "Replace" : "Import"}
                  <input
                    aria-label="Import ACRA Business Profile"
                    accept=".pdf,.txt,text/plain,application/pdf"
                    disabled={extracting !== null}
                    onChange={(event) => void uploadCompanyProfile(event.target.files?.[0])}
                    type="file"
                  />
                </label>
              </div>
              {companyProfile && (
                <div className="tender-lab-profile-result">
                  <div className="tender-lab-profile-result-head">
                    <span>NOT OFFICIALLY VERIFIED</span>
                    <small>{companyProfile.source_document}</small>
                  </div>
                  <div className="tender-lab-profile-facts">
                    <div><small>Entity</small><strong>{companyProfile.entity_name.value ?? "Review required"}</strong></div>
                    <div><small>UEN</small><strong>{companyProfile.uen.value ?? "Review required"}</strong></div>
                    <div><small>Primary SSIC</small><strong>{companyProfile.primary_ssic.value?.code ?? "Review required"}</strong></div>
                    <div><small>Paid-up capital</small><strong>{payload.company.paid_up_capital_sgd === null ? "Review required" : money(payload.company.paid_up_capital_sgd)}</strong></div>
                  </div>
                  <details>
                    <summary>Review extraction evidence and boundaries</summary>
                    <ul>
                      {[companyProfile.entity_name, companyProfile.uen, companyProfile.primary_ssic, companyProfile.paid_up_capital].map((field, index) => (
                        <li key={index}>
                          <strong>{field.confidence}</strong>
                          <span>{field.sources[0] ? `Page ${field.sources[0].page}  ${field.sources[0].excerpt}` : field.review_reason}</span>
                        </li>
                      ))}
                    </ul>
                    <div className="tender-lab-profile-grade-boundary">
                      <strong>EPU / SCA are not inferred from ACRA data</strong>
                      <span>{companyProfile.epu_grade.review_reason}</span>
                      <span>{companyProfile.sca_grade.review_reason}</span>
                    </div>
                    {companyProfile.boundaries.map((boundary) => <p key={boundary}>{boundary}</p>)}
                  </details>
                </div>
              )}
              <label className="tender-lab-field">
                <span>Company or team</span>
                <input value={payload.company.name} onChange={(event) => update({ ...payload, company: { ...payload.company, name: event.target.value } })} />
              </label>
              <div className="tender-lab-field-grid">
                <label className="tender-lab-field">
                  <span>Contract value  SGD</span>
                  <input min="0" type="number" value={payload.contract_value_sgd ?? ""} onChange={(event) => update({ ...payload, contract_value_sgd: asNumber(event.target.value) })} />
                </label>
                <label className="tender-lab-field">
                  <span>Declared delivery limit</span>
                  <input min="0" type="number" value={payload.company.max_delivery_value_sgd ?? ""} onChange={(event) => update({ ...payload, company: { ...payload.company, max_delivery_value_sgd: asNumber(event.target.value) } })} />
                </label>
              </div>
              <label className="tender-lab-field">
                <span>Capabilities  comma separated</span>
                <input value={payload.company.capabilities.join(", ")} onChange={(event) => update({ ...payload, company: { ...payload.company, capabilities: event.target.value.split(",").map((item) => item.trim()).filter(Boolean) } })} />
              </label>

              {payload.mode === "SME" && payload.pricing ? (
                <>
                  <div className="tender-lab-section-label">Cost resilience</div>
                  <div className="tender-lab-field-grid">
                    <label className="tender-lab-field">
                      <span>Estimated cost  SGD</span>
                      <input min="1" type="number" value={payload.pricing.estimated_cost_sgd} onChange={(event) => update({ ...payload, pricing: { ...payload.pricing!, estimated_cost_sgd: Number(event.target.value) } })} />
                    </label>
                    <label className="tender-lab-field">
                      <span>Proposed price  SGD</span>
                      <input min="1" type="number" value={payload.pricing.proposed_price_sgd} onChange={(event) => update({ ...payload, pricing: { ...payload.pricing!, proposed_price_sgd: Number(event.target.value) } })} />
                    </label>
                  </div>
                  <label className="tender-lab-field">
                    <span>Comparable values  user supplied</span>
                    <input value={payload.pricing.comparable_awards_sgd.join(", ")} onChange={(event) => update({ ...payload, pricing: { ...payload.pricing!, comparable_awards_sgd: event.target.value.split(",").map((item) => Number(item.trim())).filter((item) => Number.isFinite(item) && item > 0), comparables_source: "USER_SUPPLIED", comparables_note: "Values edited by the user; scope comparability has not been verified." } })} />
                  </label>
                </>
              ) : payload.startup_answers ? (
                <>
                  <div className="tender-lab-section-label">Founder answers</div>
                  {(
                    [
                      ["solution_summary", "Solution and measurable outcome"],
                      ["delivery_approach", "Delivery and acceptance"],
                      ["security_approach", "Security approach"],
                      ["team_strength", "Team proof"],
                      ["social_value", "Optional social value"],
                    ] as const
                  ).map(([key, label]) => (
                    <label className="tender-lab-field" key={key}>
                      <span>{label}</span>
                      <textarea
                        className="tender-lab-short-answer"
                        value={payload.startup_answers![key]}
                        onChange={(event) => update({ ...payload, startup_answers: { ...payload.startup_answers!, [key]: event.target.value } })}
                      />
                    </label>
                  ))}
                </>
              ) : null}

              <button className="tender-lab-run" disabled={running || payload.tender_text.trim().length < 30} onClick={() => void analyze()}>
                {running ? <LoaderCircle className="spin" size={17} /> : <Sparkles size={17} />}
                {running ? "Running workflow" : `Run ${payload.mode === "SME" ? "SME review" : "startup guide"}`}
                {!running && <ArrowRight size={16} />}
              </button>
            </aside>

            <main className="tender-lab-results">
              {!result ? (
                <div className="tender-lab-empty">
                  <span><BookOpenCheck size={24} /></span>
                  <h3>Turn tender text into a reviewable decision</h3>
                  <p>
                    The workflow keeps source excerpts visible  finds proposal gaps and ambiguities  then prepares routes and next actions for a person to review
                  </p>
                  <div className="tender-lab-empty-flow">
                    {[
                      "Read source",
                      "Match controls",
                      "Draft questions",
                      payload.mode === "SME" ? "Test commercials" : "Coach response",
                      "Compare routes",
                    ].map((item, index) => (
                      <span key={item}>{index + 1}<strong>{item}</strong>{index < 4 && <ChevronRight size={14} />}</span>
                    ))}
                  </div>
                </div>
              ) : (
                <>
                  <div className="tender-lab-result-head">
                    <div>
                      <span className="eyebrow">Analysis ready</span>
                      <h3>{result.brief.objective}</h3>
                      <p>{result.brief.plain_language_summary}</p>
                    </div>
                    <div className="tender-lab-stats">
                      <span><strong>{summary?.supported}</strong> covered</span>
                      <span className={summary?.gaps ? "has-gap" : ""}><strong>{summary?.gaps}</strong> gaps</span>
                      <span><strong>{summary?.questions}</strong> questions</span>
                      <span><strong>{summary?.actions}</strong> actions</span>
                    </div>
                  </div>

                  <nav className="tender-lab-tabs" aria-label="Tender Lab results">
                    {resultTabs.map((item) => (
                      <button key={item.id} aria-selected={tab === item.id} onClick={() => setTab(item.id)}>
                        {item.label}
                      </button>
                    ))}
                  </nav>

                  <div className="tender-lab-result-body">
                    {tab === "overview" && (
                      <div className="tender-lab-stack">
                        <section className="tender-lab-card">
                          <div className="tender-lab-card-title"><FileText size={17} /><div><span>Supplied source</span><h4>Mandatory wording detected</h4></div></div>
                          {result.brief.mandatory_signals.length ? (
                            <ol className="tender-lab-source-list">
                              {result.brief.mandatory_signals.map((item) => <li key={item}>{item}</li>)}
                            </ol>
                          ) : <p>No explicit mandatory wording detected  manual review still required</p>}
                        </section>
                        <section className="tender-lab-card">
                          <div className="tender-lab-card-title"><BookOpenCheck size={17} /><div><span>Plain-language brief</span><h4>What the buyer wants delivered</h4></div></div>
                          {result.brief.requested_outcomes.length ? (
                            <ol className="tender-lab-source-list">
                              {result.brief.requested_outcomes.map((item) => <li key={item}>{item}</li>)}
                            </ol>
                          ) : <p>No delivery outcome was extracted  review the supplied source manually</p>}
                        </section>
                        <section className="tender-lab-card">
                          <div className="tender-lab-card-title"><Sparkles size={17} /><div><span>Bounded workflow</span><h4>What the system actually ran</h4></div></div>
                          <div className="tender-lab-trace">
                            {result.trace.map((step, index) => (
                              <div key={step.id} className={step.status === "SKIPPED" ? "skipped" : ""}>
                                <span>{step.status === "SKIPPED" ? "—" : index + 1}</span>
                                <p><strong>{step.label}</strong><small>{step.detail}</small></p>
                              </div>
                            ))}
                          </div>
                        </section>
                        <section className="tender-lab-card tender-lab-limits">
                          <div className="tender-lab-card-title"><ShieldCheck size={17} /><div><span>Truth boundary</span><h4>What this result does not claim</h4></div></div>
                          <ul>{result.boundaries.map((item) => <li key={item}>{item}</li>)}</ul>
                        </section>
                      </div>
                    )}

                    {tab === "agents" && (
                      <div className="tender-lab-stack">
                        <section className="tender-lab-card tender-lab-agent-launch">
                          <div className="tender-lab-card-title">
                            <GitCompareArrows size={17} />
                            <div>
                              <span>Bounded multi-agent review</span>
                              <h4>Agent Room</h4>
                            </div>
                            <button
                              className="tender-lab-agent-run"
                              disabled={runningAgents}
                              onClick={() => void runAgentLoop()}
                            >
                              {runningAgents ? <LoaderCircle className="spin" size={15} /> : <Sparkles size={15} />}
                              {runningAgents ? "Agents reviewing" : agentLoop ? "Run again" : "Run agent loop"}
                            </button>
                          </div>
                          <p>
                            One planner briefs three specialists  a critic checks every finding against
                            named evidence  then a person receives the decision packet
                          </p>
                          <div className="tender-lab-agent-topology" aria-label="Planner to specialists to critic to human decision workflow">
                            <div className="tender-lab-agent-node planner">
                              <small>01</small><strong>Planner</strong><span>Scopes the review</span>
                            </div>
                            <ChevronRight size={16} />
                            <div className="tender-lab-agent-specialists">
                              <div><ShieldCheck size={13} /><span>Compliance</span></div>
                              <div><BriefcaseBusiness size={13} /><span>Commercial</span></div>
                              <div><CalendarPlus size={13} /><span>Timeline</span></div>
                            </div>
                            <ChevronRight size={16} />
                            <div className="tender-lab-agent-node critic">
                              <small>03</small><strong>Critic</strong><span>Tests grounding</span>
                            </div>
                            <ChevronRight size={16} />
                            <div className="tender-lab-agent-node human">
                              <small>04</small><strong>Human</strong><span>Makes the call</span>
                            </div>
                          </div>
                          <p className="tender-lab-method">
                            Maximum one revision round  no browsing  no file edits  no contact or submission
                          </p>
                        </section>

                        {!agentLoop && !runningAgents && (
                          <section className="tender-lab-card tender-lab-agent-empty">
                            <ScanSearch size={22} />
                            <div>
                              <h4>The room has not run on this workspace yet</h4>
                              <p>Run it after checking the tender and proposal inputs on the left</p>
                            </div>
                          </section>
                        )}

                        {runningAgents && !agentLoop && (
                          <section className="tender-lab-card tender-lab-agent-progress" aria-live="polite">
                            <LoaderCircle className="spin" size={20} />
                            <div><h4>Planner and specialists are reviewing</h4><p>The critic may return one specialist response for revision</p></div>
                          </section>
                        )}

                        {agentLoop && (
                          <>
                            <section className="tender-lab-card tender-lab-agent-run-summary">
                              <div className="tender-lab-card-title">
                                <Sparkles size={17} />
                                <div><span>Execution record</span><h4>What actually ran</h4></div>
                                <span className={`tender-lab-provider-state ${agentLoop.provider_state.toLowerCase()}`}>
                                  {agentLoop.provider_state}
                                </span>
                              </div>
                              <div className="tender-lab-agent-meta">
                                <div><small>Provider state</small><strong>{agentLoop.provider_state}</strong></div>
                                <div><small>Model</small><strong>{agentLoop.model_id ?? "Deterministic fallback"}</strong></div>
                                <div><small>Critic rounds</small><strong>{agentLoop.loop_iterations}</strong></div>
                                <div><small>Evidence items</small><strong>{agentLoop.evidence_register.length}</strong></div>
                              </div>
                              <div className="tender-lab-agent-executions">
                                {agentLoop.executions.map((execution) => (
                                  <article key={execution.agent_id}>
                                    <div>
                                      <strong>{execution.label}</strong>
                                      <span className={`tender-lab-execution-mode ${execution.mode.toLowerCase()}`}>
                                        {execution.mode.replaceAll("_", " ")}
                                      </span>
                                    </div>
                                    <p>{execution.detail}</p>
                                    <small>
                                      {execution.status.replaceAll("_", " ")}  ·  {execution.attempts} attempt{execution.attempts === 1 ? "" : "s"}
                                      {execution.revision_count ? `  ·  ${execution.revision_count} revision` : ""}
                                      {`  ·  ${Math.round(execution.duration_ms)} ms`}
                                      {execution.total_tokens === null ? "" : `  ·  ${execution.total_tokens} tokens`}
                                    </small>
                                  </article>
                                ))}
                              </div>
                              {agentLoop.fallback_reasons.length > 0 && (
                                <div className="tender-lab-agent-fallback">
                                  <strong>Visible fallback reasons</strong>
                                  <ul>{agentLoop.fallback_reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
                                </div>
                              )}
                            </section>

                            <section className="tender-lab-card tender-lab-agent-plan">
                              <div className="tender-lab-card-title"><Route size={17} /><div><span>Planner output</span><h4>Specialist brief</h4></div></div>
                              <p>{agentLoop.plan.mission}</p>
                              <div className="tender-lab-agent-plan-grid">
                                {agentLoop.plan.tasks.map((task) => (
                                  <article key={task.agent}>
                                    <span>{task.agent}</span>
                                    <h4>{agentLabels[task.agent]}</h4>
                                    <p>{task.objective}</p>
                                    {task.focus.length > 0 && <small>{task.focus.join("  ·  ")}</small>}
                                  </article>
                                ))}
                              </div>
                              {agentLoop.plan.success_criteria.length > 0 && (
                                <div className="tender-lab-agent-success">
                                  <small>Success criteria</small>
                                  <ul>{agentLoop.plan.success_criteria.map((criterion) => <li key={criterion}>{criterion}</li>)}</ul>
                                </div>
                              )}
                            </section>

                            <section className="tender-lab-card tender-lab-agent-findings">
                              <div className="tender-lab-card-title"><ShieldCheck size={17} /><div><span>Specialist outputs</span><h4>Evidence-grounded findings</h4></div></div>
                              <div className="tender-lab-agent-specialist-list">
                                {agentLoop.specialists.map((specialist) => (
                                  <article className="tender-lab-agent-specialist" key={specialist.agent}>
                                    <header>
                                      <div><span>{specialist.agent}</span><h4>{agentLabels[specialist.agent]}</h4></div>
                                      <div>
                                        {specialist.revision_count > 0 && <small>Revised once</small>}
                                        <span className={`tender-lab-critic-verdict ${specialist.critic_verdict.toLowerCase()}`}>Critic {specialist.critic_verdict}</span>
                                      </div>
                                    </header>
                                    <p className="tender-lab-agent-summary">{specialist.output.summary}</p>
                                    <div className="tender-lab-agent-finding-list">
                                      {specialist.output.findings.map((finding) => {
                                        const review = agentLoop.critic.finding_reviews.find((item) => item.finding_id === finding.id);
                                        return (
                                          <article key={finding.id}>
                                            <div className="tender-lab-agent-finding-head">
                                              <span className={`tender-lab-status ${finding.status.toLowerCase()}`}>{finding.status}</span>
                                              <strong>{finding.id}</strong>
                                              <small className={`severity-${finding.severity.toLowerCase()}`}>{finding.severity}</small>
                                              <span>{finding.confidence} confidence</span>
                                            </div>
                                            <h4>{finding.title}</h4>
                                            <p>{finding.claim}</p>
                                            {finding.evidence_gap && <p className="tender-lab-agent-evidence-gap"><AlertTriangle size={13} /> {finding.evidence_gap}</p>}
                                            {finding.downstream_effects.length > 0 && (
                                              <div className="tender-lab-agent-effects">
                                                <small>Downstream effects</small>
                                                {finding.downstream_effects.map((effect) => <span key={effect}>{effect}</span>)}
                                              </div>
                                            )}
                                            <p className="tender-lab-agent-action"><ArrowRight size={13} /> {finding.recommended_action}</p>
                                            {review && (
                                              <div className={`tender-lab-agent-review ${review.verdict.toLowerCase()}`}>
                                                <strong>Critic {review.verdict}</strong><span>{review.feedback}</span>
                                              </div>
                                            )}
                                            <details className="tender-lab-agent-evidence">
                                              <summary>Evidence sources <span>{finding.evidence_ids.length}</span><ChevronRight size={13} /></summary>
                                              <div>
                                                {finding.evidence_ids.map((evidenceId) => {
                                                  const evidence = agentLoop.evidence_register.find((item) => item.id === evidenceId);
                                                  return evidence ? (
                                                    <blockquote key={evidence.id}>
                                                      <div><strong>{evidence.id}</strong><span>{evidence.kind.replaceAll("_", " ")}</span></div>
                                                      <small>{evidence.label}  ·  {evidence.location}</small>
                                                      <p>{evidence.content}</p>
                                                      {evidence.source_url && <a href={evidence.source_url} rel="noreferrer" target="_blank">Official source <ExternalLink size={10} /></a>}
                                                    </blockquote>
                                                  ) : <p key={evidenceId}>Evidence ID {evidenceId} was not returned</p>;
                                                })}
                                              </div>
                                            </details>
                                          </article>
                                        );
                                      })}
                                    </div>
                                    {specialist.output.assumptions.length > 0 && (
                                      <details className="tender-lab-agent-assumptions">
                                        <summary>Assumptions to verify <span>{specialist.output.assumptions.length}</span></summary>
                                        <ul>{specialist.output.assumptions.map((assumption) => <li key={assumption}>{assumption}</li>)}</ul>
                                      </details>
                                    )}
                                    <footer><small>Handoff</small><span>{specialist.output.handoff}</span></footer>
                                  </article>
                                ))}
                              </div>
                            </section>

                            <section className="tender-lab-card tender-lab-agent-critic">
                              <div className="tender-lab-card-title">
                                <ScanSearch size={17} />
                                <div><span>Independent review</span><h4>Critic</h4></div>
                                <span className={`tender-lab-critic-verdict ${agentLoop.critic.overall_verdict.toLowerCase()}`}>
                                  {agentLoop.critic.overall_verdict}
                                </span>
                              </div>
                              <p>The critic checks whether each claim is supported by its cited evidence and whether specialists conflict</p>
                              <div className="tender-lab-agent-critic-grid">
                                <div>
                                  <small>Cross-agent conflicts</small>
                                  {agentLoop.critic.cross_agent_conflicts.length ? <ul>{agentLoop.critic.cross_agent_conflicts.map((item) => <li key={item}>{item}</li>)}</ul> : <p>No conflict reported</p>}
                                </div>
                                <div>
                                  <small>Human checks</small>
                                  {agentLoop.critic.human_checks.length ? <ul>{agentLoop.critic.human_checks.map((item) => <li key={item}>{item}</li>)}</ul> : <p>No additional check reported</p>}
                                </div>
                              </div>
                            </section>

                            <section className={`tender-lab-card tender-lab-agent-decision ${agentLoop.decision.readiness.toLowerCase()}`}>
                              <div className="tender-lab-card-title">
                                <Check size={17} />
                                <div><span>Human decision packet</span><h4>{agentLoop.decision.headline}</h4></div>
                                <span className="tender-lab-agent-readiness">{agentLoop.decision.readiness.replaceAll("_", " ")}</span>
                              </div>
                              <div className="tender-lab-agent-decision-counts">
                                <div><strong>{agentLoop.decision.grounded_finding_ids.length}</strong><span>grounded findings</span></div>
                                <div><strong>{agentLoop.decision.unresolved_finding_ids.length}</strong><span>unresolved findings</span></div>
                              </div>
                              <div className="tender-lab-agent-decision-body">
                                <div>
                                  <small>Decisions required</small>
                                  {agentLoop.decision.decisions_required.length ? <ol>{agentLoop.decision.decisions_required.map((item) => <li key={item}>{item}</li>)}</ol> : <p>No additional decision listed</p>}
                                </div>
                                <div><small>Next step</small><p>{agentLoop.decision.next_step}</p></div>
                              </div>
                              <p className="tender-lab-agent-boundary">{agentLoop.decision.boundary}</p>
                            </section>

                            <section className="tender-lab-card tender-lab-limits tender-lab-agent-limits">
                              <div className="tender-lab-card-title"><ShieldCheck size={17} /><div><span>Agent boundaries</span><h4>Actions the loop cannot take</h4></div></div>
                              <ul>{agentLoop.boundaries.map((boundary) => <li key={boundary}>{boundary}</li>)}</ul>
                            </section>
                          </>
                        )}
                      </div>
                    )}

                    {tab === "checks" && (
                      <div className="tender-lab-stack">
                        <section className="tender-lab-card">
                          <div className="tender-lab-card-title"><ShieldCheck size={17} /><div><span>Tender-triggered scan</span><h4>Proposal coverage</h4></div></div>
                          <p className="tender-lab-method">Keyword pack {result.policy_checks[0]?.pack_version}  matching text is not official compliance certification</p>
                          <div className="tender-lab-checks">
                            {result.policy_checks.map((check) => (
                                <article key={check.id}>
                                <div><span className={`tender-lab-status ${check.status.toLowerCase()}`}>{check.status}</span><small>{check.risk}</small></div>
                                <h4>{check.title}</h4>
                                <p>{check.rationale}</p>
                                <blockquote><strong>{check.tender_source.location}</strong>{check.tender_source.excerpt}</blockquote>
                                {check.proposal_evidence ? <p className="tender-lab-evidence"><Check size={14} /> {check.proposal_evidence}</p> : <p className="tender-lab-next"><ArrowRight size={14} /> {check.next_step}</p>}
                                {check.official_source && (
                                  <div className="tender-lab-official-source">
                                    <div>
                                      <strong>Official public context</strong>
                                      <span>{check.official_source.supports}</span>
                                      <small>{check.official_source.limitation}</small>
                                    </div>
                                    <a href={check.official_source.url} rel="noreferrer" target="_blank">
                                      {check.official_source.publisher} <ExternalLink size={12} />
                                    </a>
                                  </div>
                                )}
                                {check.remediation && (
                                  <details className="tender-lab-remediation">
                                    <summary>
                                      <span>
                                        <FileText size={14} />
                                        Response scaffold
                                      </span>
                                      <ChevronRight size={14} />
                                    </summary>
                                    <div>
                                      <pre>{check.remediation.draft}</pre>
                                      <div className="tender-lab-remediation-grid">
                                        <div>
                                          <small>Fill these fields</small>
                                          <ul>{check.remediation.placeholders.map((item) => <li key={item}>{item}</li>)}</ul>
                                        </div>
                                        <div>
                                          <small>Evidence to attach</small>
                                          <ul>{check.remediation.evidence_needed.map((item) => <li key={item}>{item}</li>)}</ul>
                                        </div>
                                      </div>
                                      <p>{check.remediation.boundary}</p>
                                      <button
                                        className="tender-lab-secondary"
                                        onClick={() => void copyResponseScaffold(check)}
                                      >
                                        <Clipboard size={14} /> Copy scaffold
                                      </button>
                                    </div>
                                  </details>
                                )}
                              </article>
                            ))}
                          </div>
                        </section>
                        <section className="tender-lab-card">
                          <div className="tender-lab-card-title"><Clipboard size={17} /><div><span>Draft only</span><h4>Clarification questions</h4></div><button className="tender-lab-secondary" disabled={!result.clarification_questions.length} onClick={() => void copyClarifications()}><Clipboard size={14} /> Copy draft</button></div>
                          {result.clarification_questions.length ? result.clarification_questions.map((item) => (
                            <article className="tender-lab-question" key={item.id}>
                              <span>{item.id}</span><div><h4>{item.issue}</h4><p>{item.question}</p><small>{item.commercial_impact}</small><blockquote>{item.tender_source.location}  {item.tender_source.excerpt}</blockquote></div>
                            </article>
                          )) : <p>No configured ambiguity marker was found  this is not a guarantee that the source is complete</p>}
                        </section>
                      </div>
                    )}

                    {tab === "decision" && (
                      <div className="tender-lab-stack">
                        {result.pricing && (
                          <section className="tender-lab-card">
                            <div className="tender-lab-card-title"><BriefcaseBusiness size={17} /><div><span>Transparent arithmetic</span><h4>Cost resilience</h4></div></div>
                            <div className="tender-lab-commercial-summary">
                              <div><small>Proposed price</small><strong>{money(result.pricing.proposed_price_sgd)}</strong></div>
                              <div><small>Gross margin</small><strong>{money(result.pricing.gross_margin_sgd)}</strong><span>{result.pricing.gross_margin_percent}%</span></div>
                              <div><small>Supplied median</small><strong>{money(result.pricing.comparable_median_sgd)}</strong><span>{result.pricing.comparable_count} values</span></div>
                            </div>
                            <p className="tender-lab-position">{result.pricing.position}</p>
                            <p className="tender-lab-method">
                              {result.pricing.confidence.replaceAll("_", " ")}  {result.pricing.comparables_note}
                            </p>
                            <div className="tender-lab-scenarios">
                              {result.pricing.scenarios.map((scenario) => <div key={scenario.label}><span>{scenario.label}</span><strong>{money(scenario.price_sgd)}</strong><small>{scenario.gross_margin_percent}% gross margin</small></div>)}
                            </div>
                            <p className="tender-lab-method">{result.pricing.boundary}</p>
                          </section>
                        )}
                        {result.startup_coach && (
                          <section className="tender-lab-card">
                            <div className="tender-lab-card-title"><GraduationCap size={17} /><div><span>Practice and critique</span><h4>Response coach</h4></div></div>
                            <div className="tender-lab-coach-grid">
                              {result.startup_coach.findings.map((finding) => <article key={finding.area}><span className={`tender-lab-status ${finding.status.toLowerCase()}`}>{finding.status}</span><h4>{finding.area}</h4><p>{finding.critique}</p><small>{finding.next_prompt}</small></article>)}
                            </div>
                            <div className="tender-lab-outline">
                              {result.startup_coach.sections.map((section) => <details key={section.title}><summary>{section.title}<ChevronRight size={14} /></summary><p>{section.draft}</p><small>Evidence needed  {section.evidence_needed.join("  ·  ") || "None identified"}</small></details>)}
                            </div>
                            <p className="tender-lab-method">{result.startup_coach.boundary}</p>
                          </section>
                        )}
                        {partnerPackage && (
                          <section className="tender-lab-card tender-lab-partner-package">
                            <div className="tender-lab-card-title">
                              <Route size={17} />
                              <div>
                                <span>Evidence-bounded router</span>
                                <h4>Delivery-partner research package</h4>
                              </div>
                              <span className={`tender-lab-status ${partnerPackage.eligibility.toLowerCase()}`}>
                                {partnerPackage.eligibility.replaceAll("_", " ")}
                              </span>
                            </div>
                            <p>{partnerPackage.eligibility_reason}</p>
                            {partnerPackage.tender_source && (
                              <blockquote>
                                <strong>{partnerPackage.tender_source.location}</strong>
                                {partnerPackage.tender_source.excerpt}
                              </blockquote>
                            )}
                            <p className="tender-lab-position">{partnerPackage.direct_bid_context}</p>

                            <div className="tender-lab-partner-work-packages">
                              {partnerPackage.work_packages.map((workPackage) => (
                                <details key={workPackage.id}>
                                  <summary>
                                    <span>{workPackage.id}</span>
                                    <strong>{workPackage.title}</strong>
                                    <ChevronRight size={14} />
                                  </summary>
                                  <div>
                                    <p>{workPackage.scope}</p>
                                    <small>Handoffs</small>
                                    <ul>{workPackage.handoffs.map((item) => <li key={item}>{item}</li>)}</ul>
                                    <small>Evidence needed</small>
                                    <ul>{workPackage.evidence_needed.map((item) => <li key={item}>{item}</li>)}</ul>
                                  </div>
                                </details>
                              ))}
                            </div>

                            <div className="tender-lab-partner-leads">
                              <div className="tender-lab-subheading">
                                <span>Public award sample</span>
                                <h4>Supplier research leads</h4>
                              </div>
                              {partnerPackage.research_leads.length ? (
                                partnerPackage.research_leads.map((lead) => (
                                  <article key={lead.supplier_name}>
                                    <div>
                                      <strong>{lead.supplier_name}</strong>
                                      <span>{lead.status.replaceAll("_", " ")}</span>
                                    </div>
                                    <p>{lead.public_basis}</p>
                                    <small>{lead.observed_award_rows} retained row(s)  ·  {money(lead.observed_total_awarded_sgd)}</small>
                                    <a href={lead.source_url} rel="noreferrer" target="_blank">Public source <ExternalLink size={11} /></a>
                                  </article>
                                ))
                              ) : (
                                <p>No supplier research lead was retained from this sample</p>
                              )}
                            </div>

                            <div className="tender-lab-partner-drafts">
                              <details>
                                <summary>Capability note draft <ChevronRight size={14} /></summary>
                                <pre>{partnerPackage.capability_statement_draft}</pre>
                                <button className="tender-lab-secondary" onClick={() => void copyPartnerDraft("capability")}>
                                  <Clipboard size={14} /> Copy capability note
                                </button>
                              </details>
                              <details>
                                <summary>Outreach draft <ChevronRight size={14} /></summary>
                                <pre>{partnerPackage.outreach_draft}</pre>
                                <button className="tender-lab-secondary" onClick={() => void copyPartnerDraft("outreach")}>
                                  <Clipboard size={14} /> Copy outreach draft
                                </button>
                              </details>
                            </div>
                            <div className="tender-lab-partner-next">
                              <small>Before any outreach</small>
                              <ol>{partnerPackage.next_actions.map((item) => <li key={item}>{item}</li>)}</ol>
                            </div>
                            <ul className="tender-lab-partner-boundaries">
                              {partnerPackage.boundaries.map((item) => <li key={item}>{item}</li>)}
                            </ul>
                          </section>
                        )}
                        <section className="tender-lab-card">
                          <div className="tender-lab-card-title"><Route size={17} /><div><span>Simulation only</span><h4>Participation routes</h4></div></div>
                          <div className="tender-lab-routes">
                            {result.strategy_routes.map((route) => <article key={route.id}><div><span className={`tender-lab-status ${route.status.toLowerCase()}`}>{route.status}</span><small>Human decision</small></div><h4>{route.title}</h4><p>{route.rationale}</p>{route.unresolved_facts.length > 0 && <ul>{route.unresolved_facts.map((fact) => <li key={fact}>{fact}</li>)}</ul>}<footer>{route.output.map((item) => <span key={item}>{item}</span>)}</footer></article>)}
                          </div>
                        </section>
                      </div>
                    )}

                    {tab === "history" && (
                      <div className="tender-lab-stack">
                        <section className="tender-lab-card">
                          <div className="tender-lab-card-title">
                            <Database size={17} />
                            <div>
                              <span>Official open data</span>
                              <h4>Award history context</h4>
                            </div>
                          </div>
                          <p>
                            Search historical awarded supplier records by description  then inspect the
                            actual sample before using its range as context
                          </p>
                          <div className="tender-lab-award-search">
                            <label>
                              <span>Description keyword</span>
                              <input
                                aria-label="Award description keyword"
                                value={awardQuery}
                                onChange={(event) => setAwardQuery(event.target.value)}
                              />
                            </label>
                            <label>
                              <span>Agency contains  optional</span>
                              <input
                                aria-label="Award agency filter"
                                placeholder="e.g. Civil Aviation"
                                value={awardAgency}
                                onChange={(event) => setAwardAgency(event.target.value)}
                              />
                            </label>
                            <button
                              disabled={loadingAwards || awardQuery.trim().length < 2}
                              onClick={() => void searchAwards()}
                            >
                              {loadingAwards ? <LoaderCircle className="spin" size={15} /> : <Search size={15} />}
                              {loadingAwards ? "Searching" : "Search records"}
                            </button>
                          </div>
                        </section>

                        {!awardContext ? (
                          <section className="tender-lab-card tender-lab-award-empty">
                            <Database size={22} />
                            <div>
                              <h4>No figures until a source query runs</h4>
                              <p>The operational decision above does not consume market data automatically</p>
                            </div>
                          </section>
                        ) : (
                          <>
                            <section className="tender-lab-card">
                              <div className="tender-lab-card-title">
                                <Database size={17} />
                                <div>
                                  <span>{awardContext.provenance.status.replaceAll("_", " ")}</span>
                                  <h4>{awardContext.provenance.dataset_title}</h4>
                                </div>
                                <a
                                  className="tender-lab-source-link"
                                  href={awardContext.provenance.source_url}
                                  rel="noreferrer"
                                  target="_blank"
                                >
                                  View source <ExternalLink size={13} />
                                </a>
                              </div>
                              <div className="tender-lab-award-stats">
                                <div><small>Retained rows</small><strong>{awardContext.summary.sample_count}</strong></div>
                                <div><small>Distinct tenders</small><strong>{awardContext.summary.distinct_tenders}</strong></div>
                                <div><small>Median award</small><strong>{money(awardContext.summary.median_sgd)}</strong></div>
                                <div><small>Middle 50%</small><strong>{money(awardContext.summary.lower_quartile_sgd)} – {money(awardContext.summary.upper_quartile_sgd)}</strong></div>
                              </div>
                              <p className="tender-lab-method">
                                {awardContext.provenance.limitation}  {awardContext.excluded_rows} returned
                                placeholder or non supplier-award row(s) excluded
                              </p>
                              {payload.mode === "SME" && awardContext.records.length > 0 && (
                                <div className="tender-lab-public-actions">
                                  {payload.pricing && (
                                    <button className="tender-lab-public-context" onClick={useAwardContext}>
                                      Use {awardContext.records.length} values for pricing context
                                      <ArrowRight size={14} />
                                    </button>
                                  )}
                                  <button
                                    className="tender-lab-public-context partner"
                                    disabled={buildingPartnerPackage}
                                    onClick={() => void buildPartnerPackage()}
                                  >
                                    {buildingPartnerPackage ? <LoaderCircle className="spin" size={14} /> : <Route size={14} />}
                                    {buildingPartnerPackage ? "Building package" : "Build partner research package"}
                                  </button>
                                </div>
                              )}
                            </section>

                            <section className="tender-lab-card">
                              <div className="tender-lab-card-title">
                                <FlaskConical size={17} />
                                <div>
                                  <span>{awardContext.intelligence.sample_strength} SAMPLE</span>
                                  <h4>Agency pattern  descriptive only</h4>
                                </div>
                              </div>
                              <div className="tender-lab-award-stats tender-lab-pattern-stats">
                                <div><small>Suppliers</small><strong>{awardContext.intelligence.supplier_count}</strong></div>
                                <div><small>Repeat suppliers</small><strong>{awardContext.intelligence.recurring_supplier_count}</strong></div>
                                <div><small>Price dispersion</small><strong>{awardContext.intelligence.price_dispersion_percent === null ? "—" : `${awardContext.intelligence.price_dispersion_percent}%`}</strong></div>
                                <div><small>Date window</small><strong>{awardContext.intelligence.date_start ?? "—"} – {awardContext.intelligence.date_end ?? "—"}</strong></div>
                              </div>
                              <ul className="tender-lab-observations">
                                {awardContext.intelligence.observations.map((observation) => <li key={observation}>{observation}</li>)}
                              </ul>
                              {awardContext.intelligence.top_suppliers.length > 0 && (
                                <div className="tender-lab-supplier-patterns">
                                  {awardContext.intelligence.top_suppliers.slice(0, 3).map((supplier) => (
                                    <div key={supplier.supplier_name}>
                                      <span>{supplier.supplier_name}</span>
                                      <strong>{supplier.award_rows} award row{supplier.award_rows === 1 ? "" : "s"}</strong>
                                      <small>{supplier.row_share_percent}% of sample</small>
                                    </div>
                                  ))}
                                </div>
                              )}
                              <p className="tender-lab-method">{awardContext.intelligence.boundary}</p>
                            </section>

                            <section className="tender-lab-card tender-lab-award-records">
                              <div className="tender-lab-card-title">
                                <FileText size={17} />
                                <div><span>Underlying sample</span><h4>Records used in the figures</h4></div>
                              </div>
                              {awardContext.records.length ? (
                                <div className="tender-lab-award-table-wrap">
                                  <table>
                                    <thead><tr><th>Award</th><th>Tender</th><th>Agency / supplier</th><th>Amount</th></tr></thead>
                                    <tbody>
                                      {awardContext.records.map((record) => (
                                        <tr key={`${record.tender_no}-${record.supplier_name}`}>
                                          <td>{record.award_date}</td>
                                          <td><strong>{record.tender_no}</strong><span>{record.tender_description}</span></td>
                                          <td><strong>{record.agency}</strong><span>{record.supplier_name}</span></td>
                                          <td>{money(record.awarded_amt_sgd)}</td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                </div>
                              ) : (
                                <p>No retained rows matched this query  try a broader description keyword</p>
                              )}
                            </section>
                          </>
                        )}
                      </div>
                    )}

                    {tab === "change" && (
                      <div className="tender-lab-stack">
                        <section className="tender-lab-card tender-lab-change-input">
                          <div className="tender-lab-card-title">
                            <GitCompareArrows size={17} />
                            <div><span>Stateless what-if</span><h4>Rehearse a tender amendment</h4></div>
                            <button
                              className="tender-lab-secondary"
                              disabled={simulatingChange}
                              onClick={() => {
                                setChangeSourceLabel("Corrigendum 3.pdf");
                                setAmendmentText(CHANGE_SAMPLE);
                                invalidateChangeSimulation();
                              }}
                            >
                              Load sample change
                            </button>
                          </div>
                          <p>
                            Paste the exact amendment wording  the system will compare controls deadlines
                            assumptions and the direct route without changing this workspace
                          </p>
                          <div className="tender-lab-change-fields">
                            <label className="tender-lab-field">
                              <span>Amendment source</span>
                              <input
                                aria-label="Amendment source"
                                disabled={simulatingChange}
                                value={changeSourceLabel}
                                onChange={(event) => {
                                  setChangeSourceLabel(event.target.value);
                                  invalidateChangeSimulation();
                                }}
                              />
                            </label>
                            <label className="tender-lab-upload">
                              {extracting === "amendment" ? <LoaderCircle className="spin" size={15} /> : <Upload size={15} />}
                              Import PDF / TXT
                              <input
                                aria-label="Import tender amendment"
                                accept=".pdf,.txt,.md,text/plain,application/pdf"
                                disabled={extracting !== null || simulatingChange}
                                onChange={(event) => void uploadAmendment(event.target.files?.[0])}
                                type="file"
                              />
                            </label>
                          </div>
                          <label className="tender-lab-field tender-lab-textarea tender-lab-change-text">
                            <span>Exact amendment wording</span>
                            <textarea
                              aria-label="Exact amendment wording"
                              disabled={simulatingChange}
                              value={amendmentText}
                              onChange={(event) => {
                                setAmendmentText(event.target.value);
                                invalidateChangeSimulation();
                              }}
                            />
                          </label>
                          <button
                            className="tender-lab-change-run"
                            disabled={simulatingChange || amendmentText.trim().length < 20 || changeSourceLabel.trim().length < 2}
                            onClick={() => void simulateChange()}
                          >
                            {simulatingChange ? <LoaderCircle className="spin" size={15} /> : <GitCompareArrows size={15} />}
                            {simulatingChange ? "Rehearsing change" : "Run change rehearsal"}
                          </button>
                        </section>

                        {changeSimulation && (
                          <>
                            <section className="tender-lab-card tender-lab-change-snapshot">
                              <div className="tender-lab-card-title">
                                <GitCompareArrows size={17} />
                                <div><span>Before and simulated after</span><h4>Decision state movement</h4></div>
                              </div>
                              <div className="tender-lab-change-compare">
                                <article>
                                  <span>BASELINE</span>
                                  <strong>{changeSimulation.before.direct_route_status}</strong>
                                  <small>{changeSimulation.before.mandatory_gap_count} mandatory gap(s)</small>
                                  <small>{changeSimulation.before.review_item_count} review item(s)</small>
                                  <small>Earliest extracted  {changeSimulation.before.next_milestone ? formatMilestone(changeSimulation.before.next_milestone) : "not found"}</small>
                                </article>
                                <ArrowRight size={18} />
                                <article className="after">
                                  <span>SIMULATED AFTER</span>
                                  <strong>{changeSimulation.simulated_after.direct_route_status}</strong>
                                  <small>{changeSimulation.simulated_after.mandatory_gap_count} mandatory gap(s)</small>
                                  <small>{changeSimulation.simulated_after.review_item_count} review item(s)</small>
                                  <small>Earliest extracted  {changeSimulation.simulated_after.next_milestone ? formatMilestone(changeSimulation.simulated_after.next_milestone) : "not found"}</small>
                                </article>
                              </div>
                              <div className="tender-lab-change-trace">
                                {changeSimulation.trace.map((step, index) => (
                                  <div key={step.id} className={step.status === "SKIPPED" ? "skipped" : ""}>
                                    <span>{index + 1}</span>
                                    <p><strong>{step.label}</strong><small>{step.detail}</small></p>
                                  </div>
                                ))}
                              </div>
                            </section>

                            <section className="tender-lab-card">
                              <div className="tender-lab-card-title">
                                <ShieldCheck size={17} />
                                <div><span>Re-verification</span><h4>Controls affected by the change</h4></div>
                              </div>
                              {changeSimulation.control_changes.length ? (
                                <div className="tender-lab-change-controls">
                                  {changeSimulation.control_changes.map((change) => (
                                    <article key={change.id}>
                                      <div>
                                        <span>{change.change_type.replaceAll("_", " ")}</span>
                                        <strong>{change.check.risk}</strong>
                                      </div>
                                      <h4>{change.title}</h4>
                                      <p className="tender-lab-change-status">
                                        <span>{change.before_status ?? "NOT IN BASELINE"}</span>
                                        <ArrowRight size={13} />
                                        <strong>{change.simulated_status}</strong>
                                      </p>
                                      <blockquote>{change.source.location}  {change.source.excerpt}</blockquote>
                                      <p>{change.check.next_step}</p>
                                    </article>
                                  ))}
                                </div>
                              ) : <p>No configured control signal was found in this amendment  manual comparison still applies</p>}
                            </section>

                            <section className="tender-lab-card tender-lab-change-effects">
                              <div className="tender-lab-card-title">
                                <BriefcaseBusiness size={17} />
                                <div><span>{changeSimulation.commercial_recheck.status.replaceAll("_", " ")}</span><h4>Downstream effects</h4></div>
                              </div>
                              <p>{changeSimulation.commercial_recheck.impact}</p>
                              {changeSimulation.commercial_recheck.triggers.length > 0 && (
                                <div className="tender-lab-change-trigger-list">
                                  {changeSimulation.commercial_recheck.triggers.map((item) => <span key={item}>{item}</span>)}
                                </div>
                              )}
                              {changeSimulation.milestone_changes.map((milestone) => (
                                <article className="tender-lab-change-milestone" key={`${milestone.id}-${milestone.simulated_starts_at}`}>
                                  <span>{milestone.change_type}</span>
                                  <div>
                                    <strong>{milestone.label}</strong>
                                    <small>{milestone.previous_starts_at ? formatMilestone(milestone.previous_starts_at) : "Not in baseline"} → {formatMilestone(milestone.simulated_starts_at)}</small>
                                  </div>
                                </article>
                              ))}
                              {changeSimulation.invalidated_outputs.length > 0 && (
                                <div className="tender-lab-invalidated">
                                  <small>Outputs that are now stale</small>
                                  <ul>{changeSimulation.invalidated_outputs.map((item) => <li key={item}>{item}</li>)}</ul>
                                </div>
                              )}
                            </section>

                            {changeSimulation.clarification_questions.length > 0 && (
                              <section className="tender-lab-card">
                                <div className="tender-lab-card-title"><Clipboard size={17} /><div><span>Amendment ambiguity</span><h4>Clarification drafts</h4></div></div>
                                {changeSimulation.clarification_questions.map((item) => (
                                  <article className="tender-lab-question" key={item.id}>
                                    <span>{item.id}</span><div><h4>{item.issue}</h4><p>{item.question}</p><small>{item.commercial_impact}</small></div>
                                  </article>
                                ))}
                              </section>
                            )}

                            <section className="tender-lab-card tender-lab-change-recovery">
                              <div className="tender-lab-card-title"><BookOpenCheck size={17} /><div><span>Replanned</span><h4>Recovery sequence</h4></div></div>
                              <ol>{changeSimulation.recovery_actions.map((item) => <li key={item}>{item}</li>)}</ol>
                              <ul>{changeSimulation.boundaries.map((item) => <li key={item}>{item}</li>)}</ul>
                            </section>
                          </>
                        )}
                      </div>
                    )}

                    {tab === "plan" && (
                      <div className="tender-lab-stack">
                        <section className="tender-lab-card">
                          <div className="tender-lab-card-title"><BookOpenCheck size={17} /><div><span>Reviewable plan</span><h4>Next actions</h4></div></div>
                          <div className="tender-lab-actions">
                            {result.next_actions.map((action) => <article key={`${action.priority}-${action.title}`}><span>{action.priority}</span><div><h4>{action.title}</h4><p>{action.reason}</p><small>{action.owner_role}{action.due_before ? `  ·  before ${formatMilestone(action.due_before)}` : ""}</small></div></article>)}
                          </div>
                        </section>
                        <section className="tender-lab-card">
                          <div className="tender-lab-card-title"><CalendarPlus size={17} /><div><span>Local export</span><h4>Tender milestones</h4></div><button className="tender-lab-secondary" disabled={!result.milestones.length} onClick={downloadCalendar}><CalendarPlus size={14} /> Download .ics</button></div>
                          <div className="tender-lab-milestones">
                            {result.milestones.map((milestone) => {
                              const calendarUrl = googleCalendarUrl(payload.tender_title, milestone);
                              return (
                                <article key={milestone.id}>
                                  <span>{formatMilestone(milestone.starts_at)}</span>
                                  <div><h4>{milestone.label}</h4><p>{milestone.tender_source.location}  {milestone.tender_source.excerpt}</p></div>
                                  <div className="tender-lab-milestone-actions">
                                    <small>{milestone.confidence}</small>
                                    {calendarUrl && (
                                      <a href={calendarUrl} rel="noreferrer" target="_blank">
                                        Google Calendar <ExternalLink size={10} />
                                      </a>
                                    )}
                                  </div>
                                </article>
                              );
                            })}
                          </div>
                          {!result.milestones.length && <p>No parseable date found  check the source manually</p>}
                        </section>
                      </div>
                    )}
                  </div>
                </>
              )}
            </main>
          </div>
        )}
      </section>
    </div>
  );
}
