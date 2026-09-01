# Deterministic procurement rule vocabulary

The procurement rule engine accepts a typed rule, typed observed facts, and an explicit
`evaluation_as_of` timestamp. It never derives facts from prose and never calls an LLM. Pydantic
rejects extra fields and rejects a rule paired with facts for a different rule type.

## Rule result contract

Every evaluator returns:

- `status`: `SATISFIED`, `PARTIAL`, `UNMET`, or `UNCERTAIN`;
- `recoverable`: `true`, `false`, or `null` when recoverability cannot be proven;
- a deterministic reason;
- satisfied and unresolved item names;
- projected completion time when a processing window is evaluated.

The aggregate operational-state precedence is:

1. `BLOCKED` when a known `PARTIAL` or `UNMET` mandatory gap has `recoverable=false`;
2. `UNCERTAIN` when no blocker exists but a result or recoverability fact is uncertain;
3. `RECOVERABLE` when every known gap has `recoverable=true`;
4. `FEASIBLE` when every rule is `SATISFIED`.

## Rule types

### `EVENT_ATTENDANCE`

Rule fields identify the event, its date when known, and whether attendance is compulsory. Facts
record attendance plus whether the original or a make-up attendance opportunity remains open.
Missing criticality or attendance evidence returns `UNCERTAIN`; missed compulsory attendance is
`UNMET`, with recoverability determined only by the two opportunity facts.

### `QUALIFICATION`

The rule declares one or more qualification options, `ANY`/`ALL` matching, and criticality. Each
fact states whether evidence for a named option was verified and whether a registry or other
deterministic adapter established that its grade meets the minimum. The evaluator does not encode
scheme-specific grade ordering. Unknown criticality or an unverified comparison returns
`UNCERTAIN`; otherwise a failed mandatory match is `UNMET` and uses only the explicit
`can_obtain_before_deadline` fact for recoverability.

### `REQUIRED_DOCUMENT`

The rule lists document or envelope names and `ANY`/`ALL` matching. Facts use `SUBMITTED`, `READY`,
`MISSING`, or `UNKNOWN`, plus the submission-window state. `READY` is not treated as submitted. A
partly submitted `ALL` set is `PARTIAL`; none submitted is `UNMET`; unknown document state can be
`UNCERTAIN`. Recovery requires the submission window to be open and every unresolved document to
be ready or explicitly completable before closing.

### `PROCESSING_WINDOW`

The rule contains the mandatory action and minimum processing duration. The governing deadline is
optional because a clause may state a four-week processing period without repeating the tender
closing date. An authoritative deadline can instead arrive through deterministic tender metadata
in the facts. Facts also contain completion state, earliest possible start, estimated duration, and
whether completion is possible. For an incomplete action, projected completion is:

```text
max(evaluation_as_of, earliest_start_at)
+ max(minimum_processing_hours, estimated_duration_hours)
```

The result is `UNMET`; it is recoverable only when projected completion is on or before the
authoritative deadline from either source. If neither source contains a deadline, the result is
`UNCERTAIN` rather than an invented date. This rule is neutral to the nature of the action (for
example clearance, approval, or payment) and therefore needs no tender-specific branch.

### `PARTICIPATION_RESTRICTION`

The rule records a named participation restriction and its criticality. Facts state eligibility
and whether eligibility can change before closing. Unknown eligibility is `UNCERTAIN`; known
ineligibility is `UNMET` with recoverability taken from the explicit fact.

### `SOURCE_FRESHNESS`

The rule names the authoritative corpus and whether its latest version is required. Facts state
whether the latest version was ingested and whether a known change notice's contents are available.
A known but unavailable corrigendum, or any corpus that cannot be proven current, returns
`UNCERTAIN`; stale content is never silently evaluated as authoritative.

## LLM boundary

The Bedrock interpreter may emit one of these typed rule objects from source language. The rule
engine receives only validated structured data. Supplier facts, requirement results, recovery,
and operational status remain deterministic; the LLM has no field through which it can set those
outcomes.
