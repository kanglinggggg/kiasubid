import json

import pytest
from app.config import Settings
from app.llm.provider import InvocationMetrics
from app.tender_lab.engine import scan_policy_checks
from app.tender_lab.proposal_builder import (
    ProposalAnswerReviewRequest,
    ProposalDraftRequest,
    ProposalPlanRequest,
    _fallback_draft,
    _validate_draft_content,
    build_proposal_plan,
    generate_proposal_draft,
    review_proposal_answer,
)
from app.tender_lab.sample import sample_request
from app.tender_lab.schemas import StartupAnswers


def _offline_settings() -> Settings:
    return Settings(
        _env_file=None,
        llm_provider="bedrock",
        bedrock_model_id=None,
        aws_access_key_id=None,
        aws_secret_access_key=None,
        aws_session_token=None,
    )


class SingleOutputClient:
    mode = "BEDROCK"
    model_id = "test.proposal-model-v1"

    def __init__(self, output: dict):
        self.output = output
        self.last_invocation: InvocationMetrics | None = None

    def generate_json(self, *, system: str, prompt: str, schema: dict, schema_name: str) -> str:
        self.last_invocation = InvocationMetrics(
            duration_ms=1,
            input_tokens=10,
            output_tokens=10,
            total_tokens=20,
        )
        return json.dumps(self.output)


def test_proposal_plan_covers_core_founder_questions() -> None:
    tender = sample_request("STARTUP")

    result = build_proposal_plan(ProposalPlanRequest(tender=tender))

    assert len(result.questions) == 8
    assert {question.answer_key for question in result.questions if question.required} == {
        "solution_summary",
        "technical_architecture",
        "delivery_approach",
        "operations_maintenance",
        "security_approach",
        "risk_management",
        "team_strength",
    }
    assert all(question.context_refs for question in result.questions)
    assert "do not confirm" in result.boundary


def test_proposal_mentor_continues_with_visible_fallback() -> None:
    tender = sample_request("STARTUP")
    response = review_proposal_answer(
        ProposalAnswerReviewRequest(
            tender=tender,
            question_id="Q-DELIVERY",
            answer="We will build it quickly.",
        ),
        app_settings=_offline_settings(),
    )

    assert response.provider_state == "FALLBACK"
    assert response.execution.mode == "DETERMINISTIC_FALLBACK"
    assert response.critique.verdict == "NEEDS_DETAIL"
    assert response.critique.needs_follow_up is True
    assert response.fallback_reason
    assert response.critique.formalized_answer != "We will build it quickly."
    assert "Recorded founder response" in response.critique.formalized_answer
    assert "Evidence check before use" in response.critique.formalized_answer


def test_proposal_mentor_flags_unsafe_certainty() -> None:
    tender = sample_request("STARTUP")
    response = review_proposal_answer(
        ProposalAnswerReviewRequest(
            tender=tender,
            question_id="Q-SECURITY",
            answer=(
                "We are fully compliant and guarantee zero risk. An access-control report will "
                "be reviewed by the security owner."
            ),
        ),
        app_settings=_offline_settings(),
    )

    assert response.critique.verdict == "RISKY_CLAIM"
    assert response.critique.unsupported_claims
    assert "unsafe certainty" in response.critique.mentor_feedback


def test_grounded_draft_uses_recorded_answers_and_lists_open_items() -> None:
    tender = sample_request("STARTUP")
    response = generate_proposal_draft(
        ProposalDraftRequest(tender=tender),
        app_settings=_offline_settings(),
    )

    assert response.provider_state == "FALLBACK"
    assert len(response.sections) == 7
    assert tender.startup_answers is not None
    assert tender.startup_answers.solution_summary in response.markdown
    assert "Technical Architecture" in response.markdown
    assert "Operations and Maintenance" in response.markdown
    assert "Risk Management" in response.markdown
    assert "Open Items for Human Review" in response.markdown
    assert response.open_items
    assert "does not establish compliance" in response.boundary


def test_grounded_draft_requires_every_core_answer() -> None:
    tender = sample_request("STARTUP")
    assert tender.startup_answers is not None
    tender.startup_answers.security_approach = ""

    with pytest.raises(ValueError, match="Security and Privacy"):
        generate_proposal_draft(
            ProposalDraftRequest(tender=tender),
            app_settings=_offline_settings(),
        )


def test_generated_open_items_do_not_become_compliance_evidence() -> None:
    tender = sample_request("STARTUP")
    draft = generate_proposal_draft(
        ProposalDraftRequest(tender=tender),
        app_settings=_offline_settings(),
    )
    tender.proposal_text = draft.markdown

    checks = {item.id: item for item in scan_policy_checks(tender)}

    assert "Open Items for Human Review" in draft.markdown
    assert checks["CTRL-MFA"].status == "GAP"
    assert checks["CTRL-MFA"].proposal_evidence is None


def test_live_mentor_rejects_an_invented_nonnumeric_technology() -> None:
    tender = sample_request("STARTUP")
    answer = "We give operators one shared portal with an acceptance test report."
    output = {
        "question_id": "Q-SOLUTION",
        "verdict": "STRONG",
        "mentor_feedback": "Ready.",
        "strengths": ["The outcome is clear."],
        "gaps": [],
        "evidence_needed": ["Acceptance test report"],
        "unsupported_claims": [],
        "formalized_answer": answer + " The platform uses Kubernetes.",
        "answer_quotes": [answer],
        "needs_follow_up": False,
        "follow_up_question": None,
    }
    configured = Settings(
        _env_file=None,
        llm_provider="bedrock",
        bedrock_model_id="test.proposal-model-v1",
        llm_max_retries=0,
    )

    response = review_proposal_answer(
        ProposalAnswerReviewRequest(
            tender=tender,
            question_id="Q-SOLUTION",
            answer=answer,
        ),
        app_settings=configured,
        client_factory=lambda _: SingleOutputClient(output),
    )

    assert response.provider_state == "FALLBACK"
    assert "Kubernetes" not in response.critique.formalized_answer


def test_live_draft_validator_rejects_an_unrecorded_capability() -> None:
    tender = sample_request("STARTUP")
    assert tender.startup_answers is not None
    content = _fallback_draft(tender)
    content.sections[0].text += " The platform uses Kubernetes."
    answers = {
        key: getattr(tender.startup_answers, key)
        for key in StartupAnswers.model_fields
    }

    with pytest.raises(ValueError, match="factual vocabulary"):
        _validate_draft_content(content, tender=tender, answers=answers)
