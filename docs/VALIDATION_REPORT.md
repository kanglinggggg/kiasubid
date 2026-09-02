# Final pre-freeze validation report

Date: 2 September 2026 (Asia/Singapore)

## Environment

- OS: Microsoft Windows 11 Home Single Language 10.0.26200 (build 26200)
- PowerShell: 7.6.4
- Python: 3.14.2 in `.venv`
- Node.js: 22.19.0
- npm: 10.9.3
- Frontend: `http://127.0.0.1:5173`
- Backend: `http://127.0.0.1:8000`
- API documentation: `http://127.0.0.1:8000/docs`
- Selected provider: Bedrock
- Selected model: `amazon.nova-lite-v1:0`
- Provider status: live Bedrock invocation, R17 flow, known regression, and frozen blind evaluation
  verified in `us-east-1` with valid temporary credentials
- Structured-output mode: prompted JSON schema plus strict local Pydantic/provenance validation

Temporary AWS access-key, secret-key, and session-token fields are populated only in the ignored
local `.env`. Their presence was checked without printing their values. The configured temporary
credentials expire approximately every 12 hours. Groq remains unconfigured.

## Repository and secret safety

- Local Git was initialized on `main`. A validated baseline commit and the local
  `demo-ready-2026-08-28` tag identify the frozen build; nothing was pushed externally.
- `.gitignore` explicitly excludes `.env`, `.venv/`, `node_modules/`,
  `frontend/node_modules/`, `dist/`, `frontend/dist/`, `__pycache__/`, `*.pyc`, generated
  databases/reports, runtime logs/PIDs, and temporary PDF renders.
- A filename-only source scan found expected credential/configuration terms only in configuration,
  provider, tests, documentation, and `package-lock.json`.
- High-confidence scans found zero `AKIA...` access keys, zero `gsk_...` keys, and zero populated
  AWS/Groq secret assignments in source files.
- No credential was invented, moved, or printed.

## Clean-start validation

The requested sequence passed:

```powershell
cd C:\GeBIZ
powershell -ExecutionPolicy Bypass -File .\scripts\stop.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1 -SkipInstall
```

After stopping, neither port had a listener. After starting, there was exactly one Vite listener on
5173 and one Uvicorn listener on 8000. The frontend, `/api/health`, and `/docs` returned HTTP 200.
No duplicate or orphan server process remained.

## Automated validation

Fresh results from the final tree:

| Check | Result |
|---|---:|
| Ruff | PASS |
| Backend pytest | 64 passed |
| Frontend Vitest | 4 passed in 2 files |
| TypeScript (`tsc -b`) | PASS |
| Vite production build | PASS; 1,674 modules transformed |
| npm audit | 0 known vulnerabilities |
| Provider boundary tests | 20 passed as part of the backend suite |

Pytest reports 42 third-party deprecation warnings from LangGraph/Starlette under Python 3.14; no
project test failed. The production frontend bundle completed successfully.

## GeBIZ-derived deterministic regression benchmark

Report: `data/evaluation/deterministic_report.json`

- Total cases: 9
- Deterministic requirement-result accuracy: 9/9 (100%)
- Overall bid-status accuracy: 9/9 (100%)
- Unsupported cases: 0
- Failures: 0
- Interpretation: `NOT_RUN`

This is deliberately labelled a deterministic regression benchmark. The nine structured cases
have informed development and are not an unseen-AI benchmark or an AI accuracy claim.

Case 9 passed its focused regression: the old deposit deadline produces `UNMET / BLOCKED`; the
extended deadline still produces an `UNMET` current gate but changes the overall state to
`RECOVERABLE`. The generic rule benchmark is stateless and therefore records the prior and current
results rather than persisting an Assessment row. Persisted lifecycle superseding is separately
verified by the production corrigendum workflow, where R17 v1 remains stored as `SUPERSEDED`.

## Live-model interpretation evaluation

Current selected-model report: `data/evaluation/model_bakeoff/amazon.nova-lite-v1_0.json`

- Provider: Bedrock
- Model: `amazon.nova-lite-v1:0`
- Provider configured: true
- Total known regression records: 9
- Current requirement interpretation accuracy: 6/7 (85.71%)
- Current corrigendum matching accuracy: 2/2 (100%)
- Current ambiguity handling accuracy: 9/9 (100%)
- Current final operational-state accuracy: 8/9 (88.89%)
- Unsafe-green errors: 0
- Provider blockers: 0
- Genuinely blind cases: 8 frozen teammate-supplied records

Known-regression failures were retained exactly. Case 7 omitted the qualification obligation and
returned only source-freshness uncertainty, producing one extraction error while still reaching the
correct `UNCERTAIN` final state. Case 3 extracted the expected four-week processing rule but also a
separate mandatory clearance-form document rule for which the evaluator fixture has no authoritative
document fact; the binding therefore failed closed to `UNCERTAIN` instead of coercing the expected
`RECOVERABLE` state. No unsafe-green result occurred.

The selected run recorded one attempt count per case, exact field differences, provenance checks,
rule/fact bindings, deterministic reasons, 36,247 ms aggregate provider latency, 23,007 input
tokens, 3,591 output tokens, and 26,598 total tokens. None of those evaluator diagnostics or expected
answers entered the model prompt.

Current blind report: `data/evaluation/blind_report.json`

- Source set: `GeBIZ_Unseen_Test_Cases_Blind_and_Key.docx`, U1-U8
- Provider/model: Bedrock / `amazon.nova-lite-v1:0`
- Total frozen blind records: 8
- Requirement interpretation: 2/8 (25%)
- Corrigendum matching: `NOT_APPLICABLE` (8 requirement-only cases)
- Ambiguity handling: 7/8 (87.5%)
- Final operational state: 4/8 (50%)
- Unsafe-green errors: 0
- Provider blockers: 0

The blind source passages and evaluator-only answers were frozen before the first call. Expected
answers and deterministic bidder facts were not included in model prompts. This blind-v1 set is now
historical observed evidence: it was not used to choose this round's prompt, deterministic
normalizers, or model, and it was not rerun after those known-regression-driven changes. A separate
`cases/blind_v2/` intake is intentionally empty and ready for the next teammate-sealed evaluation;
no blind-v2 performance is claimed.

Blind failures were retained exactly: extraction errors in U1, U2, U4, U6, U7, and U8;
deterministic final-state mismatches in U1, U2, U4, and U7; and an ambiguity-handling error in U5.
U3 passed all applicable metrics. U5 produced the correct FEASIBLE state, U6 and U8 safely produced
UNCERTAIN, and no ground-truth BLOCKED/UNCERTAIN case was incorrectly reported FEASIBLE.

The preserved 28 August baseline remains part of the evidence: requirement interpretation was
0/7, corrigendum matching 2/2, and ambiguity handling 6/9. Failures were not hidden. They exposed
generic defects: rule-kind aliases were not canonicalized, a `PROCESSING_WINDOW` incorrectly
required a deadline in the same clause, multi-obligation passages lacked deterministic field
projection, and final operational-state adapters were absent. Those defects are now covered by
local tests. The new measured results above replace that baseline as the current live evidence.

Separately, the live canonical R17 path passed: Bedrock interpreted the natural-language
corrigendum as `MODIFIED`, matched R17, returned `minimum_count 3 -> 4`, and the deterministic
workflow produced `FEASIBLE -> RECOVERABLE` and `8/8 -> 7/8`.

### Final interpretation hardening

- Source text is mechanically segmented into source-order clause candidates without rewriting or
  adding facts; the original page/section text remains the authoritative model input.
- Qualification identifiers use conservative canonical procurement-code identity, so descriptive
  prefixes such as a registry/workhead label do not break exact evidence binding.
- Required-document binding distinguishes an attachment artifact from the Price/Technical envelope
  used as its submission channel.
- A validated compulsory deadline amendment receives a deterministic `PROCESSING_WINDOW` adapter
  after model validation. The envelope/report labels it `DEADLINE_TO_PROCESSING_WINDOW`; the LLM
  still cannot set feasibility or recoverability.
- Missing typed rules, missing authoritative facts, and unused fact sets remain fail-closed. The
  remaining Case 3 mismatch demonstrates that safeguard rather than hiding it.
- Blind-v2 intake and an empty-set guard are ready; no unseen data or answer key was fabricated.

## AWS hackathon access preparation

- The single Hackathon 2026 lease is active. STS identity succeeded with the temporary sandbox
  role, and the region was verified as `us-east-1`.
- AWS CLI 2.36.30 is installed.
- The application and `.env.example` use the official `us-east-1` region.
- Ignored `.env` fields support the lease's temporary access key, secret key, and session token;
  incomplete credential sets fail closed.
- Temporary credential wiring is covered by tests without exposing secret values.
- Model discovery found Nova Micro and Nova Lite as active on-demand foundation models, plus active
  system inference profiles for Nova 2 Lite and Claude Haiku variants. No provisioned throughput or
  infrastructure was created.
- A fixed-prompt known-regression bake-off compared Nova Lite v1, Nova Micro v1, and the US Nova 2
  Lite system inference profile. Nova Lite won with 6/7 requirement interpretations, 2/2
  corrigendum matches, 9/9 ambiguity decisions, and 8/9 final states. Nova Micro scored 4/7, 2/2,
  8/9, and 6/9; Nova 2 Lite scored 3/7, 2/2, 7/9, and 6/9. All three had zero unsafe-green errors.
- Native JSON-schema output was attempted with
  `us.anthropic.claude-haiku-4-5-20251001-v1:0`, but AWS rejected Converse while the new account's
  sandbox role lacked the required `aws-marketplace:ViewSubscriptions` and
  `aws-marketplace:Subscribe` actions needed to enable this third-party model. Nova Lite was
  reachable, but v1 does not support Bedrock's native `outputConfig` field.
- The selected live model is `amazon.nova-lite-v1:0` with its schema included in the prompt, followed
  by strict Pydantic and exact-source validation. This is a real Bedrock invocation but is not
  described as Bedrock-native constrained decoding.
- The minimal live requirement smoke test passed as `DOCUMENT / MANDATORY / INTERPRETED` with
  validated source provenance.
- The browser was observed changing from **Interpretation: Demo fallback** before the invocation
  to **Interpretation: Bedrock** only after the live R17 interpretation was persisted, then back to
  the canonical fallback label after an actual UI reset.

## Visual QA

The live localhost application was inspected in the in-app browser at the requested viewport
settings:

- 1440 × 900 (primary desktop presentation target)
- 1280 × 720
- 390 × 844

No horizontal document overflow, clipped controls, overlapping text, unreadable cards, broken
tables, hidden primary actions, drawer overflow, or mobile-breaking layout was observed. The
requirement table scrolls horizontally on mobile as intended. The 10-second judge view clearly
shows the tender identity, Operational Feasibility, Critical Gates, time remaining, and the driver
action in the Deadline Risk card.

Screenshots under `docs/qa/`:

1. `01_initial_feasible.png`
2. `02_r17_detail_initial.png`
3. `03_corrigendum_detected.png`
4. `04_recoverable_state.png`
5. `05_recovery_candidate.png`
6. `06_blocked_scenario.png`
7. `07_uncertain_scenario.png`
8. `08_reset_state.png`
9. `09_desktop_1280x720.png`
10. `10_mobile_390x844.png`

Browser console warnings/errors were empty after the main, BLOCKED, UNCERTAIN, reset, and repeated
corrigendum flows. No unexpected 4xx/5xx responses or polling loops were observed. Expected error
traffic was limited to the deliberate duplicate (409), invalid request (422), and backend-outage
exercise (Vite proxy 500 while port 8000 was intentionally stopped).

## Demo QA

Initial canonical state was verified through both UI and API:

```text
Operational Feasibility  FEASIBLE
Critical Gates           8 / 8
Submission Coverage      91%
Deadline Risk            LOW
Interpretation            Demo fallback
```

R17 v1 states “not fewer than three personnel holding valid CISSP certification,” shows three
complete personnel evidence sets (certificate plus current CV for Engineers A, B, and C), and
exposes document, page 17, section 4.3, and an exact source snippet.

The actual **Apply Corrigendum #2** button was clicked. The rendered and persisted result was:

```text
R17 v1                    stored; assessment SUPERSEDED
R17 v2                    created; minimum 3 → 4; assessment PARTIAL
Operational Feasibility  FEASIBLE → RECOVERABLE
Critical Gates           8/8 → 7/8
Submission Coverage      91% → 84%
Deadline Risk            LOW → MEDIUM
Interpretation            Demo fallback
```

Engineer D remained a recovery candidate only: CISSP `VERIFIED`, CV `STALE`, availability
`UNKNOWN`. R17 was not marked satisfied. The four recovery tasks and dependencies were visible:
request updated CV, confirm availability, update the manpower schedule, and re-run R17 verification.

The main demo was repeated three times from reset with the same result. Measured UI runs completed
in about 2.0 seconds (the UI intentionally keeps the workflow overlay visible for 1.9 seconds).
Every completed run contained exactly two R17 versions, four unique recovery tasks, and nineteen
unique activity events. A direct duplicate application returned 409 and changed none of those
counts.

The selectable BLOCKED fixture showed `BLOCKED`, 7/8 gates, 85% coverage, zero recovery tasks, and
an explicit no-viable-recovery explanation. The selectable UNCERTAIN fixture showed `UNCERTAIN`,
8/9 gates, 87% coverage, and a human-clarification rationale rather than a system-error message.
Reset restored exactly `FEASIBLE / 8 of 8 / 91% / LOW`, four baseline events, and no change or
recovery artifacts.

## Calculation trace QA

- Operational Feasibility returned the precedence `BLOCKED → UNCERTAIN → RECOVERABLE → FEASIBLE`,
  unresolved gate records, the persisted value, and `matches_persisted_value=true`.
- Critical Gates returned all current mandatory requirement/assessment pairs. Counting `verified`
  entries reproduced 8/8 initially and 7/8 after the corrigendum.
- Submission Coverage returned exact 50% requirement, 30% evidence, and 20% task components.
  Initial raw coverage was 91.3871% → 91%; post-change raw coverage was 84.3963% → 84%.
- Deadline Risk returned the driver and slack. The initial driver was “Director declaration final
  review” at 75h (`LOW`); the post-change driver was “Request updated CV from Engineer D” at 46h
  (`MEDIUM`).
- All four trace blocks matched their persisted backend values. The UI consumes these backend
  values and does not calculate an alternative score or operational status.

## Safety and provenance QA

- The exact adversarial document text requesting instruction override, fabricated satisfaction,
  forced FEASIBLE status, tool calls, and submission returned `DEMO_FALLBACK / UNCERTAIN`, with no
  minimum count and no state mutation.
- Empty document text returned an explained `UNCERTAIN` result; an invalid page returned 422.
- Malformed model output retry and graceful failure are covered by tests.
- Fabricated source snippets are rejected and retried; normalized source snippets must be exact
  substrings of supplied text.
- Provenance was checked for R17, the compulsory briefing R05, ISO qualification R03, and the
  UNCERTAIN R19 requirement. Each exposes source document, page, section, and a validated snippet.
- A punctuation defect in the R19 fixture snippet was fixed and protected with a regression test.
- LLM output cannot set feasibility, assessment status, evidence matches, tasks, coverage, or
  deadline risk. Those remain deterministic.

## Failure recovery and performance

- Backend stopped while frontend remained open: frontend stayed available, showed “Bid state
  unavailable” with the actual 500, and recovered through **Try again** after restart.
- Database/backend restart: a persisted `RECOVERABLE` state survived restart; explicit reset then
  returned the canonical initial state.
- Duplicate corrigendum: 409, no duplicate versions/tasks/events.
- Empty text: safe `UNCERTAIN` fallback.
- Invalid structured provider output: retry then graceful failure/fallback in tests.
- Malformed PDF: not applicable; this frozen MVP accepts extracted page/section text and has no PDF
  upload/OCR endpoint.

Approximate local UI timings:

| Operation | Time |
|---|---:|
| Initial reload to rendered state | 306 ms |
| Reset | 290–307 ms |
| Scenario switch | 178 ms |
| Apply Corrigendum #2 | 2,037–2,046 ms |

No clearly bad local latency was observed.

## Defects fixed during this pass

1. Test isolation allowed a mocked Bedrock interpretation to remain in the shared demo database,
   causing a credential-free post-test launch to claim `Interpretation: Bedrock` until reset.
   Backend test fixtures now reset after every mutating test; the final suite leaves
   `DEMO_FALLBACK / FEASIBLE` state.
2. The UNCERTAIN R19 fixture stored a snippet with punctuation that did not occur verbatim in its
   source text. The snippet is now an exact substring and has a regression assertion.
3. Ignore rules now explicitly cover generic root `node_modules/`, `dist/`, and `*.pyc` paths.
4. Provider configuration now accepts the requested `GROQ_MODEL` variable as an alias for
   `GROQ_MODEL_ID`, with a unit test and `.env.example` documentation.
5. Bedrock's non-native structured-output setting previously omitted the supplied JSON schema from
   the model prompt. It now includes the cleaned schema and remains protected by Pydantic,
   provenance validation, and repair retry; a provider-boundary test covers this path.

## Blind evaluation support

A teammate can add deterministic regression JSON under `backend/evaluation/rule_cases/` without a
production-code change. The nine known interpretation cases now live under
`backend/evaluation/cases/regression/`; synthetic prompt-development fixtures remain under
`cases/development/`; the eight frozen teammate-supplied records live only under the
`cases/blind/` folder. A non-loaded `CASE_TEMPLATE.json.example` documents the strict format, and
`scripts/run-blind-evaluation.ps1` discovers `.json` cases automatically. Expected
answers and deterministic facts remain evaluator-side and are never included in the model request.
Reports separate requirement interpretation, corrigendum matching, ambiguity handling, and final
operational state, and list unsafe-green errors. The successful live run retained all failures and
reported zero unsafe-green errors; no score was manufactured.

## Remaining external blockers and limitations

- AWS native JSON-schema output with Claude Haiku 4.5 remains blocked because the sandbox role
  lacks the Marketplace subscription actions required to enable that model. Nova Lite v1 works
  through prompted JSON plus local validation.
- No authorized Groq API key/model is configured.
- Nova Lite exact requirement interpretation remains imperfect at 6/7 on known regression. The
  historical blind-v1 first run remains 2/8 and was not used for this round's prompt/model
  selection or rerun afterward. Human review and a genuinely sealed blind-v2 evaluation remain
  mandatory.
- PDF upload/OCR and multi-user production hardening are intentionally outside the frozen MVP.

## Final readiness classification

| Area | Classification |
|---|---|
| LOCAL ENGINEERING MVP | READY |
| DETERMINISTIC DEMO | READY |
| LIVE LLM VALIDATION | READY — measured with known limitations |
| HACKATHON DEMO WITHOUT LIVE PROVIDER | READY |
| FULL INTENDED HACKATHON STACK | READY — human review required |

The local deterministic demo remains ready. The live R17 story, provider boundary, known regression,
and frozen blind evaluation were verified with Nova Lite. Exact requirement interpretation is not
release-quality and remains human-reviewed. Haiku 4.5 native structured output remains unavailable
under the sandbox Marketplace/SCP controls, but it is not required for the validated Nova Lite path.
