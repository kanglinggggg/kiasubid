from typing import Any

from app.portfolio.schemas import (
    CapabilityPool,
    DecisionRoute,
    OperationalState,
    PortfolioOpportunity,
    PortfolioSimulationRequest,
)


def _state_for_counts(*, proven: int, potential: int, demand: int, uncertain: bool) -> OperationalState:
    if demand > potential:
        return "BLOCKED"
    if uncertain:
        return "UNCERTAIN"
    if demand > proven:
        return "RECOVERABLE"
    return "FEASIBLE"


def _peak_for_capability(
    capability: CapabilityPool, opportunities: list[PortfolioOpportunity]
) -> dict[str, Any]:
    demands = [
        (opportunity, demand)
        for opportunity in opportunities
        for demand in opportunity.demands
        if demand.capability == capability.capability
    ]
    if not demands:
        return {
            "capability": capability.capability,
            "label": capability.label,
            "proven_count": capability.proven_count,
            "potential_count": capability.potential_count,
            "peak_demand": 0,
            "minimum_peak_demand": 0,
            "shortfall": 0,
            "minimum_shortfall": 0,
            "evidence_gap": 0,
            "minimum_evidence_gap": 0,
            "state": "FEASIBLE",
            "active_opportunity_ids": [],
            "peak_demand_refs": [],
            "peak_windows": [],
            "window_start": None,
            "window_end": None,
            "uncertain_demand": False,
            "uncertain_opportunity_ids": [],
            "provenance": capability.provenance,
        }

    indexed_demands = [
        (opportunity, demand, demand_index)
        for opportunity in opportunities
        for demand_index, demand in enumerate(opportunity.demands)
        if demand.capability == capability.capability
    ]
    points = sorted({demand.starts_at for _, demand, _ in indexed_demands})
    point_results: list[dict[str, Any]] = []
    for point in points:
        active = [
            item
            for item in indexed_demands
            if item[1].starts_at <= point < item[1].ends_at
        ]
        point_results.append(
            {
                "point": point,
                "active": active,
                "known_demand": sum(demand.count or 0 for _, demand, _ in active),
                "minimum_demand": sum(
                    demand.count if demand.count is not None else 1
                    for _, demand, _ in active
                ),
                "uncertain": any(demand.count is None for _, demand, _ in active),
            }
        )

    minimum_peak = max(result["minimum_demand"] for result in point_results)
    peak_results = [
        result for result in point_results if result["minimum_demand"] == minimum_peak
    ]
    primary_peak = peak_results[0]
    peak_active = primary_peak["active"]
    peak_point = primary_peak["point"]

    # The constrained window begins when peak concurrency actually starts, not when
    # the earliest contributing engagement began.
    window_start = peak_point
    window_end = min(demand.ends_at for _, demand, _ in peak_active)
    peak_ref_keys = {
        (opportunity.id, demand_index)
        for result in peak_results
        for opportunity, _, demand_index in result["active"]
    }
    peak_demand_refs = [
        {"opportunity_id": opportunity_id, "demand_index": demand_index}
        for opportunity_id, demand_index in sorted(peak_ref_keys)
    ]
    uncertain_opportunity_ids = sorted(
        {opportunity.id for opportunity, demand in demands if demand.count is None}
    )
    any_uncertain = bool(uncertain_opportunity_ids)
    exact_peak = None if any_uncertain else minimum_peak
    minimum_shortfall = max(0, minimum_peak - capability.potential_count)
    minimum_evidence_gap = max(
        0, min(minimum_peak, capability.potential_count) - capability.proven_count
    )
    state = _state_for_counts(
        proven=capability.proven_count,
        potential=capability.potential_count,
        demand=minimum_peak,
        uncertain=any_uncertain,
    )
    return {
        "capability": capability.capability,
        "label": capability.label,
        "proven_count": capability.proven_count,
        "potential_count": capability.potential_count,
        "peak_demand": exact_peak,
        "minimum_peak_demand": minimum_peak,
        "shortfall": None if any_uncertain else minimum_shortfall,
        "minimum_shortfall": minimum_shortfall,
        "evidence_gap": None if any_uncertain else minimum_evidence_gap,
        "minimum_evidence_gap": minimum_evidence_gap,
        "state": state,
        "active_opportunity_ids": sorted(
            {opportunity.id for opportunity, _, _ in peak_active}
        ),
        "peak_demand_refs": peak_demand_refs,
        "peak_windows": [
            {
                "window_start": result["point"],
                "window_end": min(demand.ends_at for _, demand, _ in result["active"]),
                "active_opportunity_ids": sorted(
                    {opportunity.id for opportunity, _, _ in result["active"]}
                ),
                "known_demand": result["known_demand"],
                "minimum_demand": result["minimum_demand"],
                "uncertain_demand": result["uncertain"],
            }
            for result in peak_results
        ],
        "window_start": window_start,
        "window_end": window_end,
        "uncertain_demand": any_uncertain,
        "uncertain_opportunity_ids": uncertain_opportunity_ids,
        "provenance": capability.provenance,
    }


def _overall_state(capabilities: list[dict[str, Any]]) -> OperationalState:
    states = {item["state"] for item in capabilities}
    for state in ("BLOCKED", "UNCERTAIN", "RECOVERABLE", "FEASIBLE"):
        if state in states:
            return state  # type: ignore[return-value]
    return "FEASIBLE"


def evaluate_portfolio(payload: PortfolioSimulationRequest) -> dict[str, Any]:
    configured = {item.capability: item for item in payload.capabilities}
    demanded = {
        demand.capability for opportunity in payload.opportunities for demand in opportunity.demands
    }
    missing = sorted(demanded - configured.keys())
    if missing:
        raise ValueError(f"No capability pool is configured for: {', '.join(missing)}")

    capability_results = [
        _peak_for_capability(capability, payload.opportunities)
        for capability in sorted(payload.capabilities, key=lambda item: item.capability)
    ]
    state = _overall_state(capability_results)
    constrained = [item for item in capability_results if item["state"] != "FEASIBLE"]
    if state == "FEASIBLE":
        reason = "All concurrent mandatory capability demand fits within proven company capacity."
    elif state == "RECOVERABLE":
        reason = (
            "Concurrent demand exceeds proven capacity but fits within identified potential capacity; "
            "evidence or availability must be completed before allocation."
        )
    elif state == "UNCERTAIN":
        reason = (
            "At least one concurrent mandatory demand has no authoritative count, so the portfolio "
            "cannot be safely allocated yet."
        )
    else:
        reason = (
            "The minimum possible concurrent mandatory demand exceeds both proven and identified "
            "potential company capacity."
            if any(item["uncertain_demand"] for item in capability_results)
            else "Concurrent mandatory demand exceeds both proven and identified potential company capacity."
        )

    return {
        "scenario_label": payload.scenario_label,
        "state": state,
        "reason": reason,
        "capabilities": capability_results,
        "constrained_capabilities": [item["capability"] for item in constrained],
        "opportunities": [
            {
                "id": opportunity.id,
                "title": opportunity.title,
                "agency": opportunity.agency,
                "reference_number": opportunity.reference_number,
                "stage": opportunity.stage,
                "synthetic": opportunity.synthetic,
                "demands": [demand.model_dump(mode="json") for demand in opportunity.demands],
            }
            for opportunity in sorted(payload.opportunities, key=lambda item: item.id)
        ],
        "calculation": {
            "rule": (
                "For each capability, sum mandatory demand across overlapping delivery windows. "
                "FEASIBLE fits proven capacity; RECOVERABLE fits only after potential capacity is "
                "verified; BLOCKED exceeds potential capacity. An unknown mandatory count contributes "
                "a lower bound of one: if that lower bound already exceeds potential capacity the result "
                "is BLOCKED, otherwise it is UNCERTAIN and exact demand totals are null."
            ),
            "precedence": ["BLOCKED", "UNCERTAIN", "RECOVERABLE", "FEASIBLE"],
        },
    }


def _route_for_state(state: OperationalState) -> DecisionRoute:
    return {
        "FEASIBLE": "BID",
        "RECOVERABLE": "RECOVER",
        "UNCERTAIN": "CLARIFY",
        "BLOCKED": "WALK_AWAY",
    }[state]  # type: ignore[return-value]


def strategy_routes(payload: PortfolioSimulationRequest) -> list[dict[str, Any]]:
    current = evaluate_portfolio(payload)
    continue_title = (
        "Do not proceed with the current combination"
        if current["state"] == "BLOCKED"
        else "Continue the current portfolio"
    )
    routes: list[dict[str, Any]] = [
        {
            "id": "continue-portfolio",
            "route": _route_for_state(current["state"]),
            "title": continue_title,
            "resulting_state": current["state"],
            "included_opportunity_ids": sorted(item.id for item in payload.opportunities),
            "tradeoff": current["reason"],
            "requires_human_decision": True,
        }
    ]

    if len(payload.opportunities) > 1:
        for opportunity in sorted(payload.opportunities, key=lambda item: item.id):
            reduced = payload.model_copy(
                update={
                    "opportunities": [opportunity],
                    "scenario_label": f"Prioritise {opportunity.reference_number}",
                }
            )
            result = evaluate_portfolio(reduced)
            routes.append(
                {
                    "id": f"prioritise-{opportunity.id.lower()}",
                    "route": _route_for_state(result["state"]),
                    "title": f"Prioritise {opportunity.reference_number}",
                    "resulting_state": result["state"],
                    "included_opportunity_ids": [opportunity.id],
                    "tradeoff": (
                        f"Protects {opportunity.title}; other opportunities are deferred and require "
                        "a separate human no-bid decision."
                    ),
                    "requires_human_decision": True,
                }
            )

    blocked = [item for item in current["capabilities"] if item["state"] == "BLOCKED"]
    if blocked:
        external_slots = sum(item["minimum_shortfall"] for item in blocked)
        routes.append(
            {
                "id": "qualified-delivery-partner",
                "route": "PARTNER",
                "title": "Validate a qualified delivery partner",
                "resulting_state": "UNCERTAIN",
                "included_opportunity_ids": sorted(item.id for item in payload.opportunities),
                "tradeoff": (
                    f"Would require {external_slots} additional verified capability slot"
                    f"{'s' if external_slots != 1 else ''}; no partner or eligibility is assumed."
                ),
                "requires_human_decision": True,
            }
        )
    return routes


def capability_roadmap(
    payload: PortfolioSimulationRequest, evaluation: dict[str, Any]
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for item in evaluation["capabilities"]:
        peak_refs = {
            (reference["opportunity_id"], reference["demand_index"])
            for reference in item["peak_demand_refs"]
        }
        related = [
            (opportunity, demand)
            for opportunity in payload.opportunities
            for demand_index, demand in enumerate(opportunity.demands)
            if demand.capability == item["capability"]
            and (opportunity.id, demand_index) in peak_refs
        ]
        if item["state"] == "UNCERTAIN" or not related:
            continue
        shared = {
            "capability": item["capability"],
            "opportunity_ids": sorted({opportunity.id for opportunity, _ in related}),
            "opportunities_affected": len({opportunity.id for opportunity, _ in related}),
            "requirement_count": len(related),
            "earliest_window_start": min(demand.starts_at for _, demand in related),
            "sources": sorted({demand.source for _, demand in related}),
        }
        if item["minimum_evidence_gap"]:
            actions.append(
                {
                    **shared,
                    "gap_type": "EVIDENCE_OR_AVAILABILITY",
                    "known_gap": item["minimum_evidence_gap"],
                    "action": (
                        "Complete evidence and availability for "
                        f"{item['minimum_evidence_gap']} candidate"
                    ),
                    "effect": "Converts identified potential capacity into proven delivery capacity.",
                    "basis": item["provenance"],
                }
            )
        if item["minimum_shortfall"]:
            actions.append(
                {
                    **shared,
                    "gap_type": "ADDITIONAL_CAPACITY_REQUIRED",
                    "known_gap": item["minimum_shortfall"],
                    "action": (
                        f"Source {item['minimum_shortfall']} additional verified capability slot"
                    ),
                    "effect": "Closes the hard concurrent-capacity shortfall in this scenario.",
                    "basis": "Calculated peak demand minus identified potential capacity.",
                }
            )
    actions.sort(
        key=lambda action: (
            -action["opportunities_affected"],
            -action["known_gap"],
            action["earliest_window_start"],
            action["capability"],
            action["gap_type"],
        )
    )
    for index, action in enumerate(actions, start=1):
        action["priority"] = index
    return actions
