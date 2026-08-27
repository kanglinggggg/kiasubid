from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.enums import AssessmentStatus, OperationalStatus


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuleKind(StrEnum):
    EVENT_ATTENDANCE = "EVENT_ATTENDANCE"
    QUALIFICATION = "QUALIFICATION"
    REQUIRED_DOCUMENT = "REQUIRED_DOCUMENT"
    PROCESSING_WINDOW = "PROCESSING_WINDOW"
    PARTICIPATION_RESTRICTION = "PARTICIPATION_RESTRICTION"
    SOURCE_FRESHNESS = "SOURCE_FRESHNESS"


class EventAttendanceRule(StrictModel):
    kind: Literal["EVENT_ATTENDANCE"]
    event_name: str = Field(min_length=1)
    compulsory: bool | None
    event_at: datetime | None = None


class EventAttendanceFacts(StrictModel):
    kind: Literal["EVENT_ATTENDANCE"]
    attended: bool | None
    attendance_opportunity_open: bool | None
    makeup_available: bool | None = False


class QualificationOption(StrictModel):
    code: str = Field(min_length=1)
    minimum_grade: str | None = None


class QualificationRule(StrictModel):
    kind: Literal["QUALIFICATION"]
    options: list[QualificationOption] = Field(min_length=1)
    match: Literal["ANY", "ALL"] = "ANY"
    compulsory: bool | None


class QualificationEvidence(StrictModel):
    code: str = Field(min_length=1)
    grade: str | None = None
    verified: bool | None
    meets_minimum: bool | None


class QualificationFacts(StrictModel):
    kind: Literal["QUALIFICATION"]
    evidence: list[QualificationEvidence] = Field(default_factory=list)
    can_obtain_before_deadline: bool | None


class RequiredDocumentRule(StrictModel):
    kind: Literal["REQUIRED_DOCUMENT"]
    documents: list[str] = Field(min_length=1)
    match: Literal["ANY", "ALL"] = "ALL"
    compulsory: bool | None


class DocumentFact(StrictModel):
    name: str = Field(min_length=1)
    state: Literal["SUBMITTED", "READY", "MISSING", "UNKNOWN"]
    can_complete_before_deadline: bool | None = None


class RequiredDocumentFacts(StrictModel):
    kind: Literal["REQUIRED_DOCUMENT"]
    documents: list[DocumentFact] = Field(default_factory=list)
    submission_open: bool | None


class ProcessingWindowRule(StrictModel):
    kind: Literal["PROCESSING_WINDOW"]
    action: str = Field(min_length=1)
    deadline: datetime
    minimum_processing_hours: float = Field(default=0, ge=0)
    compulsory: bool | None


class ProcessingWindowFacts(StrictModel):
    kind: Literal["PROCESSING_WINDOW"]
    completed: bool | None
    can_complete: bool | None
    earliest_start_at: datetime | None = None
    estimated_duration_hours: float | None = Field(default=None, ge=0)


class ParticipationRestrictionRule(StrictModel):
    kind: Literal["PARTICIPATION_RESTRICTION"]
    restriction: str = Field(min_length=1)
    compulsory: bool | None


class ParticipationRestrictionFacts(StrictModel):
    kind: Literal["PARTICIPATION_RESTRICTION"]
    eligible: bool | None
    can_become_eligible_before_deadline: bool | None


class SourceFreshnessRule(StrictModel):
    kind: Literal["SOURCE_FRESHNESS"]
    source_name: str = Field(min_length=1)
    latest_version_required: bool = True


class SourceFreshnessFacts(StrictModel):
    kind: Literal["SOURCE_FRESHNESS"]
    latest_version_ingested: bool | None
    change_notice_present: bool | None
    change_content_available: bool | None


ProcurementRule = Annotated[
    EventAttendanceRule
    | QualificationRule
    | RequiredDocumentRule
    | ProcessingWindowRule
    | ParticipationRestrictionRule
    | SourceFreshnessRule,
    Field(discriminator="kind"),
]

ProcurementRuleFacts = Annotated[
    EventAttendanceFacts
    | QualificationFacts
    | RequiredDocumentFacts
    | ProcessingWindowFacts
    | ParticipationRestrictionFacts
    | SourceFreshnessFacts,
    Field(discriminator="kind"),
]


class RuleEvaluationInput(StrictModel):
    rule: ProcurementRule
    facts: ProcurementRuleFacts

    @model_validator(mode="after")
    def rule_and_facts_have_same_kind(self) -> "RuleEvaluationInput":
        if self.rule.kind != self.facts.kind:
            raise ValueError(
                f"Rule kind {self.rule.kind} cannot be evaluated with facts {self.facts.kind}"
            )
        return self


class RuleEvaluationResult(StrictModel):
    rule_kind: RuleKind
    status: Literal[
        AssessmentStatus.SATISFIED,
        AssessmentStatus.PARTIAL,
        AssessmentStatus.UNMET,
        AssessmentStatus.UNCERTAIN,
    ]
    recoverable: bool | None
    reason: str
    satisfied_items: list[str] = Field(default_factory=list)
    unresolved_items: list[str] = Field(default_factory=list)
    projected_completion_at: datetime | None = None


class RequirementEvaluationResult(StrictModel):
    requirement_status: Literal[
        AssessmentStatus.SATISFIED,
        AssessmentStatus.PARTIAL,
        AssessmentStatus.UNMET,
        AssessmentStatus.UNCERTAIN,
    ]
    operational_status: OperationalStatus
    reason: str
    rule_results: list[RuleEvaluationResult]
