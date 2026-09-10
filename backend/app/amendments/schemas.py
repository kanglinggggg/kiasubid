from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AmendmentSource(StrictModel):
    document_name: str = Field(min_length=1, max_length=500)
    document_version: int = Field(default=2, ge=1, le=10_000)
    page: int = Field(ge=1, le=100_000)
    section: str = Field(min_length=1, max_length=1_000)
    text: str = Field(min_length=1, max_length=100_000)


class AmendmentPreviewRequest(StrictModel):
    requirement_id: str = Field(min_length=1, max_length=200)
    source: AmendmentSource


class AmendmentApplyRequest(StrictModel):
    preview_id: str = Field(min_length=1, max_length=100)
    reviewed_source_and_diff: Literal[True]
    confirmed_by: str = Field(min_length=2, max_length=200)


class SourceProof(StrictModel):
    document_name: str
    document_version: int
    page: int
    section: str
    exact_excerpt: str
    sha256: str
    provenance: Literal["USER_SUPPLIED_EXACT_TEXT"] = "USER_SUPPLIED_EXACT_TEXT"


class RequirementSnapshot(StrictModel):
    id: str
    stable_key: str
    version: int
    text: str
    requirement_type: str
    gate_type: str
    minimum_count: int | None = None
    certification: str | None = None
    assessment: str


class FieldDiff(StrictModel):
    field: str
    old_value: str
    new_value: str


class PlannedTask(StrictModel):
    key: str
    title: str
    description: str
    owner: str
    status: Literal["OPEN", "WAITING"]
    priority: Literal["CRITICAL", "HIGH"]
    due_at: datetime
    latest_safe_at: datetime
    estimated_duration_hours: float
    depends_on: list[str] = Field(default_factory=list)


class AmendmentImpactPreview(StrictModel):
    assessment_before: str
    assessment_after: str
    operational_status_before: str
    operational_status_after: str
    critical_gates_before: str
    critical_gates_after: str
    submission_coverage_before: int
    submission_coverage_after: int
    deadline_risk_before: str
    deadline_risk_after: str
    calculation_note: str


class ClarificationDraft(StrictModel):
    reason: str
    question: str
    source_reference: str
    external_action: Literal["COPY_ONLY"] = "COPY_ONLY"


class WorkflowStep(StrictModel):
    step: int = Field(ge=1)
    node: str
    status: Literal["DONE", "BLOCKED", "SKIPPED"]
    detail: str


class AmendmentPreviewResponse(StrictModel):
    preview_id: str
    state: Literal[
        "PREVIEW_READY",
        "REVIEW_REQUIRED",
        "NO_TRACKED_CHANGE",
    ]
    apply_allowed: bool
    block_reason: str | None = None
    source: SourceProof
    target: RequirementSnapshot
    proposed: RequirementSnapshot | None = None
    change_type: Literal["ADDED", "MODIFIED", "REMOVED", "UNCHANGED"]
    changed_fields: list[FieldDiff] = Field(default_factory=list)
    reason_summary: str
    interpretation_mode: Literal["BEDROCK", "GROQ", "DEMO_FALLBACK"]
    model_id: str | None = None
    fallback_reason: str | None = None
    impact: AmendmentImpactPreview | None = None
    planned_tasks: list[PlannedTask] = Field(default_factory=list)
    clarification: ClarificationDraft | None = None
    workflow_trace: list[WorkflowStep]
    human_checkpoint: str
    expires_in_minutes: int = 30
