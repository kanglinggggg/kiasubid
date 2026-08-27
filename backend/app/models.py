from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    uen: Mapped[str] = mapped_column(String, nullable=False)
    industry: Mapped[str] = mapped_column(String, nullable=False)
    employee_count: Mapped[int] = mapped_column(Integer, nullable=False)
    annual_revenue: Mapped[str] = mapped_column(String, nullable=False)


class Tender(Base):
    __tablename__ = "tenders"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    agency: Mapped[str] = mapped_column(String, nullable=False)
    reference_number: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    closing_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    source_type: Mapped[str] = mapped_column(String, default="SYNTHETIC_DEMO")
    operational_status: Mapped[str] = mapped_column(String, default="FEASIBLE")
    previous_operational_status: Mapped[str | None] = mapped_column(String, nullable=True)
    submission_coverage: Mapped[float] = mapped_column(Float, default=0)
    deadline_risk: Mapped[str] = mapped_column(String, default="LOW")
    human_action_required: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    company: Mapped[Company] = relationship()
    documents: Mapped[list["TenderDocument"]] = relationship(cascade="all, delete-orphan")
    requirements: Mapped[list["Requirement"]] = relationship(cascade="all, delete-orphan")
    tasks: Mapped[list["Task"]] = relationship(cascade="all, delete-orphan")


class TenderDocument(Base):
    __tablename__ = "tender_documents"
    __table_args__ = (UniqueConstraint("tender_id", "filename", "version"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tender_id: Mapped[str] = mapped_column(ForeignKey("tenders.id"), nullable=False)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    document_type: Mapped[str] = mapped_column(String, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    text_content_reference: Mapped[str | None] = mapped_column(String, nullable=True)


class Requirement(Base):
    __tablename__ = "requirements"
    __table_args__ = (UniqueConstraint("tender_id", "stable_key", "version"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    stable_key: Mapped[str] = mapped_column(String, nullable=False)
    tender_id: Mapped[str] = mapped_column(ForeignKey("tenders.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    requirement_type: Mapped[str] = mapped_column(String, nullable=False)
    gate_type: Mapped[str] = mapped_column(String, nullable=False)
    deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source_document_id: Mapped[str] = mapped_column(
        ForeignKey("tender_documents.id"), nullable=False
    )
    source_page: Mapped[int] = mapped_column(Integer, nullable=False)
    source_section: Mapped[str] = mapped_column(String, nullable=False)
    source_snippet: Mapped[str] = mapped_column(Text, nullable=False)
    supersedes_requirement_id: Mapped[str | None] = mapped_column(
        ForeignKey("requirements.id"), nullable=True
    )
    rule_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    source_document: Mapped[TenderDocument] = relationship()
    assessments: Mapped[list["Assessment"]] = relationship(cascade="all, delete-orphan")


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    employment_status: Mapped[str] = mapped_column(String, default="ACTIVE")
    availability_status: Mapped[str] = mapped_column(String, default="UNKNOWN")
    experience_years: Mapped[int] = mapped_column(Integer, nullable=False)


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    subject_type: Mapped[str] = mapped_column(String, nullable=False)
    subject_id: Mapped[str] = mapped_column(String, nullable=False)
    source_file: Mapped[str | None] = mapped_column(String, nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    verification_status: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class Assessment(Base):
    __tablename__ = "assessments"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    requirement_id: Mapped[str] = mapped_column(ForeignKey("requirements.id"), nullable=False)
    requirement_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    reason_summary: Mapped[str] = mapped_column(Text, nullable=False)
    assessed_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    assessment_method: Mapped[str] = mapped_column(String, default="RULE")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tender_id: Mapped[str] = mapped_column(ForeignKey("tenders.id"), nullable=False)
    requirement_id: Mapped[str | None] = mapped_column(ForeignKey("requirements.id"), nullable=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    owner: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    priority: Mapped[str] = mapped_column(String, nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    latest_safe_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    estimated_duration_hours: Mapped[float] = mapped_column(Float, nullable=False)
    recovery_path: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class TaskDependency(Base):
    __tablename__ = "task_dependencies"

    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), primary_key=True)
    depends_on_task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), primary_key=True)


class ChangeEvent(Base):
    __tablename__ = "change_events"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tender_id: Mapped[str] = mapped_column(ForeignKey("tenders.id"), nullable=False)
    source_document_id: Mapped[str] = mapped_column(
        ForeignKey("tender_documents.id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    affected_requirement_ids: Mapped[list[str]] = mapped_column(JSON, default=list)


class ActivityEvent(Base):
    __tablename__ = "activity_events"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tender_id: Mapped[str] = mapped_column(ForeignKey("tenders.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    actor: Mapped[str] = mapped_column(String, default="system")
    entity_id: Mapped[str | None] = mapped_column(String, nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class HumanApproval(Base):
    __tablename__ = "human_approvals"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tender_id: Mapped[str] = mapped_column(ForeignKey("tenders.id"), nullable=False)
    approved_by: Mapped[str] = mapped_column(String, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
