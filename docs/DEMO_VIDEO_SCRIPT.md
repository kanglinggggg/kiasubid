# Demo Video Script

Target scene duration: 4 minutes 33 seconds. The encoded capture remains below the 5-minute limit.

The generated draft uses the actual local application at 1280 x 720, burned-in English lower-thirds,
and a Windows text-to-speech guide track. Replace the guide track with a human recording before final
submission if time permits. Do not change the wording about interpretation mode unless the recorded
run was actually produced by the stated provider.

## Build

Start BidOps, then run:

```powershell
cd C:\GeBIZ
powershell -ExecutionPolicy Bypass -File .\scripts\build-demo-video.ps1
```

Outputs are written under `output/demo-video/` and intentionally excluded from Git.

## Storyboard

| Time | Shot | Screen action | Core message |
|---|---|---|---|
| 0:00-0:14 | Title | Branded title card | A late corrigendum can invalidate a ready bid. |
| 0:14-0:32 | Control room | Reset and show the top of the live app | Tender, state, gates, time, action. |
| 0:32-0:47 | Initial metrics | Hold on FEASIBLE state | FEASIBLE, 8/8, 91%, LOW. |
| 0:47-1:04 | Coverage | Scroll to calculation breakdown | Coverage is preparation, not compliance. |
| 1:04-1:24 | R17 | Open/hold R17 and source detail | Requirement, evidence and provenance are linked. |
| 1:24-1:42 | Corrigendum | Return to the hero action | Three engineers becomes four. |
| 1:42-1:59 | Workflow | Click Apply Corrigendum #2 | Interpret, validate, version and reassess. |
| 1:59-2:19 | New state | Hold on RECOVERABLE metrics | 7/8, 84%, MEDIUM. |
| 2:19-2:35 | Candidate | Scroll to Engineer D | Candidate evidence is incomplete. |
| 2:35-2:53 | Tasks | Show recovery actions | Owners, deadlines and dependencies. |
| 2:53-3:10 | Impact | Show the impact chain | Change propagation remains inspectable. |
| 3:10-3:26 | BLOCKED | Select BLOCKED fixture | High coverage cannot override a hard gate. |
| 3:26-3:41 | UNCERTAIN | Select UNCERTAIN fixture | Missing authority does not become an invented answer. |
| 3:41-4:01 | Responsibility | Three-column title card | LLM interprets; rules decide; humans approve. |
| 4:01-4:21 | Validation | Evidence title card | Tests, regression and live R17 proof. |
| 4:21-4:33 | Close | Closing title card | Know what changed, what it affects and what to recover. |

## Human voiceover

1. A supplier bid can look ready in the morning, until one corrigendum changes a mandatory
   obligation. GeBIZ BidOps helps the team see that change before it becomes a failed submission.
2. This is the supplier-side Bid Control Room. In one view, the bid manager can identify the tender,
   operational feasibility, verified critical gates, remaining time, and the immediate action that
   matters most.
3. The initial bid is feasible. All eight mandatory gates are verified. Submission coverage is
   ninety-one percent, and the current deadline risk is low. Every value comes from backend state.
4. Submission coverage is not a compliance score. It combines requirement, evidence, and task
   preparation. A high percentage can never override an unmet mandatory gate, so the operational
   status remains the controlling decision.
5. Requirement R seventeen requires at least three C I S S P certified engineers. The assessment is
   traceable to the source document, page, section, exact clause, and three complete personnel
   evidence sets.
6. Now a natural-language corrigendum raises the minimum from three engineers to four. This recorded
   run is clearly labelled Demo fallback. The same R seventeen path has separately passed a real
   Amazon Bedrock Nova Lite invocation.
7. BidOps interprets the semantic change, validates the structured output and source, versions the
   affected requirement, supersedes the old assessment, and then reruns deterministic evidence,
   gate, recovery, and deadline rules.
8. The result is not a vague warning. Feasibility moves from feasible to recoverable. Critical gates
   fall from eight of eight to seven of eight, coverage drops to eighty-four percent, and deadline
   risk rises to medium.
9. The system finds a potential fourth engineer, but it does not count him prematurely. His C I S S P
   certificate is verified, while his curriculum vitae is stale and his availability remains unknown.
10. BidOps creates four dependency-aware actions: request the updated curriculum vitae, confirm
    availability, update the manpower schedule, and rerun R seventeen verification. Owners and due
    dates are calculated against the tender deadline.
11. The impact chain keeps the reasoning visible: corrigendum, changed requirement, superseded
    assessment, evidence shortfall, and recovery actions. The previous requirement and its assessment
    remain available as history.
12. BidOps also demonstrates when recovery is not credible. A hard participation restriction produces
    blocked, even if the rest of the submission package is largely complete. Coverage never overrules
    the gate.
13. When authoritative wording or evidence is insufficient, the correct result is uncertain. The
    system asks for clarification instead of manufacturing a pass, a failure, or an unsupported
    recovery plan.
14. The model has a narrow responsibility: interpret tender language and semantic changes.
    Deterministic code owns versions, evidence matching, feasibility, coverage, tasks, and deadlines.
    An authorised person retains final approval and submission.
15. The current build passes sixty-four backend tests, four frontend tests, and all nine deterministic
    regression cases. The live Bedrock R seventeen path passed. Broader unseen extraction remains a
    measured limitation and still requires human review.
16. GeBIZ BidOps turns a late tender change into a source-linked recovery plan, before the closing time
    turns that change into a lost bid.

The machine-readable timing and caption source is `docs/video/demo-scenes.json`.
