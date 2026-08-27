# Runtime AI boundary

GeBIZ BidOps has exactly two bounded LLM capabilities when the selected provider is configured:

1. **Tender Requirement Interpretation** converts supplied tender page/section text into validated Pydantic `StructuredRequirement` records. It preserves document, page, section, and an exact source snippet. Ambiguous details must be returned as `UNCERTAIN` and left null.
2. **Corrigendum Semantic Change Interpretation** compares one existing structured requirement with new corrigendum text. It returns `ADDED`, `MODIFIED`, `REMOVED`, or `UNCHANGED`, the affected stable key when identifiable, and the exact structured fields changed.

The production path calls Amazon Bedrock Runtime's Converse API. A temporary Groq path is also
available for authorized local validation through Groq's OpenAI-compatible Chat Completions API.
Both use near-zero temperature, request JSON-schema output, validate again with Pydantic, check
changed-field old/new values against the supplied structures, and make one repair retry by default.
Source document, page, and section come from the trusted request envelope. A model response with a
non-contiguous or fabricated source snippet fails validation and is retried; it is not silently
accepted.

Tender and corrigendum contents are explicitly treated as untrusted data. Document-embedded text
that asks a model to ignore validation, reveal prompts, call tools, or choose an operational result
has no authority. The clients expose no tools, and adversarial development fixtures exercise this
boundary.

The LLM output does not write to the database and cannot set an assessment, feasibility state, coverage percentage, task, or deadline risk. The canonical corrigendum workflow proceeds only when the validated interpretation is confident, is `MODIFIED`, identifies `R17`, and contains the expected isolated count change. Otherwise it stops before superseding an assessment.

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
output, a deliberately narrow rule-based parser handles the synthetic canonical fixture. This is
not an LLM. The UI displays `Interpretation: Bedrock` or `Interpretation: Groq` only after a
completed workflow has persisted that actual provider mode; configuration alone is not enough.
Otherwise it displays `Interpretation: Demo fallback`.

The fallback understands the canonical CISSP manpower count amendment, explicit removal, equivalent-count wording, obvious deadline-only changes, and ambiguous clauses. Unmatched language returns `UNCERTAIN`; it does not guess.
Instruction-like source text addressed to a model or AI also returns `UNCERTAIN` and cannot apply a
change through the fallback.

## Human control

Humans control which tender text is supplied, whether the synthetic scenario or an authorized live
provider is used, evidence verification, task completion, final interpretation review, internal
approval, and any real tender submission. BidOps never submits to GeBIZ or makes a binding legal or
commercial decision.

## Evaluation boundary

The evaluation-only harness under `backend/evaluation/` keeps synthetic development fixtures, the
nine known GeBIZ-derived regression cases, and an intentionally empty genuinely blind partition
separate. It invokes interpretation with fallback disabled and scores requirement extraction,
corrigendum matching, and ambiguity handling. Final operational state is scored only when a frozen
downstream adapter or deterministic facts exist; other cases are `NOT_RUN`, not fabricated
failures or passes. Unsafe-green errors are reported when ground truth is `BLOCKED` or `UNCERTAIN`
but deterministic output becomes `FEASIBLE`. Expected answers and deterministic facts are never
sent to the model. The separate generic-rule benchmark scores deterministic requirement results
and final bid states. Missing source content is handled by a deterministic safety guard because
sending absent text to a model would invite invention.
