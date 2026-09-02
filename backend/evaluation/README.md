# Interpretation evaluation harness

This harness is outside the product runtime. It evaluates the selected live-model interpretation
provider independently from deterministic operational logic.

Datasets are deliberately separated:

- `cases/development/` contains synthetic fixtures used while building the interpreter, including the hero handoff and semantic-isolation checks.
- `cases/regression/` contains the nine GeBIZ-derived cases that informed development. They are regression data, not unseen-AI evidence.
- `cases/blind/` contains eight teammate-authored cases frozen before their first model run, plus
  a non-loaded `.json.example` template. This is the observed blind-v1 set and is retained as
  historical first-run evidence; it is not a tuning or model-selection partition.
- `cases/blind_v2/` is intentionally empty and reserved for the next sealed teammate-owned set.
  Production prompts must not be edited to fit answers placed there, including after a failed run.

Every JSON record declares expected requirement type, gate type, structured fields, ambiguity state, affected requirement, change type, and final operational state. The runner reports four separate metrics and classifies every observed failure as one of the required categories.

Run the known live-model regression:

```powershell
uv run python -m evaluation --partition regression
```

Run development fixtures separately:

```powershell
uv run python -m evaluation --partition development --output data/evaluation/development-report.json
```

After placing frozen unseen JSON cases under `cases/blind/`, run the blind evaluation from the
repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-blind-evaluation.ps1
```

For the next genuinely unseen set, place sealed JSON under `cases/blind_v2/` and run
`scripts\run-blind-v2-evaluation.ps1`. The command fails closed while no real cases exist.

The model receives only `requirement_input` or `change_input`. Expected answers and deterministic
facts remain evaluator-side. Generic interpreted `procurement_rule` objects are bound to the
case's authoritative bidder facts by rule kind and then passed through the production deterministic
evaluators. One facts object covers a single rule; an array supports multi-obligation passages. A
missing rule/fact binding fails closed to `UNCERTAIN`; it can never become an unsafe green result.
The known R17 flow uses its existing production-workflow adapter.

Live evaluation never enables fallback. If the selected provider's model or credentials are absent,
the report records a blocker and leaves accuracy values unmeasured instead of inventing scores.
External cases without deterministic facts or a frozen downstream scenario adapter report final
operational state as `NOT_RUN`; those same states may be evaluated through the separate
deterministic rule benchmark.
Every report also lists unsafe-green errors: a ground-truth `BLOCKED` or `UNCERTAIN` case whose
deterministic final result was incorrectly `FEASIBLE`.

Each case also records exact expected/actual field differences, selected requirement, validated
source provenance, rule/fact binding status, deterministic reason, provider attempts, latency, and
token usage. These diagnostics are evaluator outputs only and are never added to the model prompt.

Run the fixed-prompt cheap-model comparison only on the known regression partition:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-bedrock-model-bakeoff.ps1
```

Ranking rejects unsafe-green outcomes first, then compares final-state, interpretation, ambiguity,
token, and latency results. It never loads either blind partition.

## Deterministic procurement-rule benchmark

The v3 external benchmark's structured rules and synthetic bidder facts live separately in
`rule_cases/`. They exercise the production generic-rule evaluators without invoking an LLM or
using fallback interpretation:

```powershell
python -m evaluation.rule_runner
```

The generated report records live interpretation as `NOT_RUN`, then reports deterministic
requirement-result accuracy and overall bid-status accuracy separately. A case outside the bounded
rule vocabulary must use an explicit `unsupported_reason`; it is excluded from the accuracy
denominator and listed rather than coerced into a nearby rule type.
