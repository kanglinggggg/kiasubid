# Final pre-freeze validation report

Date: 28 August 2026 (Asia/Singapore)

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
- Provider status: not configured; Demo fallback only

`AWS_PROFILE`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`,
`BEDROCK_MODEL_ID`, `GROQ_API_KEY`, `GROQ_MODEL_ID`, and `GROQ_MODEL` are blank in the local
`.env`. No AWS access key, AWS secret key, or Groq key was found at
process, user, or machine environment scope. No live provider call was attempted.

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
| Backend pytest | 48 passed |
| Frontend Vitest | 4 passed in 2 files |
| TypeScript (`tsc -b`) | PASS |
| Vite production build | PASS; 1,674 modules transformed |
| npm audit | 0 known vulnerabilities |
| Provider boundary tests | 19 passed as part of the backend suite |

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

Report: `data/evaluation/live_report.json`

**NOT RUN — external credential/model access unavailable.**

- Provider: Bedrock
- Provider configured: false
- Total known regression records discovered: 9
- Requirement interpretation accuracy: not measured
- Corrigendum matching accuracy: not measured
- Ambiguity handling accuracy: not measured
- Final operational-state accuracy: not measured
- Fabricated scores: none

Bedrock and Groq request construction, mode attribution, JSON-schema/Pydantic validation, repair
retry, graceful fallback, and incomplete-configuration handling are covered by mocked tests. Groq
accepts either `GROQ_MODEL_ID` or `GROQ_MODEL`. A live provider name is displayed only when that
provider produced the persisted interpretation event.

## AWS hackathon access preparation

- The official access guide was reviewed and the single Hackathon 2026 lease request progressed
  through the human-controlled authentication, Terms, and submission steps. Approval remains
  pending; no AWS API call was attempted without active lease credentials.
- AWS CLI 2.36.30 is installed.
- The application and `.env.example` use the official `us-east-1` region.
- Ignored `.env` fields support the lease's temporary access key, secret key, and session token;
  incomplete credential sets fail closed.
- Temporary credential wiring is covered by tests without exposing secret values.
- `scripts/validate-aws-post-approval.ps1` is ready to verify STS and `us-east-1`, discover only
  cheap on-demand Nova Micro/Lite or Claude Haiku candidates, reject provisioned identifiers, run
  a minimal structured inference, prove the Bedrock-to-R17 transition, and rerun live evaluation.
- STS, model discovery, inference, and live evaluation remain pending until the lease is approved
  and temporary credentials plus an explicit discovered model ID are provided locally.

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

## Blind evaluation support

A teammate can add deterministic regression JSON under `backend/evaluation/rule_cases/` without a
production-code change. The nine known interpretation cases now live under
`backend/evaluation/cases/regression/`; synthetic prompt-development fixtures remain under
`cases/development/`; genuinely unseen teammate cases belong only under the intentionally empty
`cases/blind/` folder. `scripts/run-blind-evaluation.ps1` discovers them automatically. Expected
answers and deterministic facts remain evaluator-side and are never included in the model request.
Reports separate requirement interpretation, corrigendum matching, ambiguity handling, and final
operational state, and list unsafe-green errors. No unseen performance was manufactured.

## Remaining external blockers and limitations

- The Hackathon 2026 AWS lease is awaiting external approval; temporary credentials and an
  explicit accessible Bedrock model ID are therefore unavailable.
- No authorized Groq API key/model is configured.
- Consequently, live interpretation quality and the natural-language-to-R17 live-provider proof
  remain externally blocked.
- PDF upload/OCR and multi-user production hardening are intentionally outside the frozen MVP.

## Final readiness classification

| Area | Classification |
|---|---|
| LOCAL ENGINEERING MVP | READY |
| DETERMINISTIC DEMO | READY |
| LIVE LLM VALIDATION | BLOCKED |
| HACKATHON DEMO WITHOUT LIVE PROVIDER | READY |
| FULL INTENDED HACKATHON STACK | BLOCKED |

The only blocker to live-model validation is external credential/model access. The local,
deterministic, visually verified fallback build is ready to freeze.
