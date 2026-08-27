from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class BenchmarkRequirement(BaseModel):
    stable_key: str
    text: str
    requirement_type: str = "MANPOWER"
    gate_type: Literal["MANDATORY", "SCORED", "INFORMATIONAL"] = "MANDATORY"
    source_page: int = 1
    source_section: str = "Benchmark fixture"
    rule_config: dict[str, Any]


class BenchmarkEmployee(BaseModel):
    id: str
    name: str
    availability_status: Literal["AVAILABLE", "UNAVAILABLE", "UNKNOWN"]
    experience_years: int = 1


class BenchmarkEvidence(BaseModel):
    id: str
    type: str
    title: str
    subject_id: str
    verification_status: Literal["VERIFIED", "STALE", "MISSING", "UNVERIFIED"]
    valid_until: datetime | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class BenchmarkRecoveryTask(BaseModel):
    id: str
    status: Literal["OPEN", "IN_PROGRESS", "WAITING", "DONE", "BLOCKED"] = "OPEN"
    due_at: datetime
    latest_safe_at: datetime | None = None
    estimated_duration_hours: float = 1


class BenchmarkExpected(BaseModel):
    assessment_status: Literal["SATISFIED", "PARTIAL", "UNMET", "UNCERTAIN"]
    operational_status: Literal["FEASIBLE", "RECOVERABLE", "BLOCKED", "UNCERTAIN"]
    usable_employee_count: int
    recovery_candidate_count: int


class BenchmarkCase(BaseModel):
    id: str
    description: str
    source: str = "synthetic-benchmark"
    tender_closing_at: datetime
    requirement: BenchmarkRequirement
    employees: list[BenchmarkEmployee] = Field(default_factory=list)
    evidence: list[BenchmarkEvidence] = Field(default_factory=list)
    recovery_tasks: list[BenchmarkRecoveryTask] = Field(default_factory=list)
    expected: BenchmarkExpected
