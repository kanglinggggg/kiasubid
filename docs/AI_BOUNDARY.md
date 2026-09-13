# Runtime AI boundary

GeBIZ BidOps uses the selected language model in four bounded workflow areas; Agent Room itself
contains five logical agents:

1. **Tender Requirement Interpretation** converts supplied tender page/section text into validated Pydantic `StructuredRequirement` records. It preserves document, page, section, and an exact source snippet. Ambiguous details must be returned as `UNCERTAIN` and left null.
2. **Corrigendum Semantic Change Interpretation** compares one existing structured requirement with new corrigendum text. It returns `ADDED`, `MODIFIED`, `REMOVED`, or `UNCHANGED`, the affected stable key when identifiable, and the exact structured fields changed.
3. **Tender Lab Agent Room** contains five logical agents: one planner, three fixed specialists
   (compliance, commercial, and timeline), and one critic. The critic checks every returned finding
   against allowed evidence IDs and may request at most one revision round. Ordinary code restores
   omitted roles, rejects unknown evidence references, and creates the final human decision packet.
4. **Startup Proposal Studio** critiques eight recorded founder answers and may turn the seven
   required answers into a supplier-response preparation draft; the eighth, social-value answer is
   optional, and users are told to skip it unless they have a grounded, tender-relevant commitment.
   The model must
   retain the recorded answer in each rewritten section, cite recorded answer fields, avoid new
   numeric, certainty, technology, certification, or capability claims, and place missing proof in
   a marked open-items block. That block is excluded when the generated draft is rescanned as
   proposal evidence, preventing an unresolved item from becoming a false supported control.

The separate socio-economic and quality advisor is deterministic tender-clause screening, not a
model invocation or sixth Agent Room agent. It cannot invent evaluation points, funding
eligibility, accreditation, or company commitments.

The production path calls Amazon Bedrock Runtime's Converse API. A temporary Groq path is also
available for authorized local validation through Groq's OpenAI-compatible Chat Completions API.
Every model path uses near-zero temperature, requests JSON-schema output, validates again with
Pydantic, and makes one repair retry by default. The corrigendum path additionally checks changed-
field old/new values against supplied structures. Source document, page, and section come from the
trusted request envelope. A requirement-interpretation response with a non-contiguous or fabricated
source snippet fails validation and is retried; it is not silently accepted.

After validation, ordinary code maps the six typed procurement-rule kinds to the supported
requirement/gate vocabulary, projects explicitly represented rule fields into stable
structured fields, and assigns unique stable-key suffixes to multiple obligations from one passage.
It may normalize vocabulary aliases such as `QUALIFICATION` to `COMPLIANCE`, but it cannot add a
missing qualification, count, deadline, or criticality. A processing duration without an
authoritative deadline remains deadline-null; bidder/tender metadata may supply the deadline later.

Tender and corrigendum contents are explicitly treated as untrusted data. Document-embedded text
that asks a model to ignore validation, reveal prompts, call tools, or choose an operational result
has no authority. The clients expose no tools, and adversarial development fixtures exercise this
boundary.

Proposal Studio and Agent Room are stateless and cannot browse, change files, contact suppliers,
approve a response, or submit it. Their visible deterministic fallbacks keep the demo usable when a
provider is unavailable without claiming a live model result.

The model output does not directly write to the database and cannot set an assessment, feasibility
state, coverage percentage, task, or deadline risk. The main corrigendum flow proceeds only when the
validated interpretation is confident, is `MODIFIED`, identifies `R17`, and contains the expected
isolated count change. Otherwise it stops before superseding an assessment.

## Deterministic execution

After interpretation, ordinary code controls all of the following:

- immutable requirement version creation;
- assessment superseding;
- CISSP, CV, validity, and availability evidence matching;
- requirement assessment;
- four-state Operational Feasibility;
- Critical Gates and Submission Coverage;
- recovery candidate selection and dependency-aware recovery tasks;
- Deadline Risk;
- SQLite persistence, calculation traces, audit events, and the UI read model.

LangGraph sequences these deterministic mutations, but LangGraph itself is not an LLM. Assessments remain labelled `RULE` because no assessment is model-generated.

## Demo fallback

If the selected provider is not configured, unavailable, or repeatedly returns malformed structured
output, a deliberately narrow rule-based parser handles the synthetic main fixture. This is
not an LLM. The UI displays `Interpretation: Bedrock` or `Interpretation: Groq` only after a
completed workflow has persisted that actual provider mode; configuration alone is not enough.
Otherwise it displays `Interpretation: Demo fallback`.

The fallback understands the demo's CISSP manpower count amendment, explicit removal,
equivalent-count wording, obvious deadline-only changes, and ambiguous clauses. Unmatched language
returns `UNCERTAIN`; it does not guess.
Instruction-like source text addressed to a model or AI also returns `UNCERTAIN` and cannot apply a
change through the fallback.

## Human control

Humans control which tender text is supplied, whether the synthetic scenario or an authorized live
provider is used, evidence verification, task completion, final interpretation review, internal
approval, and any real tender submission. BidOps never submits to GeBIZ or makes a binding legal or
commercial decision.

## Evaluation boundary

The evaluation-only harness under `backend/evaluation/` keeps synthetic development fixtures, the
nine known GeBIZ-derived regression cases, and eight teammate-supplied cases frozen in a distinct
blind partition separate. It invokes interpretation with fallback disabled and scores requirement
extraction, corrigendum matching, and ambiguity handling. Final operational state is scored only
when a frozen downstream adapter or deterministic facts exist; multi-obligation cases can supply
one fact set per typed rule. Missing rule/fact bindings fail closed to `UNCERTAIN`; cases with no
adapter are `NOT_RUN`, not fabricated failures or passes. Unsafe-green errors are reported when
ground truth is `BLOCKED` or `UNCERTAIN` but deterministic output becomes `FEASIBLE`. Expected
answers and deterministic facts are never sent to the model. The separate generic-rule benchmark
scores deterministic requirement results and final bid states. Missing source content is handled
by a deterministic safety guard because sending absent text to a model would invite invention.
