# 3–5 minute demo runbook

## Preflight (before judges arrive)

From PowerShell:

```powershell
cd C:\GeBIZ
powershell -ExecutionPolicy Bypass -File .\scripts\stop.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1 -SkipInstall
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/demo/reset | Out-Null
Start-Process http://127.0.0.1:5173
```

Confirm the initial screen shows `FEASIBLE`, `8 / 8`, `91%`, `LOW`, and **Interpretation: Demo
fallback** unless a real Bedrock interpretation has already been persisted. Keep browser zoom at
100% and the scenario on **Main corrigendum demo**.

## Primary sequence (approximately 4:50)

| Time | Click / action | Expected state | Speaking point |
|---|---|---|---|
| 0:00–0:25 | No click. Point to the title, fixed scenario clock, countdown, and four metric cards. | `FEASIBLE`; Critical Gates `8 / 8`; Submission Coverage `91%`; Deadline Risk `LOW`. The clock makes clear that this is a deterministic replay, not today's live deadline. No portfolio claim is shown yet. | “BidOps gives the supplier one operational truth: can we still submit safely, what proves it, and what must happen next?” |
| 0:25–0:55 | Click requirement **R17** if it is not already selected. Expand its source/provenance area if collapsed. | “Minimum 3 CISSP-certified engineers”; three complete A/B/C evidence sets; source document, page 17, section 4.3, exact snippet. | “R17 is a typed, source-linked gate. The model interprets the clause; it does not decide whether the bid passes.” |
| 0:55–1:10 | Briefly point to the Submission Coverage breakdown. | Visible 50% Requirements + 30% Evidence + 20% Tasks arithmetic. | “Coverage measures preparation completeness; it never overrides a mandatory gate.” |
| 1:10–1:20 | Click **Apply Corrigendum #2** once. | The workflow moves through interpretation, versioning, evidence checks, and recovery planning. | “A natural-language amendment raises the minimum from three to four.” |
| 1:20–2:00 | Wait for completion; point to the changed cards and Latest Change panel. | R17 `3 → 4`; v1 `SUPERSEDED`; v2 `PARTIAL`; `FEASIBLE → RECOVERABLE`; `7 / 8`; `84%`; `MEDIUM`. | “The old pass remains as history but is no longer current. Deterministic rules find a recoverable bid-level gap.” |
| 2:00–2:25 | In R17 detail, show Engineer D and the recovery tasks. | CISSP `VERIFIED`; CV `STALE`; Availability `UNKNOWN`; R17 remains `PARTIAL`. | “A certificate alone is not enough. Until the missing evidence and availability are resolved, this bid stays RECOVERABLE—not green.” |
| 2:25–2:40 | In **Latest Change**, point to **Cross-bid impact · Synthetic demo**, then click **Compare 3 routes**. | The **Portfolio impact** drawer opens with **Simulation only** and **Synthetic demo** labels. | “The same validated change now becomes a dated capability-demand delta across two supplied opportunities.” |
| 2:40–3:10 | Point to the state boundary and capacity cards. | Current bid `RECOVERABLE`; portfolio before change `RECOVERABLE`; portfolio after change `BLOCKED`; synthetic overlap 1 October–1 December 2026; three proven, four potential, five concurrent required, one shortfall. | “These are separate scopes. This tender may still recover, but continuing both pursuits needs five concurrent slots and only four have been identified.” |
| 3:10–3:25 | Point to **Affected pursuits**. | Current tender requires four; fictional companion commitment requires one. | “The companion opportunity, service windows, capacity counts, and no-double-booking rule are synthetic demo assumptions—not GeBIZ or HR data.” |
| 3:25–4:05 | Click each route: **Protect this tender**, **Protect existing commitment**, and **Verify external capacity**. | Each card shows the deterministic consequence for both pursuits. Partner remains `UNCERTAIN` and lists facts still required. | “These are counterfactual consequences, not recommendations. There is no price, margin, win probability, automatic staffing, withdrawal, or partner action here.” |
| 4:05–4:25 | Scroll to **Capability next steps**, then expand **Assumptions and calculation**. | Known evidence/capacity gaps and the exact peak-demand rule are visible. | “For an early-stage supplier, this turns recurring known gaps into a capability discussion. It does not promise qualification, awards, or revenue.” |
| 4:25–4:40 | Close the drawer and open **Activity**. | The audit trail records bid-level events from interpretation through status recomputation. | “The language model reads the change; deterministic code owns the calculations; the team owns the decision and every external action.” |
| 4:40–4:50 | Close Activity and click the header reset icon. | Exact baseline state: `FEASIBLE / 8 / 8 / 91% / LOW`; no old change, tasks, or portfolio panel. | “The whole demonstration resets to the same clean baseline in one click.” |

Optional closing line: “The LLM interprets language; deterministic rules control the bid state;
people control the decision and submission.”

If more time is available, use the **BLOCKED · no fourth engineer** and **UNCERTAIN · ambiguous
clause** fixtures only as separate safety branches. Do not mix their states with the synthetic
portfolio calculation.

## Live Bedrock variation

Use it only after the post-approval script passes. Before presenting, run the main flow once
and confirm the persisted UI badge says **Interpretation: Bedrock**. Never claim Bedrock based on
configuration alone. If the badge says Demo fallback, present the reliable fallback flow and state
that live validation is unavailable.

## Recovery procedures

### Backend failure

Symptom: the frontend shows **Bid state unavailable**, a request error, or the API health endpoint
does not return 200.

```powershell
cd C:\GeBIZ
powershell -ExecutionPolicy Bypass -File .\scripts\stop.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1 -SkipInstall
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/demo/reset | Out-Null
```

Refresh the browser. If startup fails, inspect `data\logs\backend.err.log`. Do not improvise state
through direct database edits during the pitch.

### Frontend failure

If the API is healthy but port 5173 is unavailable:

```powershell
cd C:\GeBIZ
powershell -ExecutionPolicy Bypass -File .\scripts\stop.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1 -SkipInstall
```

Reopen `http://127.0.0.1:5173`. Inspect `data\logs\frontend.err.log` only if it still fails.

### Bedrock unavailable

Do not claim a live run. Stop the app, leave temporary credentials untouched, set
`BEDROCK_MODEL_ID=` in the ignored `.env`, restart, reset, and verify **Interpretation: Demo
fallback**. Present the built-in demo flow and disclose that the provider is unavailable.

### Bad live-model interpretation

Do not force or hand-edit the interpreted result. Preserve the failed report for diagnosis. Switch
to the explicit demo fallback by blanking `BEDROCK_MODEL_ID` in `.env`, restart, reset, and state
the mode honestly. A malformed, ambiguous, or wrongly matched interpretation must never be used to
manufacture a green operational result.

### Accidental duplicate corrigendum

The API returns `409 Conflict` and does not create duplicate requirement versions, tasks, or
events. Click the header reset icon and apply the corrigendum once. If needed:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/demo/reset | Out-Null
```

### Immediate reset to FEASIBLE

Fastest UI path: click the circular reset icon in the top-right header. Fastest terminal path:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/demo/reset | Out-Null
```

Refresh if necessary and verify exactly `FEASIBLE / 8 / 8 / 91% / LOW` before continuing.

### Portfolio panel missing or inconsistent

The panel appears only after the main R17 corrigendum has been applied. Reset, select **Main
corrigendum demo**, and apply the change once. Confirm the current bid still reads `RECOVERABLE`
before opening **Compare 3 routes**. If the displayed capacity is not exactly three proven, four
potential, five required, and one shortfall, do not improvise the claim; restart, reset, and rerun
the tested fixture.
