# Blind interpretation cases

This folder is intentionally empty in the frozen repository. A teammate who has not tuned the
production prompts can place genuinely unseen `.json` cases here and run:

```powershell
cd C:\GeBIZ
powershell -ExecutionPolicy Bypass -File .\scripts\run-blind-evaluation.ps1
```

Use one JSON object or an array of objects per file. Set `partition` to `BLIND`. Each record uses
the strict `EvaluationCase` schema in `backend/evaluation/schema.py`; unknown fields fail
validation. The model receives only `requirement_input` or `change_input`. `expected`,
`deterministic_facts`, and `companion_rules` are evaluator-side data and are never included in a
model request.

Keep the case author and prompt author separate where possible. Freeze the source text and ground
truth before running the model. Do not copy blind cases into development fixtures or tune prompts
against failed blind answers.

For a final operational-state score, provide either:

- `deterministic_scenario: "HERO_R17"` for the existing R17 production workflow; or
- `deterministic_facts` matching the generic `procurement_rule` expected from interpretation,
  plus optional `companion_rules` for other already-structured gates.

If neither adapter is present, interpretation is still scored but final operational state is
truthfully reported as `NOT_RUN`. The report includes requirement interpretation, corrigendum
matching, ambiguity handling, final operational-state accuracy, classified failures, and an
`unsafe_green_errors` list for ground-truth `BLOCKED`/`UNCERTAIN` cases that became `FEASIBLE`.

Do not put credentials, personal data, proprietary tender material, or answer keys inside source
text. Use only tender data the team is authorized to process.
