# Demo video script

Target duration: **4 minutes 34 seconds**. The generated capture stays below the five-minute
submission limit and now includes the cross-bid capability story.

The draft records the real local application at 1280 × 720 with burned-in English lower-thirds.
Narration is optional: use `-NoNarration` for a subtitle-only teammate preview, or replace the
Windows guide voice with a human recording for submission. Describe the interpretation provider
shown in the recorded UI; do not infer it from configuration.

## Build

Install the declared frontend dependencies once, start BidOps, and run the builder:

```powershell
cd C:\GeBIZ\frontend
npm install

cd C:\GeBIZ
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1 -SkipInstall
powershell -ExecutionPolicy Bypass -File .\scripts\build-demo-video.ps1
```

The capture uses the declared `playwright-core` package and an installed Chrome or Edge browser.
An explicit alternative package directory can be passed with `-PlaywrightPackageDir`. A full
FFmpeg build is also required. Outputs are written under `output/demo-video/` and excluded from Git.

For a subtitle-only version:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-demo-video.ps1 -NoNarration
```

## Storyboard

| Time | Shot | Screen action | Core message |
|---|---|---|---|
| 0:00–0:12 | Title | Branded title card | One clause change can create both a bid gap and a portfolio trade-off. |
| 0:12–0:27 | Control room | Reset and show the live app | One operational view of state, gates, time, and action. |
| 0:27–0:39 | Initial metrics | Hold on the baseline | `FEASIBLE / 8 of 8 / 91% / LOW`. |
| 0:39–0:52 | Coverage | Show calculation breakdown | Coverage is preparation, not compliance. |
| 0:52–1:10 | R17 | Show requirement and source detail | The gate and its evidence are traceable. |
| 1:10–1:24 | Corrigendum | Return to the hero action | Required personnel changes from three to four. |
| 1:24–1:42 | Workflow | Apply Corrigendum #2 | Interpret, validate, version, reassess, and replan. |
| 1:42–1:59 | New state | Hold on changed metrics | `RECOVERABLE / 7 of 8 / 84% / MEDIUM`. |
| 1:59–2:13 | Candidate | Show Engineer D | Potential capacity is not verified capacity. |
| 2:13–2:28 | Tasks | Show recovery actions | Recovery becomes owned, dated work. |
| 2:28–2:41 | Impact | Show the bid-level chain | The old pass remains inspectable history. |
| 2:41–2:53 | Cross-bid trigger | Show the new Latest Change panel | The validated delta crosses tender boundaries. |
| 2:53–3:11 | Capacity | Open Portfolio impact | Current bid `RECOVERABLE`; continue-all portfolio `BLOCKED`; five vs four. |
| 3:11–3:36 | Routes | Click all three route cards | Consequences, not recommendations or actions. |
| 3:36–3:52 | Roadmap | Show capability next steps | Known gaps become focused capability work. |
| 3:52–4:09 | Responsibility | Three-column title card | LLM interprets; rules calculate; humans decide and act. |
| 4:09–4:24 | Validation | Evidence title card | Full suites, nine-case benchmark, and separate live R17 proof. |
| 4:24–4:34 | Close | Closing title card | Know what changed, what collides, and what humans must decide. |

## Human voiceover

1. A supplier bid can look ready until one corrigendum changes a mandatory obligation. GeBIZ
   BidOps shows the bid impact, recovery work, and the capacity trade-off that follows.
2. The Bid Control Room brings the tender, operational state, verified gates, remaining time, and
   immediate action into one view.
3. The baseline is feasible: eight of eight mandatory gates, ninety-one percent submission
   coverage, and low deadline risk.
4. Coverage measures preparation completeness. It never overrides a broken mandatory gate, so
   operational feasibility remains the controlling state.
5. R seventeen requires three C I S S P certified personnel. Its assessment links to the source
   page, exact clause, and three complete evidence sets.
6. A supplied corrigendum now raises the minimum from three to four. This run is labelled Demo
   fallback unless a real provider result was persisted.
7. The workflow interprets the change, validates its structure and source, versions the
   requirement, supersedes the old assessment, and reruns deterministic checks.
8. The result is specific: feasible becomes recoverable, verified gates fall to seven of eight,
   coverage becomes eighty-four percent, and deadline risk becomes medium.
9. Engineer D is only potential capacity. The certificate is verified, but the curriculum vitae
   is stale and availability remains unknown.
10. BidOps creates dependency-aware work to update evidence, confirm availability, revise the
    schedule, and rerun verification before the tender deadline.
11. The impact chain preserves how the source change produced a new requirement, a stale
    assessment, an evidence gap, and recovery actions.
12. The validated R seventeen increase also changes dated capability demand. A synthetic companion
    commitment now overlaps the current tender.
13. The current bid is still recoverable, but pursuing both supplied opportunities is blocked:
    five concurrent slots are required and only four potential slots are identified.
14. Three counterfactual routes show consequences under stated assumptions. Protect either pursuit,
    or keep both uncertain while external capacity and tender permission are verified. No route
    executes an action.
15. Known recurring gaps become focused capability next steps. They are derived only from supplied
    opportunities and do not predict qualification, awards, or revenue.
16. The model interprets language. Deterministic code owns versions, evidence, bid state, overlap
    arithmetic, and route outcomes. People retain every external decision and action.
17. Backend, frontend, and deterministic benchmark checks pass. The live R seventeen path passed
    separately. Unseen extraction still requires human review.
18. GeBIZ BidOps turns one late clause change into traceable recovery and an explicit cross-bid
    decision before closing time.

The machine-readable timing, lower-thirds, and narration source is
`docs/video/demo-scenes.json`.
