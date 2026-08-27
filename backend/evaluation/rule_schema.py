from datetime import datetime
from typing import Literal

from app.enums import AssessmentStatus, OperationalStatus
from app.rules import RuleEvaluationInput
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuleBenchmarkExpected(StrictModel):
    requirement_result: Literal[
        AssessmentStatus.SATISFIED,
        AssessmentStatus.PARTIAL,
        AssessmentStatus.UNMET,
        AssessmentStatus.UNCERTAIN,
    ]
    operational_status: OperationalStatus
    prior_operational_status: OperationalStatus | None = None


class RuleBenchmarkCase(StrictModel):
    id: str
    source_case_id: str
    title: str
    source: str
    evaluation_as_of: datetime
    rules: list[RuleEvaluationInput] = Field(default_factory=list)
    prior_rules: list[RuleEvaluationInput] = Field(default_factory=list)
    unsupported_reason: str | None = None
    expected: RuleBenchmarkExpected

    @model_validator(mode="after")
    def supported_case_has_rules(self) -> "RuleBenchmarkCase":
        if not self.rules and self.unsupported_reason is None:
            raise ValueError("A benchmark case must provide rules or an unsupported_reason")
        if self.prior_rules and self.expected.prior_operational_status is None:
            raise ValueError("prior_rules require prior_operational_status ground truth")
        return self


class BenchmarkAccuracy(StrictModel):
    passed: int
    failed: int
    unsupported: int
    accuracy_percent: float | None


class RuleBenchmarkCaseResult(StrictModel):
    id: str
    requirement_result: Literal["PASS", "FAIL", "UNSUPPORTED"]
    operational_status: Literal["PASS", "FAIL", "UNSUPPORTED"]
    actual_requirement_result: str | None
    actual_operational_status: str | None
    actual_prior_operational_status: str | None
    failure_category: Literal["deterministic rule error", "deadline error"] | None
    failure_detail: str | None


class RuleBenchmarkReport(StrictModel):
    generated_at: datetime
    source: str
    total_benchmark_cases: int
    interpretation_status: Literal["NOT_RUN"]
    interpretation_reason: str
    deterministic_requirement_result_accuracy: BenchmarkAccuracy
    overall_bid_status_accuracy: BenchmarkAccuracy
    unsupported_cases: list[dict[str, str]]
    failures: list[dict[str, str]]
    cases: list[RuleBenchmarkCaseResult]
