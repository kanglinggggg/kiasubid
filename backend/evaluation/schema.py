from datetime import datetime
from typing import Literal

from app.llm.schemas import (
    ChangeInterpretationRequest,
    ChangeType,
    GateType,
    InterpretationStatus,
    RequirementInterpretationRequest,
    RequirementType,
)
from app.rules import ProcurementRuleFacts, RuleEvaluationInput
from pydantic import BaseModel, ConfigDict, Field, model_validator

type ExpectedValue = str | int | float | bool | None | list[str]
FailureCategory = Literal[
    "extraction error",
    "semantic matching error",
    "ambiguity handling error",
    "deterministic rule error",
    "deadline error",
    "source-provenance error",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvaluationExpected(StrictModel):
    requirement_type: RequirementType | None
    gate_type: GateType | None
    structured_fields: dict[str, ExpectedValue]
    ambiguity_state: InterpretationStatus
    affected_requirement: str | None
    change_type: ChangeType | None
    final_operational_state: Literal[
        "FEASIBLE", "RECOVERABLE", "BLOCKED", "UNCERTAIN"
    ]


class EvaluationCase(StrictModel):
    id: str
    partition: Literal["DEVELOPMENT", "REGRESSION", "BLIND"]
    source_case_id: str
    title: str
    description: str
    source: str
    evaluation_as_of: datetime
    kind: Literal["REQUIREMENT", "CORRIGENDUM"]
    requirement_input: RequirementInterpretationRequest | None
    change_input: ChangeInterpretationRequest | None
    deterministic_scenario: Literal["HERO_R17"] | None
    deterministic_facts: ProcurementRuleFacts | list[ProcurementRuleFacts] | None = None
    companion_rules: list[RuleEvaluationInput] = Field(default_factory=list)
    expected: EvaluationExpected

    @model_validator(mode="after")
    def exactly_one_input_matches_kind(self) -> "EvaluationCase":
        if self.kind == "REQUIREMENT":
            if self.requirement_input is None or self.change_input is not None:
                raise ValueError("REQUIREMENT cases require only requirement_input")
        elif self.change_input is None or self.requirement_input is not None:
            raise ValueError("CORRIGENDUM cases require only change_input")
        return self


class CaseFailure(StrictModel):
    category: FailureCategory
    stage: str
    detail: str


class CaseResult(StrictModel):
    id: str
    partition: Literal["DEVELOPMENT", "REGRESSION", "BLIND"]
    interpretation_mode: str
    requirement_interpretation: Literal["PASS", "FAIL", "NOT_APPLICABLE", "NOT_RUN"]
    corrigendum_matching: Literal["PASS", "FAIL", "NOT_APPLICABLE", "NOT_RUN"]
    ambiguity_handling: Literal["PASS", "FAIL", "NOT_RUN"]
    final_operational_state: Literal["PASS", "FAIL", "NOT_RUN"]
    actual_operational_state: str | None
    unsafe_green_error: bool
    blocker: str | None = None
    failures: list[CaseFailure]


class AccuracyMetric(StrictModel):
    passed: int
    failed: int
    not_run: int
    not_applicable: int
    accuracy_percent: float | None


class EvaluationReport(StrictModel):
    generated_at: datetime
    live_model_required: bool
    provider: Literal["bedrock", "groq"]
    provider_configured: bool
    model_id: str | None
    partition: str
    total_benchmark_cases: int
    requirement_interpretation_accuracy: AccuracyMetric
    corrigendum_matching_accuracy: AccuracyMetric
    ambiguity_handling_accuracy: AccuracyMetric
    final_operational_state_accuracy: AccuracyMetric
    unsafe_green_errors: list[dict[str, str]]
    blockers: list[str]
    failures: list[dict[str, str]]
    cases: list[CaseResult]
