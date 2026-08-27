from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.rules.schemas import ProcurementRule

InterpretationMode = Literal["BEDROCK", "GROQ", "DEMO_FALLBACK"]
InterpretationStatus = Literal["INTERPRETED", "UNCERTAIN"]
ChangeType = Literal["ADDED", "MODIFIED", "REMOVED", "UNCHANGED"]
RequirementType = Literal[
    "ELIGIBILITY",
    "MANPOWER",
    "TECHNICAL",
    "COMMERCIAL",
    "DOCUMENT",
    "DEADLINE",
    "COMPLIANCE",
    "OTHER",
]
GateType = Literal["MANDATORY", "SCORED", "INFORMATIONAL"]
type JsonScalar = str | int | float | bool | None


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RequirementSource(StrictModel):
    document: str = Field(min_length=1, max_length=500)
    page: int = Field(ge=1)
    section: str = Field(min_length=1, max_length=1000)
    snippet: str = Field(max_length=100_000)


class StructuredField(StrictModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,99}$")
    value: JsonScalar


class StructuredRequirement(StrictModel):
    stable_key: str | None = Field(default=None, max_length=100)
    text: str = Field(min_length=1, max_length=100_000)
    requirement_type: RequirementType
    gate_type: GateType
    deadline: datetime | None = None
    minimum_count: int | None = None
    certification: str | None = None
    compulsory: bool | None = None
    procurement_rule: ProcurementRule | None = None
    structured_fields: list[StructuredField] = Field(default_factory=list, max_length=200)
    interpretation_status: InterpretationStatus
    uncertainty_reason: str | None = None
    source: RequirementSource

    @model_validator(mode="after")
    def uncertainty_is_explained(self) -> "StructuredRequirement":
        if self.interpretation_status == "UNCERTAIN" and not self.uncertainty_reason:
            raise ValueError("UNCERTAIN requirements must include uncertainty_reason")
        return self


class RequirementInterpretationResult(StrictModel):
    requirements: list[StructuredRequirement] = Field(max_length=200)


class RequirementInterpretationRequest(StrictModel):
    document_name: str = Field(min_length=1, max_length=500)
    page: int = Field(ge=1)
    section: str = Field(min_length=1, max_length=1000)
    text: str = Field(max_length=100_000)
    stable_key_hint: str | None = Field(default=None, max_length=100)


type ChangeValue = JsonScalar | list[StructuredField] | ProcurementRule


class FieldChange(StrictModel):
    field: Literal[
        "text",
        "requirement_type",
        "gate_type",
        "deadline",
        "minimum_count",
        "certification",
        "compulsory",
        "structured_fields",
        "procurement_rule",
    ]
    old_value: ChangeValue
    new_value: ChangeValue


class ChangeInterpretationResult(StrictModel):
    change_type: ChangeType
    affected_stable_key: str | None = None
    changed_fields: list[FieldChange] = Field(max_length=50)
    resulting_requirement: StructuredRequirement | None = None
    interpretation_status: InterpretationStatus
    uncertainty_reason: str | None = None
    reason_summary: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def change_shape_is_consistent(self) -> "ChangeInterpretationResult":
        if self.interpretation_status == "UNCERTAIN" and not self.uncertainty_reason:
            raise ValueError("UNCERTAIN changes must include uncertainty_reason")
        if self.change_type == "MODIFIED":
            if not self.changed_fields or self.resulting_requirement is None:
                raise ValueError("MODIFIED requires changed_fields and resulting_requirement")
        elif self.change_type == "ADDED":
            if self.resulting_requirement is None:
                raise ValueError("ADDED requires resulting_requirement")
        elif self.change_type == "REMOVED":
            if self.resulting_requirement is not None:
                raise ValueError("REMOVED cannot include resulting_requirement")
        elif self.changed_fields:
            raise ValueError("UNCHANGED cannot include changed_fields")
        fields = [item.field for item in self.changed_fields]
        if len(fields) != len(set(fields)):
            raise ValueError("changed_fields cannot contain duplicate fields")
        return self


class ChangeInterpretationRequest(StrictModel):
    existing_requirement: StructuredRequirement
    corrigendum_document: str = Field(min_length=1, max_length=500)
    page: int = Field(ge=1)
    section: str = Field(min_length=1, max_length=1000)
    text: str = Field(max_length=100_000)


class RequirementInterpretationEnvelope(StrictModel):
    mode: InterpretationMode
    model_id: str | None = None
    fallback_reason: str | None = None
    attempts: int = Field(ge=0)
    result: RequirementInterpretationResult


class ChangeInterpretationEnvelope(StrictModel):
    mode: InterpretationMode
    model_id: str | None = None
    fallback_reason: str | None = None
    attempts: int = Field(ge=0)
    result: ChangeInterpretationResult
