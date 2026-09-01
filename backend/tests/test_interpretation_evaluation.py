import json
from pathlib import Path

from app.config import Settings
from app.llm.interpreter import TenderInterpreter
from app.llm.provider import BedrockUnavailable
from app.llm.schemas import RequirementInterpretationRequest, RequirementSource
from evaluation.runner import EvaluationRunner, load_cases
from evaluation.schema import EvaluationCase


class FakeBedrockClient:
    model_id = "test.bedrock-model"

    def __init__(self, payload: dict):
        self.payload = payload
        self.last_call: dict[str, object] = {}

    def generate_json(self, **kwargs: object) -> str:
        self.last_call = kwargs
        return json.dumps(self.payload)


class UnavailableBedrockClient:
    model_id = "test.bedrock-model"
    mode = "BEDROCK"

    def generate_json(self, **_: object) -> str:
        raise BedrockUnavailable("temporary credentials expired")


def test_regression_development_and_blind_benchmarks_are_separate_and_validated():
    regression = load_cases("regression")
    development = load_cases("development")
    blind = load_cases("blind")
    assert len(regression) == 9
    assert len(development) == 8
    assert len(blind) == 8
    assert all(case.partition == "REGRESSION" for case in regression)
    assert all(case.partition == "DEVELOPMENT" for case in development)
    assert all(case.partition == "BLIND" for case in blind)
    assert {case.source_case_id for case in regression} == {str(value) for value in range(1, 10)}
    assert {case.source_case_id for case in blind} == {f"U{value}" for value in range(1, 9)}
    for case in [*regression, *development, *blind]:
        expected = case.expected
        assert expected.ambiguity_state in {"INTERPRETED", "UNCERTAIN"}
        assert expected.final_operational_state in {
            "FEASIBLE",
            "RECOVERABLE",
            "BLOCKED",
            "UNCERTAIN",
        }
    template = Path(
        "backend/evaluation/cases/blind/CASE_TEMPLATE.json.example"
    )
    EvaluationCase.model_validate(json.loads(template.read_text(encoding="utf-8")))


def test_live_evaluation_reports_configuration_blocker_without_fallback_scores():
    app_settings = Settings(bedrock_model_id=None, aws_profile=None)
    cases = load_cases("regression")
    report = EvaluationRunner(app_settings=app_settings).run(cases, "regression")
    assert report.total_benchmark_cases == 9
    assert report.provider == "bedrock"
    assert report.provider_configured is False
    assert report.blockers
    assert report.requirement_interpretation_accuracy.accuracy_percent is None
    assert report.corrigendum_matching_accuracy.accuracy_percent is None
    assert report.ambiguity_handling_accuracy.accuracy_percent is None
    assert report.final_operational_state_accuracy.accuracy_percent is None
    assert all(case.interpretation_mode == "NOT_RUN" for case in report.cases)
    assert all(not case.failures for case in report.cases)
    assert report.unsafe_green_errors == []


def test_runtime_provider_failure_is_not_misreported_as_model_inaccuracy():
    app_settings = Settings(bedrock_model_id="test.bedrock-model")
    interpreter = TenderInterpreter(UnavailableBedrockClient(), app_settings)
    report = EvaluationRunner(interpreter, app_settings).run(
        load_cases("regression"), "regression"
    )
    assert report.blockers
    assert "temporary credentials expired" in report.blockers[0]
    assert report.requirement_interpretation_accuracy.accuracy_percent is None
    assert report.corrigendum_matching_accuracy.accuracy_percent is None
    assert report.ambiguity_handling_accuracy.accuracy_percent is None
    assert report.final_operational_state_accuracy.accuracy_percent is None
    assert report.failures == []


def test_missing_tender_text_returns_uncertain_without_model_invention():
    app_settings = Settings(bedrock_model_id="configured-but-not-called")
    result = TenderInterpreter(app_settings=app_settings).interpret_requirements(
        RequirementInterpretationRequest(
            document_name="missing.pdf",
            page=1,
            section="Unavailable",
            text="",
            stable_key_hint="MISSING-1",
        )
    )
    requirement = result.result.requirements[0]
    assert result.mode == "DEMO_FALLBACK"
    assert result.attempts == 0
    assert requirement.interpretation_status == "UNCERTAIN"
    assert requirement.minimum_count is None
    assert requirement.certification is None
    assert requirement.compulsory is None
    assert requirement.source.snippet == ""


def test_evaluator_separates_live_interpretation_from_hero_downstream_result():
    case = next(
        item for item in load_cases("development") if item.id == "development-r17-unseen-paraphrase"
    )
    existing = case.change_input.existing_requirement
    new_text = (
        "The Tenderer shall propose not fewer than four personnel holding valid CISSP "
        "certification."
    )
    resulting = existing.model_copy(
        update={
            "text": new_text,
            "minimum_count": 4,
            "source": RequirementSource(
                document=case.change_input.corrigendum_document,
                page=case.change_input.page,
                section=case.change_input.section,
                snippet=case.change_input.text,
            ),
        }
    )
    payload = {
        "change_type": "MODIFIED",
        "affected_stable_key": "R17",
        "changed_fields": [
            {"field": "text", "old_value": existing.text, "new_value": new_text},
            {"field": "minimum_count", "old_value": 3, "new_value": 4},
        ],
        "resulting_requirement": resulting.model_dump(mode="json"),
        "interpretation_status": "INTERPRETED",
        "uncertainty_reason": None,
        "reason_summary": "The staffing minimum increases from three to four.",
    }
    app_settings = Settings(bedrock_model_id="test.bedrock-model")
    interpreter = TenderInterpreter(FakeBedrockClient(payload), app_settings)
    report = EvaluationRunner(interpreter, app_settings).run([case], "development")
    assert report.corrigendum_matching_accuracy.accuracy_percent == 100
    assert report.ambiguity_handling_accuracy.accuracy_percent == 100
    assert report.final_operational_state_accuracy.accuracy_percent == 100
    assert report.cases[0].actual_operational_state == "RECOVERABLE"
    assert report.cases[0].failures == []


def _typed_requirement_record(
    case: EvaluationCase,
    *,
    text: str,
    requirement_type: str,
    gate_type: str,
    rule: dict,
    status: str = "INTERPRETED",
) -> dict:
    return {
        "stable_key": None,
        "text": text,
        "requirement_type": requirement_type,
        "gate_type": gate_type,
        "deadline": None,
        "minimum_count": None,
        "certification": None,
        "compulsory": rule.get("compulsory"),
        "procurement_rule": rule,
        "structured_fields": [],
        "interpretation_status": status,
        "uncertainty_reason": (
            "The source does not establish whether this registration is compulsory."
            if status == "UNCERTAIN"
            else None
        ),
        "source": {
            "document": case.requirement_input.document_name,
            "page": case.requirement_input.page,
            "section": case.requirement_input.section,
            "snippet": text,
        },
    }


def test_multi_obligation_interpretation_binds_only_external_facts_downstream():
    case = next(
        item
        for item in load_cases("regression")
        if item.id == "external-01-positive-public-gates"
    )
    parts = [part.strip().rstrip(".") + "." for part in case.requirement_input.text.split(". ")]
    payload = {
        "requirements": [
            _typed_requirement_record(
                case,
                text=parts[0],
                requirement_type="QUALIFICATION",
                gate_type="REQUIRED",
                rule={
                    "kind": "QUALIFICATION",
                    "options": [{"code": "CR11", "minimum_grade": "L2"}],
                    "match": "ANY",
                    "compulsory": True,
                },
            ),
            _typed_requirement_record(
                case,
                text=parts[1],
                requirement_type="ELIGIBILITY",
                gate_type="MANDATORY",
                rule={
                    "kind": "EVENT_ATTENDANCE",
                    "event_name": "Tender Briefing and Site Showround",
                    "compulsory": True,
                    "event_at": None,
                },
            ),
            _typed_requirement_record(
                case,
                text=parts[2],
                requirement_type="DOCUMENT",
                gate_type="MANDATORY",
                rule={
                    "kind": "REQUIRED_DOCUMENT",
                    "documents": ["Price attachment", "Technical attachment"],
                    "match": "ALL",
                    "compulsory": True,
                },
            ),
        ]
    }
    app_settings = Settings(bedrock_model_id="test.bedrock-model")
    report = EvaluationRunner(
        TenderInterpreter(FakeBedrockClient(payload), app_settings), app_settings
    ).run([case], "regression")
    assert report.requirement_interpretation_accuracy.accuracy_percent == 100
    assert report.final_operational_state_accuracy.accuracy_percent == 100
    assert report.cases[0].actual_operational_state == "FEASIBLE"


def test_processing_duration_combines_with_authoritative_deadline_downstream():
    case = next(
        item
        for item in load_cases("regression")
        if item.id == "external-03-clearance-remediation-window"
    )
    payload = {
        "requirements": [
            _typed_requirement_record(
                case,
                text=case.requirement_input.text,
                requirement_type="DOCUMENT",
                gate_type="MANDATORY",
                rule={
                    "kind": "PROCESSING_WINDOW",
                    "action": "Submit Clearance Form and obtain drawings clearance",
                    "deadline": None,
                    "minimum_processing_hours": 672,
                    "compulsory": True,
                },
            )
        ]
    }
    app_settings = Settings(bedrock_model_id="test.bedrock-model")
    report = EvaluationRunner(
        TenderInterpreter(FakeBedrockClient(payload), app_settings), app_settings
    ).run([case], "regression")
    assert report.requirement_interpretation_accuracy.accuracy_percent == 100
    assert report.final_operational_state_accuracy.accuracy_percent == 100
    assert report.cases[0].actual_operational_state == "RECOVERABLE"


def test_unclear_criticality_is_forced_closed_by_typed_rule():
    case = next(
        item
        for item in load_cases("regression")
        if item.id == "external-07-gra-criticality-unclear"
    )
    payload = {
        "requirements": [
            _typed_requirement_record(
                case,
                text=case.requirement_input.text,
                requirement_type="COMPLIANCE",
                gate_type="INFORMATIONAL",
                rule={
                    "kind": "QUALIFICATION",
                    "options": [{"code": "EPU/FBV/10", "minimum_grade": None}],
                    "match": "ANY",
                    "compulsory": None,
                },
                status="UNCERTAIN",
            )
        ]
    }
    app_settings = Settings(bedrock_model_id="test.bedrock-model")
    report = EvaluationRunner(
        TenderInterpreter(FakeBedrockClient(payload), app_settings), app_settings
    ).run([case], "regression")
    assert report.requirement_interpretation_accuracy.accuracy_percent == 100
    assert report.ambiguity_handling_accuracy.accuracy_percent == 100
    assert report.final_operational_state_accuracy.accuracy_percent == 100
    assert report.cases[0].actual_operational_state == "UNCERTAIN"


def test_expected_answers_and_deterministic_facts_never_enter_model_prompt():
    case = next(
        item
        for item in load_cases("regression")
        if item.id == "external-06-shortlist-restriction"
    )
    payload = {
        "requirements": [
            _typed_requirement_record(
                case,
                text=case.requirement_input.text,
                requirement_type="ELIGIBILITY",
                gate_type="MANDATORY",
                rule={
                    "kind": "PARTICIPATION_RESTRICTION",
                    "restriction": case.requirement_input.text,
                    "compulsory": True,
                },
            )
        ]
    }
    app_settings = Settings(bedrock_model_id="test.bedrock-model")
    client = FakeBedrockClient(payload)
    EvaluationRunner(TenderInterpreter(client, app_settings), app_settings).run(
        [case], "regression"
    )
    prompt = str(client.last_call["prompt"])
    assert '"expected"' not in prompt
    assert "final_operational_state" not in prompt
    assert "can_become_eligible_before_deadline" not in prompt


def test_blind_evaluation_flags_unsafe_green_result():
    case = EvaluationCase.model_validate(
        {
            "id": "blind-safety-check",
            "partition": "BLIND",
            "source_case_id": "teammate-001",
            "title": "Participation restriction incorrectly interpreted as eligible",
            "description": "Harness-only safety metric exercise.",
            "source": "Test fixture",
            "evaluation_as_of": "2026-08-28T12:00:00+08:00",
            "kind": "REQUIREMENT",
            "requirement_input": {
                "document_name": "blind.pdf",
                "page": 1,
                "section": "Eligibility",
                "text": "Only shortlisted suppliers may participate.",
                "stable_key_hint": "BLIND-1",
            },
            "change_input": None,
            "deterministic_scenario": None,
            "deterministic_facts": {
                "kind": "PARTICIPATION_RESTRICTION",
                "eligible": True,
                "can_become_eligible_before_deadline": False,
            },
            "expected": {
                "requirement_type": "ELIGIBILITY",
                "gate_type": "MANDATORY",
                "structured_fields": {"compulsory": True},
                "ambiguity_state": "INTERPRETED",
                "affected_requirement": None,
                "change_type": None,
                "final_operational_state": "BLOCKED",
            },
        }
    )
    payload = {
        "requirements": [
            {
                "stable_key": "BLIND-1",
                "text": "Only shortlisted suppliers may participate.",
                "requirement_type": "ELIGIBILITY",
                "gate_type": "MANDATORY",
                "deadline": None,
                "minimum_count": None,
                "certification": None,
                "compulsory": True,
                "procurement_rule": {
                    "kind": "PARTICIPATION_RESTRICTION",
                    "restriction": "Only shortlisted suppliers may participate.",
                    "compulsory": True,
                },
                "structured_fields": [],
                "interpretation_status": "INTERPRETED",
                "uncertainty_reason": None,
                "source": {
                    "document": "blind.pdf",
                    "page": 1,
                    "section": "Eligibility",
                    "snippet": "Only shortlisted suppliers may participate.",
                },
            }
        ]
    }
    app_settings = Settings(bedrock_model_id="test.bedrock-model")
    interpreter = TenderInterpreter(FakeBedrockClient(payload), app_settings)
    report = EvaluationRunner(interpreter, app_settings).run([case], "blind")

    assert report.final_operational_state_accuracy.accuracy_percent == 0
    assert report.cases[0].actual_operational_state == "FEASIBLE"
    assert report.cases[0].unsafe_green_error is True
    assert report.unsafe_green_errors == [
        {"case_id": "blind-safety-check", "expected": "BLOCKED", "actual": "FEASIBLE"}
    ]
