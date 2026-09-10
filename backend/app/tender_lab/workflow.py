from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.tender_lab.engine import (
    analyse_pricing,
    build_brief,
    build_calendar_ics,
    build_next_actions,
    build_startup_coach,
    build_strategy_routes,
    draft_clarifications,
    extract_milestones,
    scan_policy_checks,
)
from app.tender_lab.schemas import (
    ClarificationQuestion,
    Milestone,
    NextAction,
    PolicyCheck,
    PricingAnalysis,
    StartupCoach,
    StrategyRoute,
    TenderBrief,
    TenderLabRequest,
    TenderLabResponse,
    TraceStep,
)


class TenderLabState(TypedDict, total=False):
    payload: TenderLabRequest
    brief: TenderBrief
    policy_checks: list[PolicyCheck]
    clarification_questions: list[ClarificationQuestion]
    milestones: list[Milestone]
    pricing: PricingAnalysis | None
    startup_coach: StartupCoach | None
    strategy_routes: list[StrategyRoute]
    next_actions: list[NextAction]
    trace: list[TraceStep]
    calendar_ics: str


def _append_trace(
    state: TenderLabState, *, step_id: str, label: str, detail: str, skipped: bool = False
) -> list[TraceStep]:
    return [
        *state.get("trace", []),
        TraceStep(
            id=step_id,
            label=label,
            status="SKIPPED" if skipped else "COMPLETED",
            detail=detail,
        ),
    ]


def _brief_node(state: TenderLabState) -> TenderLabState:
    payload = state["payload"]
    return {
        "brief": build_brief(payload),
        "trace": _append_trace(
            state,
            step_id="INGEST",
            label="Read supplied tender text",
            detail="Built a plain-language brief while retaining supplied page markers.",
        ),
    }


def _policy_node(state: TenderLabState) -> TenderLabState:
    checks = scan_policy_checks(state["payload"])
    gaps = sum(item.status == "GAP" for item in checks)
    remediation_count = sum(item.remediation is not None for item in checks)
    return {
        "policy_checks": checks,
        "trace": _append_trace(
            state,
            step_id="CONTROL_SCAN",
            label="Match tender controls to the draft",
            detail=(
                f"Found {len(checks)} tender-triggered control check(s), including {gaps} text gap(s), "
                f"and prepared {remediation_count} evidence-gated response scaffold(s)."
            ),
        ),
    }


def _clarification_node(state: TenderLabState) -> TenderLabState:
    questions = draft_clarifications(state["payload"])
    return {
        "clarification_questions": questions,
        "trace": _append_trace(
            state,
            step_id="CLARIFY",
            label="Identify assumptions that need clarification",
            detail=(
                f"Prepared {len(questions)} editable, source-linked clarification draft(s)."
                if questions
                else "No configured ambiguity marker was detected; manual source review still applies."
            ),
        ),
    }


def _milestone_node(state: TenderLabState) -> TenderLabState:
    milestones = extract_milestones(state["payload"])
    return {
        "milestones": milestones,
        "calendar_ics": build_calendar_ics(state["payload"], milestones),
        "trace": _append_trace(
            state,
            step_id="MILESTONES",
            label="Extract dated milestones",
            detail=f"Extracted {len(milestones)} date(s) for review and local calendar export.",
        ),
    }


def _sme_node(state: TenderLabState) -> TenderLabState:
    pricing = analyse_pricing(state["payload"])
    return {
        "pricing": pricing,
        "startup_coach": None,
        "trace": _append_trace(
            state,
            step_id="COMMERCIAL",
            label="Run cost resilience scenarios",
            detail=(
                "Calculated margin and sensitivity from user-supplied values."
                if pricing
                else "Skipped because no pricing values were supplied."
            ),
            skipped=pricing is None,
        ),
    }


def _startup_node(state: TenderLabState) -> TenderLabState:
    coach = build_startup_coach(state["payload"], state["policy_checks"])
    return {
        "pricing": None,
        "startup_coach": coach,
        "trace": _append_trace(
            state,
            step_id="STARTUP_COACH",
            label="Build and critique a response outline",
            detail="Mapped founder answers into an evidence-aware first draft and rehearsal questions.",
        ),
    }


def _mode_route(state: TenderLabState) -> str:
    return "sme" if state["payload"].mode == "SME" else "startup"


def _strategy_node(state: TenderLabState) -> TenderLabState:
    routes = build_strategy_routes(
        state["payload"],
        state["policy_checks"],
        state["clarification_questions"],
    )
    return {
        "strategy_routes": routes,
        "trace": _append_trace(
            state,
            step_id="ROUTES",
            label="Compare participation routes",
            detail=(
                f"Generated {len(routes)} consequence-based route(s); no route was selected automatically."
            ),
        ),
    }


def _actions_node(state: TenderLabState) -> TenderLabState:
    actions = build_next_actions(
        state["policy_checks"],
        state["clarification_questions"],
        state["milestones"],
        state.get("pricing"),
        state["strategy_routes"],
        state.get("startup_coach"),
    )
    return {
        "next_actions": actions,
        "trace": _append_trace(
            state,
            step_id="PLAN",
            label="Order the next actions",
            detail=f"Prepared {len(actions)} reviewable action(s) without changing bid state.",
        ),
    }


def _build_graph():
    graph = StateGraph(TenderLabState)
    graph.add_node("brief", _brief_node)
    graph.add_node("policy", _policy_node)
    graph.add_node("clarify", _clarification_node)
    graph.add_node("milestones", _milestone_node)
    graph.add_node("sme", _sme_node)
    graph.add_node("startup", _startup_node)
    graph.add_node("strategy", _strategy_node)
    graph.add_node("actions", _actions_node)
    graph.add_edge(START, "brief")
    graph.add_edge("brief", "policy")
    graph.add_edge("policy", "clarify")
    graph.add_edge("clarify", "milestones")
    graph.add_conditional_edges("milestones", _mode_route, {"sme": "sme", "startup": "startup"})
    graph.add_edge("sme", "strategy")
    graph.add_edge("startup", "strategy")
    graph.add_edge("strategy", "actions")
    graph.add_edge("actions", END)
    return graph.compile()


TENDER_LAB_GRAPH = _build_graph()


def run_tender_lab(payload: TenderLabRequest) -> TenderLabResponse:
    """Run a deterministic, stateless decision-support workflow."""
    state = TENDER_LAB_GRAPH.invoke({"payload": payload, "trace": []})
    return TenderLabResponse(
        mode=payload.mode,
        source_type=payload.source_type,
        brief=state["brief"],
        policy_checks=state["policy_checks"],
        clarification_questions=state["clarification_questions"],
        milestones=state["milestones"],
        pricing=state.get("pricing"),
        strategy_routes=state["strategy_routes"],
        startup_coach=state.get("startup_coach"),
        next_actions=state["next_actions"],
        trace=state["trace"],
        calendar_ics=state["calendar_ics"],
        boundaries=[
            "This workspace is stateless: the analysis does not update the operational bid record.",
            "Inputs are user-supplied or synthetic; no live GeBIZ, ACRA, MOM or GovTech lookup is performed.",
            "A supported control means matching proposal text was found, not that official compliance is certified.",
            "Pricing is transparent sensitivity arithmetic, not a win probability or recommended bid price.",
            "Participation routes are simulations only; a human decides whether and how to proceed.",
        ],
    )
