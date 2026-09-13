import { useState } from "react";
import type { AgentLoopResponse, TenderLabRequest, TenderLabResponse, TenderLabSourceReference } from "../types/tenderLab";

export function SourceQuote({ source }: { source: TenderLabSourceReference }) {
  return <details className="readiness-source"><summary>{source.source_label} · {source.location}</summary><blockquote>{source.excerpt}</blockquote></details>;
}

export function StructuredBrief({ result }: { result: TenderLabResponse }) {
  const [category, setCategory] = useState("All");
  const clauses = result.brief.clauses ?? [];
  const categories = [...new Set(clauses.flatMap(c => c.categories))];
  const visible = clauses.filter(c => category === "All" || c.categories.includes(category));
  return <section className="tender-lab-card readiness-panel">
    <h4>Tender action plan</h4>
    <p>{result.brief.method}</p>
    <label>Show source section <select value={category} onChange={event => setCategory(event.target.value)}>
      <option>All</option>{categories.map(c => <option key={c}>{c}</option>)}
    </select></label>
    <small>{visible.length} of {clauses.length} extracted clauses · check all pages for completeness</small>
    <div className="readiness-clauses">{visible.map(clause => <article key={clause.id}>
      <small>{clause.id} · {clause.categories.join(" / ")}</small>
      <p>{clause.plain_language}</p><SourceQuote source={clause.source} />
    </article>)}</div>
    {!!result.brief.missing_sections?.length && <p className="readiness-warning">Not identified in supplied text  {result.brief.missing_sections.join(" · ")}  Review the original tender or request clarification</p>}
  </section>;
}

export function FitAndRecommendation({ result }: { result: TenderLabResponse }) {
  const fit = result.company_fit;
  const rec = result.recommendation;
  return <>
    {rec && <section className="tender-lab-card readiness-panel" aria-label="Consolidated readiness recommendation">
      <span className="eyebrow">{rec.action.replaceAll("_", " ")}</span>
      <h4>{rec.headline}</h4>
      <ul>{rec.reasons.map((reason, i) => <li key={i}>{reason}</li>)}</ul>
      <small>Evidence IDs  {rec.evidence_ids.join(" · ") || "Workspace inputs / missing draft"}</small>
      {!!rec.alternatives.length && <><h5>Alternative path to investigate</h5><ul>{rec.alternatives.map(a => <li key={a}>{a}</li>)}</ul></>}
      {!!rec.missing_information.length && <details><summary>Information still needed · {rec.missing_information.length}</summary><ul>{rec.missing_information.map(m => <li key={m}>{m}</li>)}</ul></details>}
      <p className="readiness-warning">Screening recommendation only  Use the separate five-agent review packet and ask the bid owner to verify the evidence before any submission</p>
    </section>}
    {fit && <section className="tender-lab-card readiness-panel">
      <span className="eyebrow">{fit.status.replaceAll("_", " ")}</span><h4>Company bid-fit assessment</h4>
      <p>Company age  {fit.company_age_years === null ? "Unknown" : `${fit.company_age_years} completed years`} · Assessed {fit.assessed_on}</p>
      {fit.checks.map(check => <article className="readiness-fit" key={check.id}>
        <span className={`readiness-badge ${check.status.toLowerCase()}`}>{check.status}</span><h5>{check.area}</h5>
        <p>{check.company_fact}</p><p>{check.explanation}</p><small>Next  {check.next_step}</small>
        {check.source && <SourceQuote source={check.source} />}
      </article>)}
      <p className="tender-lab-method">{fit.boundary}</p>
    </section>}
  </>;
}

export function QualityPanel({ result }: { result: TenderLabResponse }) {
  const quality = result.quality_advisor;
  if (!quality) return <p>Run the review to inspect published quality criteria</p>;
  return <section className="tender-lab-card readiness-panel">
    <span className="eyebrow">Tender-specific suggestions · not a sixth agent</span><h4>Socio-economic and quality advisor</h4>
    {quality.opportunities.length ? quality.opportunities.map(item => <article className="readiness-fit" key={item.id}>
      <h5>{item.topic}</h5><SourceQuote source={item.criterion} />
      <h5>Suggested commitment scaffold</h5><p>{item.suggested_commitment}</p>
      <small>Suggested owner  {item.owner_role}</small>
      <ul>{item.evidence_needed.map(e => <li key={e}>{e}</li>)}</ul><p>{item.cost_consideration}</p>
      <p className="readiness-warning">Review and replace every placeholder with an achievable, approved commitment before copying into the proposal</p>
    </article>) : <p>No relevant published quality-scoring criterion was detected  SkillsFuture  ESG or social-value wording will not be added as an assumed scoring benefit  Upload the evaluation schedule if it is in a separate document</p>}
    <p className="tender-lab-method">{quality.boundary}</p>
  </section>;
}

export function GuidancePanel({ result }: { result: TenderLabResponse }) {
  return <section className="tender-lab-card readiness-panel"><h4>Retrieved official-source guidance</h4>
    <p>Local retrieval over versioned summaries of official public guidance  These passages also enter the five-agent evidence packet  They are not a live policy lookup or the full policy manual</p>
    {!result.retrieved_guidance?.length && <p>No matching guidance in the current source pack  This does not imply there are no applicable policies</p>}
    {result.retrieved_guidance?.map(item => <article className="readiness-fit" key={item.id}>
      <h5><a href={item.url} target="_blank" rel="noreferrer">{item.title}</a></h5>
      <small>{item.id} · {item.publisher} · reviewed {item.reviewed_on} · Curated summary</small>
      <p>{item.passage}</p><p>{item.limitation}</p><small>Matched tender terms  {item.matched_terms.join(" · ")}</small>
    </article>)}
  </section>;
}

export function buildReadinessReport(payload: TenderLabRequest, result: TenderLabResponse, agents: AgentLoopResponse | null): string {
  const recommendation = result.recommendation;
  const lines = [
    `# Bid readiness review — ${payload.tender_title}`,
    `Mode: ${result.mode} · Company: ${payload.company.name}`,
    `Input: ${payload.source_label} (${result.source_type})`,
    "",
    "## Screening recommendation",
    recommendation ? `Action: ${recommendation.action.replaceAll("_", " ")}` : "Action: Not available",
    recommendation?.headline ?? "Not available",
    ...(recommendation?.reasons ?? []).map(r => `- ${r}`),
    `Evidence IDs: ${recommendation?.evidence_ids.join(", ") || "Workspace input or missing information"}`,
    ...(recommendation?.alternatives ?? []).map(a => `Alternative to investigate: ${a}`),
    ...(recommendation?.missing_information ?? []).map(m => `Missing information: ${m}`),
    "Human review required before submission.",
    "",
    "## Company bid fit",
  ];
  for (const check of result.company_fit?.checks ?? []) lines.push(`### ${check.id} — ${check.area} (${check.status})`, check.company_fact, check.explanation, `Next: ${check.next_step}`);
  if (result.company_fit?.boundary) lines.push(result.company_fit.boundary);
  lines.push("", "## Tender action plan");
  for (const clause of result.brief.clauses ?? []) lines.push(`### ${clause.id} — ${clause.categories.join(" / ")}`, clause.plain_language, `Source: ${clause.source.source_label}, ${clause.source.location}`, `> ${clause.source.excerpt}`);
  for (const section of result.brief.missing_sections ?? []) lines.push(`Missing section to verify: ${section}`);
  lines.push("", "## Compliance review");
  for (const check of result.policy_checks) lines.push(`### ${check.id} — ${check.title} (${check.status})`, check.rationale, `Source: ${check.tender_source.source_label}, ${check.tender_source.location}`, `> ${check.tender_source.excerpt}`, `Proposal evidence: ${check.proposal_evidence ?? "Not found"}`, `Next: ${check.next_step}`, ...(check.remediation ? [check.remediation.draft, check.remediation.boundary] : []));
  lines.push("", "## Clarifications");
  if (!result.clarification_questions.length) lines.push("No clarification question was generated from the supplied text.");
  for (const item of result.clarification_questions) lines.push(`### ${item.id} — ${item.issue}`, item.question, `Commercial impact: ${item.commercial_impact}`, `Source: ${item.tender_source.source_label}, ${item.tender_source.location}`, `> ${item.tender_source.excerpt}`);
  lines.push("", "## Quality opportunities");
  for (const q of result.quality_advisor?.opportunities ?? []) lines.push(`### ${q.topic}`, `Source: ${q.criterion.source_label}, ${q.criterion.location}`, `> ${q.criterion.excerpt}`, q.suggested_commitment, `Owner: ${q.owner_role}`, q.cost_consideration, ...q.evidence_needed.map(e => `- ${e}`));
  if (result.quality_advisor && !result.quality_advisor.opportunities.length) lines.push("No relevant published quality-scoring criterion was detected. No SkillsFuture, ESG or social-value scoring benefit was assumed.");
  lines.push(result.quality_advisor?.boundary ?? "", "", "## Milestones");
  for (const m of result.milestones) lines.push(`- ${m.label}: ${m.starts_at} ${m.timezone} (${m.confidence}) — ${m.tender_source.location}: ${m.tender_source.excerpt}`);
  lines.push("", "## Action checklist");
  for (const a of result.next_actions) lines.push(`- ${a.title} — ${a.owner_role} — due ${a.due_before ?? "needs confirmation"} — ${a.reason}`);
  lines.push("", "## Commercial context");
  if (result.pricing) lines.push(
    `Proposed price: SGD ${result.pricing.proposed_price_sgd.toLocaleString("en-SG")}`,
    `Estimated cost: SGD ${result.pricing.estimated_cost_sgd.toLocaleString("en-SG")}`,
    `Gross margin: ${result.pricing.gross_margin_percent}%`,
    `Comparable award records: ${result.pricing.comparable_count} · Confidence: ${result.pricing.confidence}`,
    result.pricing.position,
    result.pricing.comparables_note,
    result.pricing.boundary,
  );
  else lines.push("No pricing inputs were supplied for this run.");
  for (const route of result.strategy_routes) lines.push(`### ${route.title} (${route.status})`, route.rationale, ...route.unresolved_facts.map(f => `Unresolved: ${f}`), "Human decision required; no contact or submission was performed.");
  lines.push("", "## Retrieved guidance");
  for (const g of result.retrieved_guidance ?? []) lines.push(`- ${g.id} [${g.title}](${g.url}) — curated summary reviewed ${g.reviewed_on}`, g.passage, g.limitation);
  lines.push("", "## Five-agent review", agents ? JSON.stringify(agents, null, 2) : "Not run for this input. The screening recommendation is not a five-agent approval.", "", "## Human review boundaries", ...result.boundaries.map(b => `- ${b}`));
  return lines.join("\n\n");
}
