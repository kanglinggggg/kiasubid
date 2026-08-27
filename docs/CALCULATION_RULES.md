# Deterministic calculation rules

This document defines the exact policy implemented by GeBIZ BidOps. The API exposes the same inputs and intermediate values under `calculations` in every `GET /api/bids/{bid_id}` response.

All calculations operate on the current SQLite state. Requirement history remains stored, but only the highest version of each `stable_key` participates in current-state calculations.

## Operational Feasibility

Inputs:

- the current version of every `MANDATORY` requirement;
- the latest assessment for each current requirement;
- recovery tasks linked to unresolved requirements;
- each recovery task's status and `latest_safe_at` or `due_at`;
- tender closing time.

Evaluation precedence is deterministic:

1. `BLOCKED`: at least one mandatory `PARTIAL` or `UNMET` assessment has no recovery task set, or any task in its recovery set is `BLOCKED` or cannot finish before closing.
2. `UNCERTAIN`: there is no known blocker, but at least one mandatory requirement has no assessment or has an `UNCERTAIN` assessment.
3. `RECOVERABLE`: every mandatory gap is `PARTIAL` or `UNMET`, and every task in each non-empty recovery set is non-blocked and scheduled before closing.
4. `FEASIBLE`: every current mandatory requirement's latest assessment is `SATISFIED`.

Finding a candidate record does not make an assessment satisfied. For R17, an employee counts only when all of these are true:

- the employee has a `VERIFIED` CISSP Evidence record;
- the certificate remains valid at tender closing;
- the employee has a `VERIFIED` current CV Evidence record;
- availability is `AVAILABLE`.

The API trace includes the unresolved requirement IDs, assessment states, linked recovery task IDs, and whether each recovery path is viable.

## Critical Gates

Critical Gates are not a score.

```text
total = count(current requirements where gate_type = MANDATORY)

verified = count(those requirements where latest assessment = SATISFIED)
```

Superseded requirement versions are excluded because their newer version is current. `PARTIAL`, `UNMET`, `UNCERTAIN`, a missing assessment, and `SUPERSEDED` never count as verified.

The API trace lists every counted requirement version and its assessment ID and status.

## Submission Coverage

Submission Coverage measures preparation completeness, not compliance. A bid may have high coverage and still be `BLOCKED` by one mandatory gate.

```text
Submission Coverage =
  0.50 × Requirement Coverage
  + 0.30 × Evidence Coverage
  + 0.20 × Task Coverage
```

### Requirement Coverage

Requirement weights:

| Gate | Units |
|---|---:|
| `MANDATORY` | 3 |
| `SCORED` | 1 |
| `INFORMATIONAL` | 0 |

Assessment completion factors:

| Assessment | Factor |
|---|---:|
| `SATISFIED` | 1.0 |
| `PARTIAL` | 0.5 |
| `UNMET` | 0.0 |
| `UNCERTAIN` | 0.0 |
| `SUPERSEDED` | 0.0 |

```text
Requirement Coverage =
  Σ(current requirement units × assessment factor)
  ÷ Σ(current requirement units)
```

### Evidence Coverage

```text
Evidence Coverage =
  VERIFIED Evidence Registry records for the company
  ÷ all Evidence Registry records for the company
```

The MVP uses the synthetic single-company registry. Evidence status must equal `VERIFIED`; `STALE`, `MISSING`, and `UNVERIFIED` contribute zero.

### Task Coverage

```text
Task Coverage =
  tender tasks with status DONE
  ÷ all tender tasks
```

All other task states contribute zero.

The backend retains the raw weighted percentage and rounds it to the nearest whole percentage point for the headline UI. The response exposes every component numerator, denominator, percentage, weight, and weighted-point contribution.

Initial demo example:

```text
Requirement Coverage: 30 / 31 weighted units = 96.77% × 50% = 48.39 points
Evidence Coverage:    18 / 20 records        = 90.00% × 30% = 27.00 points
Task Coverage:         8 / 10 tasks          = 80.00% × 20% = 16.00 points

Raw total: 91.39%
Displayed: 91%
```

After Corrigendum #2, the R17 factor falls from 1.0 to 0.5 and four recovery tasks are created. The deterministic result is approximately 84.40%, displayed as 84%.

## Deadline Risk

Inputs are every open task with status `OPEN`, `IN_PROGRESS`, or `WAITING`.

For each task:

```text
latest_finish = latest_safe_at if present, otherwise due_at
latest_start  = latest_finish - estimated_duration_hours
slack_hours   = latest_start - calculation_time
```

The open task with the smallest slack drives the headline risk:

| Minimum slack | Risk |
|---|---|
| `> 48h` | `LOW` |
| `> 12h` and `≤ 48h` | `MEDIUM` |
| `≥ 0h` and `≤ 12h` | `HIGH` |
| `< 0h` | `MISSED` |

If no open tasks exist, risk is `LOW` and there is no driver task.

In `DEMO_MODE`, the calculation time is the fixed synthetic timestamp `2026-08-21 13:00 SGT`, so the demonstration remains repeatable. Outside demo mode, UTC wall-clock time is used. The API trace exposes the calculation timestamp, driver task, latest start, duration, slack, thresholds, and all evaluated open tasks.

## Persistence consistency

Operational Feasibility, Submission Coverage, and Deadline Risk are persisted after workflow mutations. The read model recalculates each value from current state and returns both the calculated and persisted values with a `matches_persisted_value` flag. The UI displays the calculated trace value.
