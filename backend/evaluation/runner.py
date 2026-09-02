import argparse
import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.config import Settings, settings
from app.database import Base
from app.demo.seed import DEMO_BID_ID, seed_demo
from app.graph.workflow import build_corrigendum_graph
from app.llm.interpreter import (
    InterpretationFailure,
    InterpretationUnavailable,
    TenderInterpreter,
)
from app.llm.schemas import ChangeInterpretationEnvelope, StructuredRequirement
from app.rules import (
    ProcurementRuleFacts,
    RuleEvaluationInput,
    evaluate_requirement,
    evaluate_rule,
)
from app.rules.identity import document_name_key, qualification_code_key
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from evaluation.schema import (
    AccuracyMetric,
    CaseDiagnostics,
    CaseFailure,
    CaseResult,
    EvaluationCase,
    EvaluationReport,
    FieldDifference,
    RuleBindingDiagnostic,
)

EVALUATION_ROOT = Path(__file__).resolve().parent / "cases"
DEFAULT_REPORT = Path(__file__).resolve().parents[2] / "data" / "evaluation" / "latest_report.json"


def load_cases(partition: str) -> list[EvaluationCase]:
    aliases = {"evaluation": "regression", "blind-v2": "blind_v2"}
    selected = (
        [aliases.get(partition.lower(), partition.lower())]
        if partition != "all"
        else ["development", "regression", "blind"]
    )
    cases: list[EvaluationCase] = []
    for name in selected:
        for path in sorted((EVALUATION_ROOT / name).glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            records = payload if isinstance(payload, list) else [payload]
            cases.extend(EvaluationCase.model_validate(record) for record in records)
    return cases


def _actual_fields(requirement: StructuredRequirement) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "deadline": requirement.deadline.isoformat() if requirement.deadline else None,
        "minimum_count": requirement.minimum_count,
        "certification": requirement.certification,
        "compulsory": requirement.compulsory,
    }
    fields.update({item.name: item.value for item in requirement.structured_fields})
    return fields


def _differences(expected: dict[str, Any], actual: dict[str, Any]) -> list[FieldDifference]:
    return [
        FieldDifference(field=field, expected=value, actual=actual.get(field))
        for field, value in expected.items()
        if actual.get(field) != value
    ]


def _difference_summary(differences: list[FieldDifference]) -> str:
    return "; ".join(
        f"{item.field}: expected {item.expected!r}, got {item.actual!r}"
        for item in differences
    )


def _diagnostic_value(value: Any) -> Any:
    return value.model_dump(mode="json") if hasattr(value, "model_dump") else value


def _requirement_match_score(
    case: EvaluationCase, requirement: StructuredRequirement
) -> tuple[int, int, int]:
    """Choose the scored obligation without exposing ground truth to the model prompt."""
    actual_fields = _actual_fields(requirement)
    field_matches = sum(
        actual_fields.get(key) == value
        for key, value in case.expected.structured_fields.items()
    )
    return (
        int(requirement.requirement_type == case.expected.requirement_type),
        int(requirement.gate_type == case.expected.gate_type),
        field_matches,
    )


def _fact_sets(case: EvaluationCase) -> list[ProcurementRuleFacts]:
    facts = case.deterministic_facts
    if facts is None:
        return []
    return facts if isinstance(facts, list) else [facts]


def _binding_score(rule: Any, facts: ProcurementRuleFacts) -> int:
    """Prefer matching identifiers when several fact sets share a rule kind."""
    if str(rule.kind) == "QUALIFICATION":
        rule_keys = {qualification_code_key(option.code) for option in rule.options}
        fact_keys = {qualification_code_key(item.code) for item in facts.evidence}
        return len(rule_keys & fact_keys)
    if str(rule.kind) == "REQUIRED_DOCUMENT":
        rule_keys = {document_name_key(document) for document in rule.documents}
        fact_keys = {document_name_key(item.name) for item in facts.documents}
        return len(rule_keys & fact_keys)
    return 0


def _evaluate_interpreted_rules(
    case: EvaluationCase, requirements: list[StructuredRequirement]
) -> tuple[str, list[RuleBindingDiagnostic], str]:
    """Bind interpreted rules to registry facts, then run the rule evaluators."""
    available_facts = list(_fact_sets(case))
    evaluations: list[RuleEvaluationInput] = []
    bindings: list[RuleBindingDiagnostic] = []
    unmatched_rule = False
    for requirement in requirements:
        rule = requirement.procurement_rule
        if rule is None:
            unmatched_rule = True
            bindings.append(
                RuleBindingDiagnostic(
                    requirement_stable_key=requirement.stable_key,
                    rule_kind=None,
                    fact_kind=None,
                    binding_status="MISSING_RULE",
                    reason="The interpreted requirement did not include a typed procurement rule.",
                )
            )
            continue
        matching_indexes = [
            index
            for index, facts in enumerate(available_facts)
            if str(facts.kind) == str(rule.kind)
        ]
        matching_index = (
            max(
                matching_indexes,
                key=lambda index: _binding_score(rule, available_facts[index]),
            )
            if matching_indexes
            else None
        )
        if matching_index is None:
            unmatched_rule = True
            bindings.append(
                RuleBindingDiagnostic(
                    requirement_stable_key=requirement.stable_key,
                    rule_kind=str(rule.kind),
                    fact_kind=None,
                    binding_status="MISSING_FACT",
                    reason="No evaluator-side fact set matched the interpreted rule kind.",
                )
            )
            continue
        facts = available_facts.pop(matching_index)
        evaluation = RuleEvaluationInput(rule=rule, facts=facts)
        evaluations.append(evaluation)
        rule_result = evaluate_rule(evaluation, case.evaluation_as_of)
        bindings.append(
            RuleBindingDiagnostic(
                requirement_stable_key=requirement.stable_key,
                rule_kind=str(rule.kind),
                fact_kind=str(facts.kind),
                binding_status="MATCHED",
                evaluation_status=rule_result.status.value,
                recoverable=rule_result.recoverable,
                reason=rule_result.reason,
            )
        )

    for companion in case.companion_rules:
        evaluations.append(companion)
        rule_result = evaluate_rule(companion, case.evaluation_as_of)
        bindings.append(
            RuleBindingDiagnostic(
                requirement_stable_key=None,
                rule_kind=str(companion.rule.kind),
                fact_kind=str(companion.facts.kind),
                binding_status="MATCHED",
                evaluation_status=rule_result.status.value,
                recoverable=rule_result.recoverable,
                reason=f"Companion rule: {rule_result.reason}",
            )
        )
    for facts in available_facts:
        bindings.append(
            RuleBindingDiagnostic(
                requirement_stable_key=None,
                rule_kind=None,
                fact_kind=str(facts.kind),
                binding_status="UNUSED_FACT",
                reason="The model did not produce a rule for this evaluator-side fact set.",
            )
        )
    if not evaluations or unmatched_rule or available_facts:
        # Missing either a typed rule or authoritative bidder facts cannot safely
        # become a green operational result.
        return (
            "UNCERTAIN",
            bindings,
            "At least one interpreted rule or authoritative fact set could not be safely bound.",
        )
    result = evaluate_requirement(evaluations, case.evaluation_as_of)
    return result.operational_status.value, bindings, result.reason


def _source_matches_requirement(case: EvaluationCase, requirement: StructuredRequirement) -> bool:
    source = case.requirement_input
    return bool(
        source
        and requirement.source.document == source.document_name
        and requirement.source.page == source.page
        and requirement.source.section == source.section
        and requirement.source.snippet in source.text
    )


def _source_matches_change(case: EvaluationCase, envelope: ChangeInterpretationEnvelope) -> bool:
    source = case.change_input
    resulting = envelope.result.resulting_requirement
    if resulting is None:
        return True
    return bool(
        source
        and resulting.source.document == source.corrigendum_document
        and resulting.source.page == source.page
        and resulting.source.section == source.section
        and resulting.source.snippet in source.text
    )


class _ReplayInterpreter:
    def __init__(self, envelope: ChangeInterpretationEnvelope):
        self.envelope = envelope

    def interpret_change(self, *_: Any, **__: Any) -> ChangeInterpretationEnvelope:
        return self.envelope


def _run_hero_downstream(
    case: EvaluationCase, envelope: ChangeInterpretationEnvelope
) -> str:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    try:
        with factory() as session:
            seed_demo(session)
        workflow = build_corrigendum_graph(
            session_factory=factory,
            interpretation_service=_ReplayInterpreter(envelope),
            corrigendum_text=case.change_input.text,
        )
        state = workflow(
            {
                "session_id": f"evaluation-{uuid4().hex[:8]}",
                "tender_id": DEMO_BID_ID,
                "errors": [],
            }
        )
        return state["operational_status"]
    finally:
        engine.dispose()


def _metric(results: Iterable[CaseResult], field: str) -> AccuracyMetric:
    values = [getattr(item, field) for item in results]
    passed = values.count("PASS")
    failed = values.count("FAIL")
    not_run = values.count("NOT_RUN")
    not_applicable = values.count("NOT_APPLICABLE")
    denominator = passed + failed
    return AccuracyMetric(
        passed=passed,
        failed=failed,
        not_run=not_run,
        not_applicable=not_applicable,
        accuracy_percent=round(100 * passed / denominator, 2) if denominator else None,
    )


class EvaluationRunner:
    def __init__(
        self,
        interpreter: TenderInterpreter | None = None,
        app_settings: Settings = settings,
        *,
        require_live_model: bool = True,
    ):
        self.interpreter = interpreter or TenderInterpreter(app_settings=app_settings)
        self.settings = app_settings
        self.require_live_model = require_live_model

    def run(self, cases: list[EvaluationCase], partition: str) -> EvaluationReport:
        blockers: list[str] = []
        if self.require_live_model and not self.settings.interpretation_configured:
            blockers.append(
                f"Live {self.settings.llm_provider.title()} evaluation was not run: the selected "
                "provider's model and credential configuration are unavailable."
            )
        results: list[CaseResult] = []
        provider_blocked = bool(blockers)
        for case in cases:
            result = self._run_case(case, provider_blocked)
            results.append(result)
            if result.blocker:
                if result.blocker not in blockers:
                    blockers.append(result.blocker)
                provider_blocked = True
        failures = [
            {"case_id": result.id, **failure.model_dump()}
            for result in results
            for failure in result.failures
        ]
        unsafe_green_errors = [
            {
                "case_id": result.id,
                "expected": next(
                    case.expected.final_operational_state
                    for case in cases
                    if case.id == result.id
                ),
                "actual": "FEASIBLE",
            }
            for result in results
            if result.unsafe_green_error
        ]
        return EvaluationReport(
            generated_at=datetime.now(UTC),
            live_model_required=self.require_live_model,
            provider=self.settings.llm_provider,
            provider_configured=self.settings.interpretation_configured,
            model_id=self.settings.active_model_id,
            partition=partition,
            total_benchmark_cases=len(cases),
            requirement_interpretation_accuracy=_metric(
                results, "requirement_interpretation"
            ),
            corrigendum_matching_accuracy=_metric(results, "corrigendum_matching"),
            ambiguity_handling_accuracy=_metric(results, "ambiguity_handling"),
            final_operational_state_accuracy=_metric(results, "final_operational_state"),
            unsafe_green_errors=unsafe_green_errors,
            blockers=blockers,
            failures=failures,
            cases=results,
        )

    def _run_case(self, case: EvaluationCase, configuration_blocked: bool) -> CaseResult:
        requirement_status = "NOT_APPLICABLE" if case.kind == "CORRIGENDUM" else "NOT_RUN"
        change_status = "NOT_APPLICABLE" if case.kind == "REQUIREMENT" else "NOT_RUN"
        if configuration_blocked:
            return CaseResult(
                id=case.id,
                partition=case.partition,
                interpretation_mode="NOT_RUN",
                requirement_interpretation=requirement_status,
                corrigendum_matching=change_status,
                ambiguity_handling="NOT_RUN",
                final_operational_state="NOT_RUN",
                actual_operational_state=None,
                unsafe_green_error=False,
                blocker=None,
                failures=[],
            )

        failures: list[CaseFailure] = []
        diagnostics = CaseDiagnostics()
        actual_state: str | None = None
        interpreted_requirements: list[StructuredRequirement] = []
        try:
            if case.kind == "REQUIREMENT":
                envelope = self.interpreter.interpret_requirements(
                    case.requirement_input, allow_fallback=not self.require_live_model
                )
                missing_source = not case.requirement_input.text.strip()
                if (
                    self.require_live_model
                    and envelope.mode != self.settings.interpretation_mode
                    and not missing_source
                ):
                    raise InterpretationFailure(
                        "The selected live provider did not produce the interpretation result"
                    )
                requirements = envelope.result.requirements
                diagnostics.attempts = envelope.attempts
                diagnostics.duration_ms = envelope.duration_ms
                diagnostics.input_tokens = envelope.input_tokens
                diagnostics.output_tokens = envelope.output_tokens
                diagnostics.total_tokens = envelope.total_tokens
                diagnostics.candidate_count = len(requirements)
                requirement = (
                    max(requirements, key=lambda item: _requirement_match_score(case, item))
                    if requirements
                    else None
                )
                interpreted_requirements = requirements
                if requirement is None:
                    requirement_status = "FAIL"
                    failures.append(
                        CaseFailure(
                            category="extraction error",
                            stage="requirement interpretation",
                            detail="No structured requirement was returned.",
                        )
                    )
                    actual_ambiguity = None
                else:
                    actual_fields = _actual_fields(requirement)
                    expected_values = {
                        "requirement_type": case.expected.requirement_type,
                        "gate_type": case.expected.gate_type,
                        **case.expected.structured_fields,
                    }
                    actual_values = {
                        "requirement_type": requirement.requirement_type,
                        "gate_type": requirement.gate_type,
                        **actual_fields,
                    }
                    differences = _differences(expected_values, actual_values)
                    extraction_ok = not differences
                    provenance_ok = _source_matches_requirement(case, requirement)
                    diagnostics.selected_stable_key = requirement.stable_key
                    diagnostics.actual_requirement_type = requirement.requirement_type
                    diagnostics.actual_gate_type = requirement.gate_type
                    diagnostics.actual_structured_fields = actual_fields
                    diagnostics.actual_procurement_rule = (
                        requirement.procurement_rule.model_dump(mode="json")
                        if requirement.procurement_rule
                        else None
                    )
                    diagnostics.actual_interpretation_status = (
                        requirement.interpretation_status
                    )
                    diagnostics.source_provenance_match = provenance_ok
                    diagnostics.field_differences = differences
                    requirement_status = "PASS" if extraction_ok and provenance_ok else "FAIL"
                    if not extraction_ok:
                        failures.append(
                            CaseFailure(
                                category="extraction error",
                                stage="requirement interpretation",
                                detail=_difference_summary(differences),
                            )
                        )
                    if not provenance_ok:
                        failures.append(
                            CaseFailure(
                                category="source-provenance error",
                                stage="requirement interpretation",
                                detail="Document, page, section, or exact snippet did not match input.",
                            )
                        )
                    actual_ambiguity = requirement.interpretation_status
                mode = "DETERMINISTIC_SAFETY_GUARD" if missing_source else envelope.mode
                downstream_envelope = None
            else:
                envelope = self.interpreter.interpret_change(
                    case.change_input, allow_fallback=not self.require_live_model
                )
                missing_source = not case.change_input.text.strip()
                if (
                    self.require_live_model
                    and envelope.mode != self.settings.interpretation_mode
                    and not missing_source
                ):
                    raise InterpretationFailure(
                        "The selected live provider did not produce the interpretation result"
                    )
                result = envelope.result
                diagnostics.attempts = envelope.attempts
                diagnostics.duration_ms = envelope.duration_ms
                diagnostics.input_tokens = envelope.input_tokens
                diagnostics.output_tokens = envelope.output_tokens
                diagnostics.total_tokens = envelope.total_tokens
                diagnostics.deterministic_adapters = envelope.deterministic_adapters
                changed_values = {
                    item.field: _diagnostic_value(item.new_value)
                    for item in result.changed_fields
                }
                expected_values = {
                    "affected_requirement": case.expected.affected_requirement,
                    "change_type": case.expected.change_type,
                    **case.expected.structured_fields,
                }
                actual_values = {
                    "affected_requirement": result.affected_stable_key,
                    "change_type": result.change_type,
                    **changed_values,
                }
                differences = _differences(expected_values, actual_values)
                matching_ok = not differences
                provenance_ok = _source_matches_change(case, envelope)
                diagnostics.actual_affected_requirement = result.affected_stable_key
                diagnostics.actual_change_type = result.change_type
                diagnostics.actual_changed_fields = changed_values
                diagnostics.actual_interpretation_status = result.interpretation_status
                diagnostics.source_provenance_match = provenance_ok
                diagnostics.field_differences = differences
                resulting = result.resulting_requirement
                if resulting is not None:
                    diagnostics.selected_stable_key = resulting.stable_key
                    diagnostics.actual_requirement_type = resulting.requirement_type
                    diagnostics.actual_gate_type = resulting.gate_type
                    diagnostics.actual_structured_fields = _actual_fields(resulting)
                    diagnostics.actual_procurement_rule = (
                        resulting.procurement_rule.model_dump(mode="json")
                        if resulting.procurement_rule
                        else None
                    )
                change_status = "PASS" if matching_ok and provenance_ok else "FAIL"
                if not matching_ok:
                    failures.append(
                        CaseFailure(
                            category="semantic matching error",
                            stage="corrigendum matching",
                            detail=_difference_summary(differences),
                        )
                    )
                if not provenance_ok:
                    failures.append(
                        CaseFailure(
                            category="source-provenance error",
                            stage="corrigendum matching",
                            detail="Corrigendum source provenance did not match input.",
                        )
                    )
                actual_ambiguity = result.interpretation_status
                mode = "DETERMINISTIC_SAFETY_GUARD" if missing_source else envelope.mode
                downstream_envelope = envelope
                interpreted_requirements = (
                    [result.resulting_requirement] if result.resulting_requirement else []
                )

            ambiguity_status = (
                "PASS" if actual_ambiguity == case.expected.ambiguity_state else "FAIL"
            )
            if ambiguity_status == "FAIL":
                failures.append(
                    CaseFailure(
                        category="ambiguity handling error",
                        stage="ambiguity handling",
                        detail=(
                            f"Expected {case.expected.ambiguity_state}, got {actual_ambiguity}."
                        ),
                    )
                )

            if case.deterministic_scenario == "HERO_R17" and downstream_envelope is not None:
                try:
                    actual_state = _run_hero_downstream(case, downstream_envelope)
                    diagnostics.deterministic_reason = (
                        "The production R17 workflow replayed the validated change envelope."
                    )
                    final_status = (
                        "PASS"
                        if actual_state == case.expected.final_operational_state
                        else "FAIL"
                    )
                except Exception as exc:
                    final_status = "FAIL"
                    failures.append(
                        CaseFailure(
                            category="deterministic rule error",
                            stage="final operational state",
                            detail=f"Production workflow failed: {exc}",
                        )
                    )
            elif missing_source:
                actual_state = "UNCERTAIN"
                diagnostics.deterministic_reason = (
                    "Missing authoritative source text triggered the deterministic safety guard."
                )
                final_status = (
                    "PASS"
                    if actual_state == case.expected.final_operational_state
                    else "FAIL"
                )
            elif case.deterministic_facts is not None:
                (
                    actual_state,
                    diagnostics.rule_bindings,
                    diagnostics.deterministic_reason,
                ) = _evaluate_interpreted_rules(case, interpreted_requirements)
                final_status = (
                    "PASS"
                    if actual_state == case.expected.final_operational_state
                    else "FAIL"
                )
            else:
                final_status = "NOT_RUN"
            if final_status == "FAIL" and actual_state is not None:
                category = (
                    "deadline error"
                    if case.expected.requirement_type == "DEADLINE"
                    else "deterministic rule error"
                )
                failures.append(
                    CaseFailure(
                        category=category,
                        stage="final operational state",
                        detail=(
                            f"Expected {case.expected.final_operational_state}, got {actual_state}. "
                            f"{diagnostics.deterministic_reason or ''}"
                        ),
                    )
                )
            unsafe_green = (
                case.expected.final_operational_state in {"BLOCKED", "UNCERTAIN"}
                and actual_state == "FEASIBLE"
            )
            return CaseResult(
                id=case.id,
                partition=case.partition,
                interpretation_mode=mode,
                requirement_interpretation=requirement_status,
                corrigendum_matching=change_status,
                ambiguity_handling=ambiguity_status,
                final_operational_state=final_status,
                actual_operational_state=actual_state,
                unsafe_green_error=unsafe_green,
                blocker=None,
                failures=failures,
                diagnostics=diagnostics,
            )
        except InterpretationUnavailable as exc:
            return CaseResult(
                id=case.id,
                partition=case.partition,
                interpretation_mode="NOT_RUN",
                requirement_interpretation=(
                    "NOT_RUN" if case.kind == "REQUIREMENT" else "NOT_APPLICABLE"
                ),
                corrigendum_matching=(
                    "NOT_RUN" if case.kind == "CORRIGENDUM" else "NOT_APPLICABLE"
                ),
                ambiguity_handling="NOT_RUN",
                final_operational_state="NOT_RUN",
                actual_operational_state=None,
                unsafe_green_error=False,
                blocker=f"Live {self.settings.llm_provider.title()} evaluation was not run: {exc}",
                failures=[],
                diagnostics=diagnostics,
            )
        except InterpretationFailure as exc:
            applicable = "requirement interpretation" if case.kind == "REQUIREMENT" else "corrigendum matching"
            failures.append(
                CaseFailure(
                    category=(
                        "extraction error"
                        if case.kind == "REQUIREMENT"
                        else "semantic matching error"
                    ),
                    stage=applicable,
                    detail=str(exc),
                )
            )
            return CaseResult(
                id=case.id,
                partition=case.partition,
                interpretation_mode="ERROR",
                requirement_interpretation=(
                    "FAIL" if case.kind == "REQUIREMENT" else "NOT_APPLICABLE"
                ),
                corrigendum_matching=(
                    "FAIL" if case.kind == "CORRIGENDUM" else "NOT_APPLICABLE"
                ),
                ambiguity_handling="FAIL",
                final_operational_state="NOT_RUN",
                actual_operational_state=None,
                unsafe_green_error=False,
                blocker=None,
                failures=failures,
                diagnostics=diagnostics,
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run isolated live-model interpretation evaluation")
    parser.add_argument(
        "--partition",
        choices=["development", "regression", "blind", "blind-v2", "evaluation", "all"],
        default="regression",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    cases = load_cases(args.partition)
    report = EvaluationRunner().run(cases, args.partition)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    print(report.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
