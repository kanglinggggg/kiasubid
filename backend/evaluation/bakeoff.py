import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from app.config import Settings

from evaluation.runner import EvaluationRunner, load_cases
from evaluation.schema import AccuracyMetric, EvaluationReport

DEFAULT_OUTPUT = Path(__file__).resolve().parents[2] / "data" / "evaluation" / "model_bakeoff"


def _metric(metric: AccuracyMetric) -> dict[str, int | float | None]:
    return metric.model_dump()


def summarize(report: EvaluationReport) -> dict[str, Any]:
    duration_ms = round(sum(case.diagnostics.duration_ms for case in report.cases), 2)
    token_values = [
        case.diagnostics.total_tokens
        for case in report.cases
        if case.diagnostics.total_tokens is not None
    ]
    categories = Counter(item["category"] for item in report.failures)
    return {
        "model_id": report.model_id,
        "partition": report.partition,
        "total_cases": report.total_benchmark_cases,
        "requirement_interpretation": _metric(report.requirement_interpretation_accuracy),
        "corrigendum_matching": _metric(report.corrigendum_matching_accuracy),
        "ambiguity_handling": _metric(report.ambiguity_handling_accuracy),
        "final_operational_state": _metric(report.final_operational_state_accuracy),
        "unsafe_green_errors": len(report.unsafe_green_errors),
        "failure_categories": dict(sorted(categories.items())),
        "failed_case_ids": sorted({item["case_id"] for item in report.failures}),
        "provider_duration_ms": duration_ms,
        "total_tokens": sum(token_values) if token_values else None,
        "blockers": report.blockers,
    }


def _rank(summary: dict[str, Any]) -> tuple[int, int, int, int, int, float]:
    requirement = summary["requirement_interpretation"]["passed"]
    corrigendum = summary["corrigendum_matching"]["passed"]
    return (
        -summary["unsafe_green_errors"],
        summary["final_operational_state"]["passed"],
        requirement + corrigendum,
        summary["ambiguity_handling"]["passed"],
        -(summary["total_tokens"] or 0),
        -summary["provider_duration_ms"],
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare Bedrock models only on the known regression partition."
    )
    parser.add_argument("models", nargs="+", help="Cheap on-demand Bedrock model IDs")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    cases = load_cases("regression")
    summaries: list[dict[str, Any]] = []
    for model_id in args.models:
        app_settings = Settings(
            llm_provider="bedrock",
            bedrock_model_id=model_id,
            aws_default_region="us-east-1",
        )
        report = EvaluationRunner(app_settings=app_settings).run(cases, "regression")
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", model_id)
        report_path = args.output_dir / f"{safe_name}.json"
        report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        summaries.append(summarize(report))

    eligible = [item for item in summaries if not item["blockers"]]
    winner = max(eligible, key=_rank)["model_id"] if eligible else None
    aggregate = {
        "label": "Known GeBIZ-derived regression model bake-off; not blind evaluation",
        "selection_partition": "REGRESSION",
        "expected_answers_sent_to_model": False,
        "winner": winner,
        "models": summaries,
    }
    output = args.output_dir / "summary.json"
    output.write_text(json.dumps(aggregate, indent=2), encoding="utf-8")
    print(json.dumps(aggregate, indent=2))


if __name__ == "__main__":
    main()
