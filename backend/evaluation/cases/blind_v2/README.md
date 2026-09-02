# Blind evaluation v2 intake

This folder is intentionally empty. It is reserved for a teammate-authored evaluation set that has
not been inspected, run, or used for prompt/model selection by the implementation team.

1. Copy `CASE_TEMPLATE.json.example` to one or more `.json` files.
2. Freeze source passages and evaluator-only ground truth before any provider call.
3. Keep `partition` set to `BLIND`.
4. Run `scripts\run-blind-v2-evaluation.ps1` once the set is sealed.

The LLM receives only `requirement_input` or `change_input`. The runner never places `expected`,
`deterministic_facts`, or `companion_rules` in the prompt. Do not move failures into development
fixtures or tune the production prompt against this set.

No blind-v2 performance claim exists until a real teammate-owned set is added and run.
