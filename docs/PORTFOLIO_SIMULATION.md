# Portfolio capability simulation

## Purpose

The portfolio layer answers a narrower question than bid readiness:

> If several opportunities need the same capability during overlapping service periods, does the
> supplier have enough identified capacity to keep pursuing all of them?

It extends the existing bid-control story through one auditable chain:

```text
Validated clause change → Dated capability-demand delta → Cross-tender collision
→ { Deterministic counterfactual options + Capability roadmap } → Human decision
```

This is a read-only planning simulation. It does not schedule named people, change a bid, reserve
staff, contact a partner, withdraw an opportunity, or submit anything.

## Demonstrated R17 scenario

The bid-level hero remains unchanged. Corrigendum #2 changes R17 from three to four required
CISSP-certified personnel, giving:

```text
Current bid: FEASIBLE / 8 of 8 / 91% / LOW
          → RECOVERABLE / 7 of 8 / 84% / MEDIUM
```

The separate portfolio simulation uses these **synthetic demo assumptions**:

- the current tender requires three capability slots before the amendment and four after it;
- the current tender's synthetic service window is 1 September to 1 December 2026;
- a fictional companion opportunity requires one slot from 1 October 2026 to 1 January 2027, so
  the synthetic overlap is 1 October to 1 December 2026;
- three slots are proven now and a fourth is identified only as potential after its evidence and
  availability gaps are resolved;
- one capability slot cannot be double-booked across overlapping windows;
- the companion opportunity, service periods, pool counts, and capacity provenance are demo inputs,
  not GeBIZ, calendar, HR, customer, or market records.

The arithmetic is therefore:

| View | Current tender | Companion | Peak demand | Proven now | Potential after recovery | Hard shortfall |
|---|---:|---:|---:|---:|---:|---:|
| Before R17 change | 3 | 1 | 4 | 3 | 4 | 0 |
| After R17 change | 4 | 1 | 5 | 3 | 4 | 1 |

Before the change, the supplied portfolio fits only after the fourth potential slot is verified, so
its state is `RECOVERABLE`. After the change, demand exceeds even identified potential capacity, so
the continue-all portfolio becomes `BLOCKED`. The amended current bid remains `RECOVERABLE` at bid
level. These statuses are intentionally separate.

## Deterministic calculation

`POST /api/portfolio/simulate` accepts caller-supplied capability pools and opportunities. Each
demand has a capability, mandatory count, source label, and service-window start and end.

For each capability, ordinary code:

1. finds concurrent demands using half-open windows (`start <= time < end`), so one period ending
   exactly when another begins does not overlap;
2. sums the mandatory counts at each overlap point, treating an unknown mandatory count as a
   lower bound of one because supplied known counts must be positive;
3. compares the peak lower bound with proven and identified potential counts; and
4. applies `BLOCKED > UNCERTAIN > RECOVERABLE > FEASIBLE` precedence.

| Portfolio state | Deterministic meaning |
|---|---|
| `FEASIBLE` | Peak demand fits within the supplied proven count. |
| `RECOVERABLE` | Peak demand exceeds proven count but fits within supplied potential count. |
| `BLOCKED` | Exact peak demand, or its minimum possible lower bound, exceeds supplied potential count. |
| `UNCERTAIN` | A mandatory count is missing and its lower bound does not already prove a blocker. |

The endpoint does not persist its input or result. Stable input produces stable arithmetic; the
model does not rank or override these states.

When any mandatory count is unknown, `peak_demand`, `shortfall`, and `evidence_gap` are `null`
rather than false precision. `minimum_peak_demand`, `minimum_shortfall`, and
`minimum_evidence_gap` expose only what can be proved from the positive-count lower bound. A known
lower bound that already exceeds potential capacity is therefore `BLOCKED`, even if another exact
count is still missing.

Input timestamps without an offset are treated as UTC. Offset-aware ISO-8601 timestamps are
normalised to UTC before interval arithmetic, so mixed timezone notation cannot change overlap
results or produce incomparable datetime values.

If the same maximum occurs in disjoint windows, `window_start`, `window_end`, and
`active_opportunity_ids` describe the earliest primary peak. `peak_windows` lists each tied window,
while every tied peak contributes to roadmap provenance. A fully satisfiable non-peak engagement is
not labelled as affected.

## Counterfactual options

After the R17 change, the demo compares three human-controlled routes:

- **Protect this tender**: finish the fourth candidate's evidence and reserve four potential slots
  for R17; the companion commitment becomes `BLOCKED` in that counterfactual.
- **Protect existing commitment**: retain one slot for the companion; the amended current tender
  becomes `BLOCKED` in that counterfactual.
- **Verify external capacity**: keep both in view only as `UNCERTAIN` until qualification,
  availability, and permission for the delivery arrangement are established.

These routes describe consequences under stated assumptions. They are not recommendations, value
rankings, named-person allocations, or automatic actions. BidOps has no verified partner registry
and does not assume that a tender permits subcontracting.

## Capability roadmap

The roadmap aggregates known evidence or capacity gaps across the opportunities active at the
constrained overlap. For the demo it shows one additional verified slot needed to close the hard concurrent
shortfall, plus the evidence and availability work still required for one identified candidate.

For an early-stage supplier or startup, this is a focused capability-planning view: it can show
which known eligibility gaps recur across the opportunity set. It is not an incubator, proposal
writer, training programme, hiring instruction, or forecast of awards or revenue. Its scope is
limited to the supplied opportunities and their stated sources.

## Responsibility boundary

| Layer | Role in this flow |
|---|---|
| Language model or demo fallback | Interpret the supplied clause or amendment into a typed change with source provenance. |
| Deterministic code | Validate structure and provenance; version R17; recalculate bid state; sum dated capability demand; expose collision, state, routes, and roadmap. |
| Human team | Confirm source completeness and capacity facts; choose whether to recover, clarify, seek a partner, deprioritise, or proceed; perform every external action. |

## Claim guardrails

The demonstrated capability supports only the claims above. Do not present it as:

- a named-person workforce scheduler or live HR/calendar integration;
- market pricing, margin optimisation, award probability, or a commercial bid/no-bid recommender;
- autonomous monitoring, staffing, partner outreach, withdrawal, or submission;
- evidence of preferential treatment for SMEs;
- proof of agency-specific scoring preferences or fixed policy requirements;
- legal, cybersecurity, labour-policy, or procurement compliance certification;
- a world-first product or a guarantee that a supplier will qualify or win.

The safe competition statement is: **BidOps demonstrates how one validated clause change can alter
dated delivery-capability demand across a supplied opportunity set, and lets a human compare
deterministically calculated consequences.**

## Current limitations

- All portfolio-demo facts are synthetic and are not loaded from GeBIZ, ACRA, HR, calendars, or
  delivery systems.
- Capacity is represented as aggregate counts. The implementation does not prove which specific
  person is assigned to which opportunity.
- Potential capacity is caller-supplied and may include unresolved evidence or availability; it is
  not treated as proven.
- The generic endpoint evaluates capability count and interval overlap. It does not evaluate price,
  opportunity value, strategic fit, partner eligibility, or execution risk.
- Roadmap actions address known scenario gaps only. Broader capability discovery and independent
  validation remain future work.
