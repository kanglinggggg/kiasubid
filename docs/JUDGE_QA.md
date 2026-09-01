# Judge Q&A

These answers describe the frozen local build. They deliberately distinguish implemented behavior
from planned live-provider validation.

## Why not ChatGPT plus Excel?

ChatGPT can summarize prose and Excel can track rows, but neither combination automatically gives
us stable requirement identities, immutable versions, evidence links, superseded assessments,
dependency-aware recovery tasks, deterministic gate precedence, or a reproducible audit trail.
BidOps uses an LLM only to translate tender language into validated structured data. Ordinary code
then owns the operational decision. The value is controlled state propagation, not a chat answer.

Evidence to show: R17 v1 remains stored after the corrigendum, its assessment becomes
`SUPERSEDED`, R17 v2 is created, and every visible metric exposes backend calculation details.

## What if the LLM misses a mandatory requirement?

The current MVP cannot guarantee perfect recall. That is the most important remaining model-risk
limitation. It reduces the risk by retaining exact source provenance, validating output with strict
Pydantic schemas, treating document text as untrusted data, refusing invented mandatory details,
and returning `UNCERTAIN` when wording is ambiguous. Blind evaluation is separated from the known
regression set, and unsafe-green errors are reported explicitly. Human review remains required;
BidOps does not represent an extraction as a legal or compliance guarantee.

## Why can Submission Coverage be high while status is BLOCKED?

They answer different questions. Submission Coverage measures preparation completeness with a
fixed formula: 50% current requirement assessments, 30% linked usable evidence, and 20% task
completion. Operational Feasibility uses gate precedence. One known mandatory, unrecoverable gate
forces `BLOCKED` even if nearly every other item is complete. This prevents an average score from
hiding a fatal obligation.

Evidence to show: select **BLOCKED · no fourth engineer**. Coverage remains relatively high while
the feasibility card and unresolved-gate explanation show the blocking reason.

## What is actually Agentic AI here?

The product implements a bounded, stateful workflow rather than an open-ended autonomous agent.
LangGraph coordinates change detection, requirement versioning, assessment superseding, evidence
re-evaluation, recovery-task planning, metric recomputation, and activity logging. Each step reads
and writes typed state and stops at safety conditions. The LLM supplies semantic interpretation;
deterministic services make operational decisions; a human retains final approval and submission.

This is intentionally narrow agency: useful autonomy inside a controlled procurement workflow,
not a bot that can decide or submit a bid on its own.

## What is LLM-driven versus deterministic?

LLM-driven, when a configured provider succeeds:

1. extracting typed requirements from supplied page/section text;
2. interpreting a corrigendum as `ADDED`, `MODIFIED`, `REMOVED`, or `UNCHANGED`, matching a stable
   requirement where possible, and listing changed fields.

Deterministic:

- Pydantic validation and exact-snippet provenance checks;
- requirement versioning and `SUPERSEDED` lifecycle state;
- evidence matching and assessment calculation;
- generic procurement-rule evaluation;
- `FEASIBLE`, `RECOVERABLE`, `BLOCKED`, `UNCERTAIN` precedence;
- Critical Gates, Submission Coverage, recovery tasks, dependencies, and Deadline Risk;
- duplicate-corrigendum protection and persistence.

Human-controlled: source completeness, ambiguous-clause clarification, evidence verification,
commercial judgment, final approval, and GeBIZ submission.

## How do you handle hallucination and ambiguity?

Model output is accepted only through strict schemas. Source document, page, section, and snippet
must agree with the supplied input, and the snippet must be an exact substring. Invalid output is
retried within a small fixed limit and otherwise fails gracefully. Ambiguous or missing source text
must remain `UNCERTAIN`; the LLM cannot set feasibility, mark evidence verified, create a pass, or
submit anything. Prompt-injection text is treated as document content, not as an instruction.

The honest limitation is that schema validation cannot prove semantic completeness. That is why
blind cases, unsafe-green reporting, provenance inspection, and human review remain necessary.

## How do corrigenda propagate?

The interpreter compares corrigendum text with an existing structured requirement and returns the
affected stable key plus exact field changes. The workflow creates a new requirement version,
retains the old version, marks only its prior assessment `SUPERSEDED`, rechecks linked evidence,
recomputes the current assessment, creates recovery tasks when justified, and recalculates all
metrics. A deadline-only amendment does not invalidate R17; unrelated changes are isolated; a
duplicate corrigendum returns `409 Conflict` without duplicate versions or tasks.

Evidence to show: **Apply Corrigendum #2** produces R17 minimum `3 → 4`, v1 `SUPERSEDED`, v2
`PARTIAL`, and `FEASIBLE → RECOVERABLE`.

## Why not automatically submit?

Tender submission carries legal declarations, commercial commitments, and irreversible external
effects. The local MVP has no GeBIZ submission integration and deliberately ends at a locked human
checkpoint. Automation supports preparation and verification; an authorized person must review,
approve, and submit through the official channel.

## How is this different from existing GeBIZ functionality?

GeBIZ is the official publication and transaction channel. BidOps does not replace or scrape it.
BidOps is a supplier-side operational control layer after documents are obtained: it turns clauses
into versioned obligations, connects them to internal evidence, detects amendment impact, and makes
the recovery path and deadline consequences visible. There is no claim of privileged GeBIZ data or
an existing GeBIZ integration in this build.

## Why should we trust the percentages and statuses?

The frontend displays backend values and backend-provided trace objects. Operational precedence,
the full mandatory-gate numerator and denominator, the 50/30/20 coverage arithmetic, and the
deadline driver/slack are all deterministic and covered by tests. The UI labels Submission
Coverage as preparation completeness, not a compliance score.

## Does the demo depend on AWS being available?

No. The canonical synthetic fixture is a clearly labelled **Interpretation: Demo fallback**, so
the deterministic product story remains reliable offline. With the active sandbox, Nova Lite has
also completed the live R17 path; the UI changed to **Interpretation: Bedrock** only after that
result was persisted. The post-hardening known regression remains mixed: exact requirement
interpretation passed 4/7, corrigendum matching passed 2/2, ambiguity handling passed 9/9, and
final operational state passed 6/9. The frozen blind set scored 2/8, not applicable, 7/8, and 4/8
respectively, with zero unsafe-green errors.

## What evidence do you have today?

- backend and frontend regression tests;
- Ruff, TypeScript, production build, and npm audit checks;
- a 9/9 GeBIZ-derived deterministic regression benchmark across the six generic rule types;
- mocked Bedrock/Groq boundaries, malformed-output, provenance, ambiguity, injection, semantic
  isolation, duplicate, and R17 end-to-end tests;
- a real Nova Lite Bedrock smoke test and live R17 `FEASIBLE → RECOVERABLE` transition;
- a live post-hardening known regression of 4/7 requirement interpretation, 2/2 corrigendum
  matching, 9/9 ambiguity handling, and 6/9 final state, with every failure retained;
- a frozen eight-case blind result of 2/8 requirement interpretation, 7/8 ambiguity handling, and
  4/8 final state, with zero unsafe-green errors;
- saved desktop and mobile QA screenshots and three repeatable canonical demo runs.

The nine regression cases informed development and are not presented as unseen model accuracy.
The separate U1-U8 blind cases were frozen before their first successful model run and were not
used to tune production prompts after scoring.

## What are the current limitations?

- Nova Lite v1 does not support Bedrock-native `outputConfig`; it uses prompted JSON followed by
  strict Pydantic and provenance validation. Claude Haiku 4.5 native structured output remains
  blocked because the sandbox role lacks the required AWS Marketplace subscription actions.
- Exact requirement interpretation remains the main limitation: 4/7 on known regression and 2/8
  on the frozen blind set. Corrigendum matching, ambiguity safety, zero unsafe-green outcomes, and
  the R17 hero path are the stronger live results.
- The demo uses synthetic tender, company, evidence, and personnel data.
- Input is extracted page/section text; PDF upload, OCR, and live GeBIZ retrieval are outside scope.
- Extraction completeness remains below release quality and still requires human review and
  broader independent evaluation.
- SQLite and the local single-user process are demonstration architecture, not production
  multi-user deployment.
- There is no authentication, proposal generation, pricing optimization, competitor intelligence,
  or automatic submission.
