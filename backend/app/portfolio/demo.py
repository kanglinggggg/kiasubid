from datetime import datetime
from typing import Any

from app.models import Requirement, Tender
from app.portfolio.engine import capability_roadmap, evaluate_portfolio
from app.portfolio.schemas import PortfolioSimulationRequest
from app.services.assessment import AssessmentResult
from app.services.clock import now


def _scenario(current_tender: Tender, minimum_count: int) -> PortfolioSimulationRequest:
    return PortfolioSimulationRequest.model_validate(
        {
            "scenario_label": f"R17 requires {minimum_count} CISSP personnel",
            "capabilities": [
                {
                    "capability": "CISSP_DELIVERY_PERSONNEL",
                    "label": "CISSP delivery personnel",
                    "proven_count": 3,
                    "potential_count": 4,
                    "provenance": (
                        "Three complete R17 personnel evidence sets plus Engineer D as one "
                        "identified candidate with unresolved CV and availability."
                    ),
                }
            ],
            "opportunities": [
                {
                    "id": current_tender.id,
                    "title": current_tender.title,
                    "agency": current_tender.agency,
                    "reference_number": current_tender.reference_number,
                    "stage": "ACTIVE_BID",
                    "demands": [
                        {
                            "capability": "CISSP_DELIVERY_PERSONNEL",
                            "count": minimum_count,
                            "starts_at": datetime(2026, 9, 1, 0, 0),
                            "ends_at": datetime(2026, 12, 1, 0, 0),
                            "source": "Current R17 structured minimum_count",
                        }
                    ],
                    "synthetic": True,
                },
                {
                    "id": "BID-DEMO-SOC-008",
                    "title": "Municipal SOC Operations Extension",
                    "agency": "Demo Municipal Authority",
                    "reference_number": "DMA/SOC/2026/008",
                    "stage": "DELIVERY_COMMITMENT",
                    "demands": [
                        {
                            "capability": "CISSP_DELIVERY_PERSONNEL",
                            "count": 1,
                            "starts_at": datetime(2026, 10, 1, 0, 0),
                            "ends_at": datetime(2027, 1, 1, 0, 0),
                            "source": "Synthetic companion-bid staffing commitment",
                        }
                    ],
                    "synthetic": True,
                },
            ],
        }
    )


def build_demo_portfolio_impact(
    tender: Tender,
    current_requirement: Requirement,
    assessment_result: AssessmentResult,
) -> dict[str, Any]:
    """Build a simulation-only cross-bid view without mutating either bid or staff allocation."""
    minimum_count = int(current_requirement.rule_config["minimum_count"])
    before_payload = _scenario(tender, 3)
    after_payload = _scenario(tender, minimum_count)

    proven = len(assessment_result.usable_employee_ids)
    potential = proven + len(assessment_result.recovery_candidate_ids)
    before_payload.capabilities[0].proven_count = proven
    before_payload.capabilities[0].potential_count = potential
    after_payload.capabilities[0].proven_count = proven
    after_payload.capabilities[0].potential_count = potential

    before = evaluate_portfolio(before_payload)
    after = evaluate_portfolio(after_payload)
    constraint = after["capabilities"][0]
    current_id = tender.id
    other_id = "BID-DEMO-SOC-008"
    shortfall = constraint["shortfall"]

    return {
        "mode": "SIMULATION_ONLY",
        "synthetic": True,
        "trigger": {
            "stable_key": current_requirement.stable_key,
            "change_summary": f"Minimum count 3 → {minimum_count}",
        },
        "summary": (
            "Recovering R17 creates a shared-personnel conflict between this tender and an "
            "overlapping delivery commitment."
        ),
        "before_state": before["state"],
        "after_state": after["state"],
        "assumptions": [
            "The companion delivery commitment and service windows are synthetic demo inputs.",
            "Potential capacity assumes Engineer D's CV and availability gaps are resolved.",
            "No employee is double-booked across overlapping delivery windows.",
            "No external delivery partner is assumed until its qualification and availability are verified.",
        ],
        "capacity": {
            "capability": constraint["label"],
            "unit": "concurrent CISSP assignments",
            "proven_now": constraint["proven_count"],
            "potential_after_recovery": constraint["potential_count"],
            "concurrent_required": constraint["peak_demand"],
            "shortfall": shortfall,
            "window_start": constraint["window_start"],
            "window_end": constraint["window_end"],
        },
        "affected_bids": [
            {
                "bid_id": current_id,
                "reference_number": tender.reference_number,
                "title": tender.title,
                "relationship": "CURRENT",
                "required_capacity": minimum_count,
            },
            {
                "bid_id": other_id,
                "reference_number": "DMA/SOC/2026/008",
                "title": "Municipal SOC Operations Extension",
                "relationship": "OTHER",
                "required_capacity": 1,
            },
        ],
        "routes": [
            {
                "id": "protect-current-tender",
                "action": "RECOVER",
                "label": "Protect this tender",
                "rationale": (
                    "Complete Engineer D's evidence and reserve all four potential CISSP personnel "
                    "for the amended R17 obligation."
                ),
                "outcomes": [
                    {"bid_id": current_id, "status": "RECOVERABLE"},
                    {"bid_id": other_id, "status": "BLOCKED"},
                ],
                "unresolved_facts": ["Engineer D's current CV", "Engineer D's availability"],
                "requires_human_decision": True,
            },
            {
                "id": "protect-existing-commitment",
                "action": "WALK_AWAY",
                "label": "Protect existing commitment",
                "rationale": (
                    "Keep one CISSP assignment for the companion bid; only three potential slots "
                    "remain for R17, so the amended tender cannot currently proceed."
                ),
                "outcomes": [
                    {"bid_id": current_id, "status": "BLOCKED"},
                    {"bid_id": other_id, "status": "FEASIBLE"},
                ],
                "unresolved_facts": [],
                "requires_human_decision": True,
            },
            {
                "id": "verify-external-capacity",
                "action": "PARTNER",
                "label": "Verify external capacity",
                "rationale": (
                    f"Both bids may remain viable if {max(shortfall, 1)} additional qualified "
                    "delivery slot is verified before allocation."
                ),
                "outcomes": [
                    {"bid_id": current_id, "status": "UNCERTAIN"},
                    {"bid_id": other_id, "status": "FEASIBLE"},
                ],
                "unresolved_facts": [
                    "Partner qualification",
                    "Partner availability",
                    "Tender permission for the proposed delivery arrangement",
                ],
                "requires_human_decision": True,
            },
        ],
        "capability_roadmap": capability_roadmap(after_payload, after),
        "calculation": after["calculation"],
        "calculated_at": now(),
    }
