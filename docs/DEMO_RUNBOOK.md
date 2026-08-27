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

## Primary sequence (approximately 4:20)

| Time | Click / action | Expected state | Speaking point |
|---|---|---|---|
| 0:00–0:30 | No click. Point to the title, countdown, and four metric cards. | `FEASIBLE`; Critical Gates `8 / 8`; Submission Coverage `91%`; Deadline Risk `LOW`. | “BidOps gives the supplier one operational truth: can we still submit safely, what proves it, and what must happen next?” |
| 0:30–1:05 | Click requirement **R17** if it is not already selected. Expand its source/provenance area if collapsed. | “Minimum 3 CISSP-certified engineers”; three complete A/B/C evidence sets; source document, page 17, section 4.3, exact snippet. | “This is not a chat summary. R17 is a typed, source-linked gate backed by named evidence.” |
| 1:05–1:25 | Briefly point to the Submission Coverage breakdown. | Visible 50% Requirements + 30% Evidence + 20% Tasks arithmetic. | “Coverage measures preparation completeness; it never overrides a mandatory gate.” |
| 1:25–1:35 | Click **Apply Corrigendum #2** once. | Bounded workflow overlay progresses through interpretation, versioning, evidence, and recovery. | “A natural-language amendment raises the minimum from three to four.” |
| 1:35–2:20 | Wait for completion; point to the changed cards and Latest Change panel. | R17 `3 → 4`; v1 `SUPERSEDED`; v2 `PARTIAL`; `FEASIBLE → RECOVERABLE`; `7 / 8`; `84%`; `MEDIUM`. | “The old pass is retained as history but is no longer current. Deterministic logic finds a real gap and a viable recovery path.” |
| 2:20–3:00 | In R17 detail, show Engineer D and recovery tasks. | CISSP `VERIFIED`; CV `STALE`; Availability `UNKNOWN`; R17 remains `PARTIAL`. Tasks request CV, confirm availability, update schedule, then re-run R17. | “A certificate alone is not enough. BidOps refuses to turn the gate green until all evidence and dependent actions are complete.” |
| 3:00–3:25 | Point to the compact impact chain and click **Activity**. | Corrigendum → requirement change → superseded assessment → evidence shortfall → recovery; structured activity summaries only. | “Every transition is traceable without exposing hidden model reasoning.” |
| 3:25–3:50 | Close Activity. In **Scenario**, choose **BLOCKED · no fourth engineer**. | `BLOCKED`; understandable no-viable-recovery reason; coverage remains relatively high. | “This is not a system that always invents a recovery. One unrecoverable mandatory gate overrides a high completeness percentage.” |
| 3:50–4:10 | Choose **UNCERTAIN · ambiguous clause**. | `UNCERTAIN`; human clarification / insufficient authoritative detail; no manufactured pass/fail. | “When the source is ambiguous, the safe answer is uncertainty—not hallucinated compliance.” |
| 4:10–4:20 | Click the header reset icon. | Exact canonical state: `FEASIBLE / 8 / 8 / 91% / LOW`; no old change/tasks. | “And the complete demonstration resets deterministically in one click.” |

Optional closing line: “The LLM interprets language; deterministic rules control the bid state;
people control the decision and submission.”

## Live Bedrock variation

Use it only after the post-approval script passes. Before presenting, run the canonical flow once
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
fallback**. Present the canonical deterministic flow and disclose that the provider is unavailable.

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
