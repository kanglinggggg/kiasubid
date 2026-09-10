# Judge Q&A

These answers describe the build we can demonstrate today. They separate working product behavior,
measured Bedrock results, and limitations that still need human review.

## Why not ChatGPT plus Excel?

ChatGPT can summarize prose and Excel can track rows, but neither combination automatically gives
us stable requirement identities, immutable versions, evidence links, superseded assessments,
dependency-aware recovery tasks, deterministic gate precedence, dated cross-opportunity demand, or
a reproducible audit trail. BidOps uses an LLM only to translate tender language into validated
structured data. Ordinary code then owns the operational calculation. The value is controlled state
propagation, not a chat answer.

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

BidOps is agentic in a narrow operational sense: it carries a change across the bid instead of
returning a one-off chat answer. LangGraph coordinates requirement versioning, assessment
superseding, evidence rechecks, recovery planning, metric updates, and the audit trail. Every step
reads and writes typed state and stops when the evidence is insufficient. The portfolio extension
continues that chain from a validated clause change to a dated capability-demand delta, collision
calculation, counterfactual options, human decision, and capability roadmap. Bedrock interprets the
language; rules calculate bid and portfolio states; a person keeps every decision and external
action.

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
- peak capability demand across supplied overlapping service windows, portfolio-state precedence,
  counterfactual route outcomes, and known-gap roadmap items;
- duplicate-corrigendum protection and persistence.

Human-controlled: source completeness, ambiguous-clause clarification, evidence verification,
staffing and partner facts, route selection, commercial judgment, final approval, and GeBIZ
submission.

## What does the new portfolio view prove?

It proves one deterministic consequence within the supplied scenario. R17 changes from three to
four required capability slots. A synthetic companion opportunity requires one more slot in an
overlapping service period. Peak demand therefore changes from four to five, while identified
potential capacity remains four. The hard shortfall is one.

The current bid and the portfolio are separate scopes. The amended bid is `RECOVERABLE` because
Engineer D's evidence and availability may be completed. The continue-all portfolio is `BLOCKED`
because even that potential fourth slot does not satisfy five concurrent slots.

## Where did the companion opportunity and capacity data come from?

They are synthetic demo inputs. The companion opportunity, service windows, three proven slots,
one potential slot, and no-double-booking assumption do not come from GeBIZ, ACRA, an HR system, a
calendar, or a customer. The UI labels the panel **Simulation only** and **Synthetic demo**, and its
assumptions remain inspectable.

The generic API accepts equivalent caller-supplied facts. Production use would require an
authoritative integration and human confirmation; that is not part of this MVP.

## Is this a staff scheduler?

No. The simulator works with aggregate capability counts and dated demand windows. It does not
persist or optimise named-person assignments, inspect calendars, reserve staff, or prove who will
serve each tender. Engineer D appears in the bid-level evidence recovery story; the portfolio
arithmetic does not constitute a named assignment.

## How are the three routes chosen?

They are deterministic counterfactuals under the displayed assumptions:

- protect the current tender and expose the effect on the companion commitment;
- protect the companion commitment and expose the effect on the current tender; or
- verify additional capacity, which remains `UNCERTAIN` until partner qualification, availability,
  and permission are established.

They are not recommendations and are not ranked by price, margin, strategic value, or win
probability. Selecting a card changes only the displayed scenario. A human must decide and perform
any follow-up.

## What is the capability roadmap for?

It aggregates known evidence and capacity gaps across the opportunities active at the constrained
overlap. For the demo, it first exposes the one additional slot required to remove the hard
concurrent shortfall, followed by the unresolved evidence/availability for one potential slot.

For a startup or early-stage supplier, this can frame a concrete capability-development discussion:
which known eligibility gaps recur in its selected opportunity set. It is not a training plan,
hiring instruction, proposal generator, or forecast that an investment will produce an award or
revenue.

## Does BidOps predict price or the chance of winning?

No. This build has no verified market dataset, pricing model, margin optimiser, or award-probability
model. The portfolio routes compare operational capacity consequences only. We do not infer agency
preferences or claim that historical prices determine a future award.

## Is the portfolio capability unique?

We do not claim a world first. Document review, amendment tracking, and capacity planning exist in
the market. Our demonstrated focus is the connected audit chain: a source-linked semantic change
alters a dated capability obligation, which changes cross-tender feasibility and exposes
human-controlled counterfactuals and recurring gaps. Judges can inspect each link rather than take
an originality superlative on trust.

## Does the demo prove IM8, PWM, or other policy compliance?

No. R17 and its documents are original synthetic tender text. BidOps demonstrates a framework for
source-linked requirements; it does not claim that IM8, PWM, a fixed social-value score, or any
other policy applies universally. Applying the product to a real tender would require the actual
authoritative documents, scoped interpretation, and human review.

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

No. The main synthetic fixture is clearly labelled **Interpretation: Demo fallback**, so the
product story remains reliable offline. With the active sandbox, Nova Lite has
also completed the live R17 path; the UI changed to **Interpretation: Bedrock** only after that
result was persisted. The post-hardening known regression remains mixed: exact requirement
interpretation passed 6/7, corrigendum matching passed 2/2, ambiguity handling passed 9/9, and
final operational state passed 8/9. The frozen blind-v1 set scored 2/8, not applicable, 7/8, and 4/8
respectively, with zero unsafe-green errors.

## What evidence do you have today?

- backend and frontend regression tests;
- Ruff, TypeScript, production build, and npm audit checks;
- a 9/9 GeBIZ-derived deterministic regression benchmark across the six generic rule types;
- mocked Bedrock/Groq boundaries, malformed-output, provenance, ambiguity, injection, semantic
  isolation, duplicate, and R17 end-to-end tests;
- a real Nova Lite Bedrock smoke test and live R17 `FEASIBLE → RECOVERABLE` transition;
- a live final known regression of 6/7 requirement interpretation, 2/2 corrigendum matching,
  9/9 ambiguity handling, and 8/9 final state, with every failure retained;
- a frozen eight-case blind result of 2/8 requirement interpretation, 7/8 ambiguity handling, and
  4/8 final state, with zero unsafe-green errors;
- deterministic portfolio tests for overlapping and adjacent service windows, hard shortfall,
  missing mandatory count, unsupported capability input, non-persistence, and preservation of the
  R17 bid-level hero state;
- saved desktop and mobile QA screenshots and three repeatable main-demo runs.

The nine regression cases informed development and are not presented as unseen model accuracy.
The separate U1-U8 blind-v1 cases were frozen before their first successful model run. They were
not used to select this round's prompt, normalizers, or model, and were not rerun after those
known-regression-driven changes. A separate empty blind-v2 intake is ready for the next teammate-
sealed evaluation.

## What are the current limitations?

- Nova Lite v1 does not support Bedrock-native `outputConfig`; it uses prompted JSON followed by
  strict Pydantic and provenance validation. Claude Haiku 4.5 native structured output remains
  blocked because the sandbox role lacks the required AWS Marketplace subscription actions.
- Exact requirement interpretation remains the main limitation: 6/7 on known regression and 2/8
  on the historical frozen blind-v1 run. Corrigendum matching, ambiguity safety, zero unsafe-green outcomes, and
  the R17 hero path are the stronger live results.
- The demo uses synthetic tender, company, evidence, and personnel data.
- The portfolio companion opportunity, service windows, capability counts, and no-double-booking
  assumption are synthetic. The simulator is aggregate and does not schedule named people.
- Input is extracted page/section text; PDF upload, OCR, and live GeBIZ retrieval are outside scope.
- Extraction completeness remains below release quality and still requires human review and
  broader independent evaluation.
- SQLite and the local single-user process are demonstration architecture, not production
  multi-user deployment.
- There is no authentication, proposal generation, pricing or margin optimisation, award
  probability, competitor intelligence, staff allocation, partner outreach, automatic bid
  withdrawal, or automatic submission.
- The capability roadmap addresses known gaps in the supplied opportunity set; it does not predict
  qualification, awards, revenue, or startup growth.
