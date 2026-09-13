import json
from collections.abc import Iterable

from app.config import Settings
from app.llm.provider import InvocationMetrics, ModelUnavailable
from app.main import app
from app.tender_lab.agent_loop import run_agent_loop
from app.tender_lab.agent_models import AgentLoopRequest
from app.tender_lab.sample import sample_request
from fastapi.testclient import TestClient


class SequenceClient:
    mode = "BEDROCK"
    model_id = "test.agent-model-v1"

    def __init__(self, outputs: Iterable[dict | str | Exception]):
        self.outputs = list(outputs)
        self.prompts: list[str] = []
        self.last_invocation: InvocationMetrics | None = None

    def generate_json(self, *, system: str, prompt: str, schema: dict, schema_name: str) -> str:
        self.prompts.append(prompt)
        if not self.outputs:
            raise AssertionError(f"unexpected model call for {schema_name}")
        output = self.outputs.pop(0)
        self.last_invocation = InvocationMetrics(
            duration_ms=12.5,
            input_tokens=100,
            output_tokens=40,
            total_tokens=140,
        )
        if isinstance(output, Exception):
            raise output
        return output if isinstance(output, str) else json.dumps(output)


def _settings() -> Settings:
    return Settings(llm_max_retries=0)


def _request(*, max_revision_rounds: int = 1) -> AgentLoopRequest:
    tender = sample_request("SME").model_copy(
        update={
            "tender_text": (
                "[Page 1]\nThe supplier must provide MFA for 100 users, submission closes on "
                "20 September 2026 at 12:00 SGT, and the scope, service level, price and volume "
                "are stated."
            ),
            "proposal_text": (
                "[Page 2]\nThe proposed service provides MFA for administrator access and supports "
                "100 users."
            ),
        }
    )
    return AgentLoopRequest(tender=tender, max_revision_rounds=max_revision_rounds)


def _plan() -> dict:
    return {
        "mission": "Prepare an evidence-grounded review for a human decision.",
        "tasks": [
            {
                "agent": "COMPLIANCE",
                "objective": "Compare mandatory wording with proposal evidence.",
                "focus": ["mandatory controls"],
            },
            {
                "agent": "COMMERCIAL",
                "objective": "Test the supplied commercial assumptions.",
                "focus": ["cost", "scope"],
            },
            {
                "agent": "TIMELINE",
                "objective": "Extract explicit dates and dependencies.",
                "focus": ["submission"],
            },
        ],
        "success_criteria": ["Every finding cites evidence."],
    }


def _specialist(
    agent: str,
    finding_id: str,
    evidence_ids: list[str],
    *,
    claim: str,
) -> dict:
    return {
        "agent": agent,
        "summary": f"{agent.title()} review completed.",
        "findings": [
            {
                "id": finding_id,
                "title": f"{agent.title()} evidence",
                "status": "SUPPORTED",
                "severity": "INFO",
                "claim": claim,
                "evidence_ids": evidence_ids,
                "evidence_gap": None,
                "downstream_effects": [],
                "recommended_action": "An authorised reviewer should verify the cited source.",
                "confidence": "HIGH",
            }
        ],
        "assumptions": [],
        "handoff": "Send the evidence-linked result to the Critic.",
    }


def _compliance(*, claim: str = "The tender asks for MFA and the proposal states MFA support.") -> dict:
    return _specialist(
        "COMPLIANCE",
        "CMP-001",
        ["TENDER-001", "PROPOSAL-001"],
        claim=claim,
    )


def _commercial() -> dict:
    return _specialist(
        "COMMERCIAL",
        "COM-001",
        ["FACT-PRICING-INPUTS"],
        claim="The workspace contains an estimated cost, proposed price and five comparables.",
    )


def _timeline() -> dict:
    return _specialist(
        "TIMELINE",
        "TIM-001",
        ["TENDER-001"],
        claim="The tender text states a submission close on 20 September 2026 at 12:00 SGT.",
    )


def _critic(*, revise_compliance: bool = False) -> dict:
    return {
        "overall_verdict": "REVISE" if revise_compliance else "PASS",
        "finding_reviews": [
            {
                "finding_id": "CMP-001",
                "verdict": "REVISE" if revise_compliance else "PASS",
                "feedback": (
                    "Limit the claim to what the two excerpts explicitly state."
                    if revise_compliance
                    else "The claim is bounded by the cited tender and proposal excerpts."
                ),
            },
            {
                "finding_id": "COM-001",
                "verdict": "PASS",
                "feedback": "The claim only describes supplied pricing inputs.",
            },
            {
                "finding_id": "TIM-001",
                "verdict": "PASS",
                "feedback": "The date and timezone appear in the cited tender excerpt.",
            },
        ],
        "cross_agent_conflicts": [],
        "human_checks": ["Confirm the source pack before relying on the findings."],
    }


def test_live_agent_loop_runs_planner_specialists_critic_and_human_gate():
    client = SequenceClient([_plan(), _compliance(), _commercial(), _timeline(), _critic()])

    result = run_agent_loop(_request(), client=client, app_settings=_settings())

    assert result.provider_state == "LIVE"
    assert result.model_id == client.model_id
    assert result.loop_iterations == 1
    assert [item.agent for item in result.specialists] == [
        "COMPLIANCE",
        "COMMERCIAL",
        "TIMELINE",
    ]
    assert [item.agent_id for item in result.executions] == [
        "PLANNER",
        "COMPLIANCE",
        "COMMERCIAL",
        "TIMELINE",
        "CRITIC",
    ]
    assert all(item.mode == "BEDROCK" for item in result.executions)
    assert result.critic.overall_verdict == "PASS"
    assert result.decision.readiness == "READY_FOR_HUMAN_REVIEW"
    assert result.decision.grounded_finding_ids == ["CMP-001", "COM-001", "TIM-001"]
    assert result.fallback_reasons == []
    assert len(client.prompts) == 5


def test_missing_specialist_display_title_is_derived_without_changing_the_finding():
    compliance = _compliance()
    original_claim = compliance["findings"][0]["claim"]
    compliance["findings"][0].pop("title")
    compliance["handoff"] = ""
    client = SequenceClient([_plan(), compliance, _commercial(), _timeline(), _critic()])

    result = run_agent_loop(_request(), client=client, app_settings=_settings())

    finding = result.specialists[0].output.findings[0]
    assert result.provider_state == "LIVE"
    assert finding.title == original_claim
    assert finding.status == "SUPPORTED"
    assert finding.evidence_ids == ["TENDER-001", "PROPOSAL-001"]
    assert result.specialists[0].output.handoff.startswith("Send the evidence-linked")
    assert len(client.prompts) == 5


def test_recoverable_specialist_alias_remains_a_gap():
    commercial = _commercial()
    commercial["findings"][0]["status"] = "RECOVERABLE"
    commercial["findings"][0]["evidence_gap"] = "The commercial assumption needs human review."
    client = SequenceClient([_plan(), _compliance(), commercial, _timeline(), _critic()])

    result = run_agent_loop(_request(), client=client, app_settings=_settings())

    finding = result.specialists[1].output.findings[0]
    assert result.provider_state == "LIVE"
    assert finding.status == "GAP"
    assert finding.evidence_ids == ["FACT-PRICING-INPUTS"]
    assert len(client.prompts) == 5


def test_critic_can_trigger_one_bounded_revision_with_stable_finding_ids():
    revised_compliance = _compliance(
        claim="The tender states an MFA obligation and the proposal states MFA support."
    )
    client = SequenceClient(
        [
            _plan(),
            _compliance(claim="MFA appears in both supplied documents."),
            _commercial(),
            _timeline(),
            _critic(revise_compliance=True),
            revised_compliance,
            _critic(),
        ]
    )

    result = run_agent_loop(_request(), client=client, app_settings=_settings())

    assert result.provider_state == "LIVE"
    assert result.loop_iterations == 2
    compliance = next(item for item in result.specialists if item.agent == "COMPLIANCE")
    assert compliance.revision_count == 1
    assert compliance.output.findings[0].id == "CMP-001"
    compliance_execution = next(
        item for item in result.executions if item.agent_id == "COMPLIANCE"
    )
    assert compliance_execution.status == "REVISED"
    assert compliance_execution.revision_count == 1
    assert compliance_execution.attempts == 2
    assert "Limit the claim" in client.prompts[5]
    assert "Preserve exactly these finding IDs" in client.prompts[5]
    assert "CMP-001" in client.prompts[5]
    assert result.critic.overall_verdict == "PASS"


def test_model_unavailability_fails_closed_to_visible_deterministic_fallback():
    client = SequenceClient([ModelUnavailable("provider offline")])

    result = run_agent_loop(_request(), client=client, app_settings=_settings())

    assert result.provider_state == "FALLBACK"
    assert all(item.mode == "DETERMINISTIC_FALLBACK" for item in result.executions)
    assert all(item.status == "FALLBACK" for item in result.executions)
    assert result.fallback_reasons == ["Planner: provider offline"]
    # A proposed service is a future commitment, not established implementation evidence.
    assert result.decision.readiness == "NEEDS_EVIDENCE"
    assert "Agent consensus is not bid approval" in result.decision.boundary
    assert len(client.prompts) == 1


def test_provider_credentials_are_not_exposed_in_fallback_reason():
    client = SequenceClient([
        ModelUnavailable(
            "Bedrock Converse failed: ExpiredTokenException: security token SECRET-VALUE"
        )
    ])

    result = run_agent_loop(_request(), client=client, app_settings=_settings())

    assert result.fallback_reasons == [
        "Planner: The configured language-model provider is unavailable."
    ]
    assert "SECRET-VALUE" not in str(result.model_dump())


def test_deterministic_guard_overrides_a_critic_that_passes_a_prohibited_claim():
    client = SequenceClient(
        [
            _plan(),
            _compliance(claim="The proposal is fully compliant with the tender."),
            _commercial(),
            _timeline(),
            _critic(),
        ]
    )

    result = run_agent_loop(
        _request(max_revision_rounds=0), client=client, app_settings=_settings()
    )

    review = next(item for item in result.critic.finding_reviews if item.finding_id == "CMP-001")
    assert review.verdict == "REVISE"
    assert "Guardrail" in review.feedback
    assert result.critic.overall_verdict == "REVISE"
    assert result.decision.readiness == "NEEDS_EVIDENCE"
    assert "CMP-001" in result.decision.unresolved_finding_ids


def test_sparse_workspace_cannot_return_an_empty_ready_review():
    tender = sample_request("STARTUP").model_copy(
        update={
            "tender_text": (
                "[Page 1]\nThis document contains general background information for interested "
                "suppliers without a detailed schedule."
            ),
            "proposal_text": "",
        }
    )
    request = AgentLoopRequest(tender=tender, max_revision_rounds=1)

    result = run_agent_loop(
        request,
        client=SequenceClient([ModelUnavailable("provider offline")]),
        app_settings=_settings(),
    )

    assert all(item.output.findings for item in result.specialists)
    assert result.decision.readiness in {"HOLD", "NEEDS_EVIDENCE"}
    assert result.decision.unresolved_finding_ids


def test_agent_loop_endpoint_accepts_the_nested_tender_envelope(monkeypatch):
    request = _request()
    expected = run_agent_loop(
        request,
        client=SequenceClient([ModelUnavailable("provider offline")]),
        app_settings=_settings(),
    )
    monkeypatch.setattr("app.main.run_agent_loop", lambda payload: expected)

    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/tender-lab/agent-loop",
            json=request.model_dump(mode="json"),
        )

    assert response.status_code == 200, response.text
    assert response.json()["provider_state"] == "FALLBACK"
    assert response.json()["decision"]["boundary"].startswith("Agent consensus")
