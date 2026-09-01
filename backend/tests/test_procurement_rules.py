from datetime import datetime
from types import SimpleNamespace

import pytest
from app.config import Settings
from app.enums import AssessmentStatus
from app.rules import RuleEvaluationInput, RuleKind, evaluate_requirement
from app.services.assessment import assess_requirement
from evaluation.rule_runner import load_rule_benchmark_cases, run_rule_benchmark
from pydantic import ValidationError


def test_v3_benchmark_uses_every_generic_rule_type_and_preserves_nine_cases():
    cases = load_rule_benchmark_cases()
    kinds = {item.rule.kind for case in cases for item in [*case.rules, *case.prior_rules]}
    assert len(cases) == 9
    assert {case.source_case_id for case in cases} == {str(value) for value in range(1, 10)}
    assert kinds == set(RuleKind)


def test_deterministic_v3_report_is_separate_from_unavailable_interpretation():
    report = run_rule_benchmark(
        load_rule_benchmark_cases(),
        Settings(bedrock_model_id=None, aws_profile=None),
    )
    assert report.interpretation_status == "NOT_RUN"
    assert "bedrock model or credential configuration is unavailable" in report.interpretation_reason
    assert report.deterministic_requirement_result_accuracy.accuracy_percent == 100
    assert report.overall_bid_status_accuracy.accuracy_percent == 100
    assert report.unsupported_cases == []
    assert report.failures == []


def test_deadline_corrigendum_changes_blocked_path_to_recoverable():
    case = next(
        item
        for item in load_rule_benchmark_cases()
        if item.id == "external-09-deposit-deadline-corrigendum"
    )
    before = evaluate_requirement(case.prior_rules, case.evaluation_as_of)
    after = evaluate_requirement(case.rules, case.evaluation_as_of)
    assert before.requirement_status == AssessmentStatus.UNMET
    assert before.operational_status == "BLOCKED"
    assert after.requirement_status == AssessmentStatus.UNMET
    assert after.operational_status == "RECOVERABLE"
    assert before.rule_results[0].projected_completion_at == after.rule_results[0].projected_completion_at


def test_rule_and_fact_types_cannot_be_cross_wired():
    with pytest.raises(ValidationError, match="cannot be evaluated"):
        RuleEvaluationInput.model_validate(
            {
                "rule": {
                    "kind": "EVENT_ATTENDANCE",
                    "event_name": "Briefing",
                    "compulsory": True,
                },
                "facts": {
                    "kind": "PARTICIPATION_RESTRICTION",
                    "eligible": True,
                    "can_become_eligible_before_deadline": False,
                },
            }
        )


def test_production_assessment_dispatches_generic_rules_from_typed_backend_state():
    requirement = SimpleNamespace(
        rule_config={
            "kind": "PARTICIPATION_RESTRICTION",
            "restriction": "Bidder must be invited",
            "compulsory": True,
            "facts": {
                "eligible": False,
                "can_become_eligible_before_deadline": False,
            },
            "evaluation_as_of": "2026-08-27T12:00:00+08:00",
        }
    )
    result = assess_requirement(None, requirement)
    assert result.status == AssessmentStatus.UNMET
    assert "does not satisfy" in result.reason


def test_missing_generic_fact_state_returns_uncertain_instead_of_guessing():
    requirement = SimpleNamespace(
        rule_config={
            "kind": "SOURCE_FRESHNESS",
            "source_name": "Current tender corpus",
            "latest_version_required": True,
        }
    )
    result = assess_requirement(None, requirement)
    assert result.status == AssessmentStatus.UNCERTAIN
    assert "no ambient time or missing fact was guessed" in result.reason


def test_processing_window_uses_authoritative_deadline_from_facts_when_clause_omits_it():
    evaluation = RuleEvaluationInput.model_validate(
        {
            "rule": {
                "kind": "PROCESSING_WINDOW",
                "action": "Obtain drawings clearance",
                "deadline": None,
                "minimum_processing_hours": 168,
                "compulsory": True,
            },
            "facts": {
                "kind": "PROCESSING_WINDOW",
                "completed": False,
                "can_complete": True,
                "governing_deadline": "2026-09-10T09:00:00+08:00",
                "earliest_start_at": "2026-09-01T09:00:00+08:00",
                "estimated_duration_hours": 168,
            },
        }
    )
    result = evaluate_requirement(
        [evaluation], datetime.fromisoformat("2026-09-01T09:00:00+08:00")
    )
    assert result.operational_status == "RECOVERABLE"


def test_processing_window_without_any_authoritative_deadline_is_uncertain():
    evaluation = RuleEvaluationInput.model_validate(
        {
            "rule": {
                "kind": "PROCESSING_WINDOW",
                "action": "Obtain drawings clearance",
                "deadline": None,
                "minimum_processing_hours": 168,
                "compulsory": True,
            },
            "facts": {
                "kind": "PROCESSING_WINDOW",
                "completed": False,
                "can_complete": True,
                "earliest_start_at": "2026-09-01T09:00:00+08:00",
                "estimated_duration_hours": 168,
            },
        }
    )
    result = evaluate_requirement(
        [evaluation], datetime.fromisoformat("2026-09-01T09:00:00+08:00")
    )
    assert result.operational_status == "UNCERTAIN"
