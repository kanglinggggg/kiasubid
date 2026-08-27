import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from app.config import Settings, settings
from app.rules import evaluate_requirement

from evaluation.rule_schema import (
    BenchmarkAccuracy,
    RuleBenchmarkCase,
    RuleBenchmarkCaseResult,
    RuleBenchmarkReport,
)

RULE_CASE_ROOT = Path(__file__).resolve().parent / "rule_cases"
DEFAULT_REPORT = (
    Path(__file__).resolve().parents[2] / "data" / "evaluation" / "deterministic_report.json"
)


def load_rule_benchmark_cases() -> list[RuleBenchmarkCase]:
    cases: list[RuleBenchmarkCase] = []
    for path in sorted(RULE_CASE_ROOT.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        records = payload if isinstance(payload, list) else [payload]
        cases.extend(RuleBenchmarkCase.model_validate(record) for record in records)
    if not cases:
        raise RuntimeError(f"No rule benchmark cases found in {RULE_CASE_ROOT}")
    return cases


def _accuracy(results: list[RuleBenchmarkCaseResult], field: str) -> BenchmarkAccuracy:
    values = [getattr(result, field) for result in results]
    passed = values.count("PASS")
    failed = values.count("FAIL")
    unsupported = values.count("UNSUPPORTED")
    denominator = passed + failed
    return BenchmarkAccuracy(
        passed=passed,
        failed=failed,
        unsupported=unsupported,
        accuracy_percent=round(100 * passed / denominator, 2) if denominator else None,
    )


def run_rule_benchmark(
    cases: list[RuleBenchmarkCase], app_settings: Settings = settings
) -> RuleBenchmarkReport:
    results: list[RuleBenchmarkCaseResult] = []
    unsupported_cases: list[dict[str, str]] = []
    failures: list[dict[str, str]] = []
    for case in cases:
        if case.unsupported_reason is not None:
            unsupported_cases.append({"case_id": case.id, "reason": case.unsupported_reason})
            results.append(
                RuleBenchmarkCaseResult(
                    id=case.id,
                    requirement_result="UNSUPPORTED",
                    operational_status="UNSUPPORTED",
                    actual_requirement_result=None,
                    actual_operational_status=None,
                    actual_prior_operational_status=None,
                    failure_category=None,
                    failure_detail=None,
                )
            )
            continue

        actual = evaluate_requirement(case.rules, case.evaluation_as_of)
        prior = (
            evaluate_requirement(case.prior_rules, case.evaluation_as_of)
            if case.prior_rules
            else None
        )
        requirement_pass = actual.requirement_status == case.expected.requirement_result
        operational_pass = actual.operational_status == case.expected.operational_status and (
            case.expected.prior_operational_status is None
            or (prior is not None and prior.operational_status == case.expected.prior_operational_status)
        )
        detail_parts: list[str] = []
        if not requirement_pass:
            detail_parts.append(
                f"requirement expected {case.expected.requirement_result}, "
                f"got {actual.requirement_status}"
            )
        if actual.operational_status != case.expected.operational_status:
            detail_parts.append(
                f"status expected {case.expected.operational_status}, "
                f"got {actual.operational_status}"
            )
        if case.expected.prior_operational_status is not None and (
            prior is None or prior.operational_status != case.expected.prior_operational_status
        ):
            detail_parts.append(
                f"prior status expected {case.expected.prior_operational_status}, "
                f"got {prior.operational_status if prior else None}"
            )
        failure_detail = "; ".join(detail_parts) or None
        failure_category = None
        if failure_detail:
            failure_category = (
                "deadline error" if any(item.rule.kind == "PROCESSING_WINDOW" for item in case.rules)
                else "deterministic rule error"
            )
            failures.append(
                {"case_id": case.id, "category": failure_category, "detail": failure_detail}
            )
        results.append(
            RuleBenchmarkCaseResult(
                id=case.id,
                requirement_result="PASS" if requirement_pass else "FAIL",
                operational_status="PASS" if operational_pass else "FAIL",
                actual_requirement_result=actual.requirement_status,
                actual_operational_status=actual.operational_status,
                actual_prior_operational_status=prior.operational_status if prior else None,
                failure_category=failure_category,
                failure_detail=failure_detail,
            )
        )

    interpretation_reason = (
        f"Interpretation was not run because {app_settings.llm_provider} model or credential "
        "configuration is unavailable."
        if not app_settings.interpretation_configured
        else "Interpretation was not run in the deterministic-only benchmark pass."
    )
    return RuleBenchmarkReport(
        generated_at=datetime.now(UTC),
        source="GeBIZ_Agent_Test_Cases_FINAL_v3.docx",
        total_benchmark_cases=len(cases),
        interpretation_status="NOT_RUN",
        interpretation_reason=interpretation_reason,
        deterministic_requirement_result_accuracy=_accuracy(results, "requirement_result"),
        overall_bid_status_accuracy=_accuracy(results, "operational_status"),
        unsupported_cases=unsupported_cases,
        failures=failures,
        cases=results,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run deterministic procurement-rule evaluation")
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    report = run_rule_benchmark(load_rule_benchmark_cases())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    print(report.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
