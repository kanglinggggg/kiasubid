from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.enums import (
    AssessmentStatus,
    AvailabilityStatus,
    GateType,
    TaskPriority,
    TaskStatus,
    VerificationStatus,
)
from app.models import (
    ActivityEvent,
    Assessment,
    ChangeEvent,
    Company,
    Employee,
    Evidence,
    HumanApproval,
    Requirement,
    Task,
    TaskDependency,
    Tender,
    TenderDocument,
)

DEMO_BID_ID = "BID-DEMO-001"
DEMO_COMPANY_ID = "COMPANY-NEXUS"
DEMO_CLOSING = datetime(2026, 8, 28, 9, 0)  # 17:00 Singapore time
DEMO_NOW = datetime(2026, 8, 21, 5, 0)  # 13:00 Singapore time


def _document(
    document_id: str, filename: str, document_type: str, version: int = 1
) -> TenderDocument:
    return TenderDocument(
        id=document_id,
        tender_id=DEMO_BID_ID,
        filename=filename,
        document_type=document_type,
        version=version,
        uploaded_at=DEMO_NOW,
        text_content_reference=f"demo://documents/{document_id}",
    )


def _requirement(
    key: str,
    text: str,
    requirement_type: str,
    gate: GateType,
    page: int,
    section: str,
    document_id: str = "DOC-MAIN",
    rule: dict | None = None,
) -> Requirement:
    return Requirement(
        id=f"REQ-{key}-V1",
        stable_key=key,
        tender_id=DEMO_BID_ID,
        version=1,
        text=text,
        requirement_type=requirement_type,
        gate_type=gate.value,
        deadline=DEMO_CLOSING if key in {"R05", "R18"} else None,
        source_document_id=document_id,
        source_page=page,
        source_section=section,
        source_snippet=text,
        rule_config=rule or {"kind": "fixture"},
        created_at=DEMO_NOW,
    )


def _evidence(
    evidence_id: str,
    evidence_type: str,
    title: str,
    subject_type: str,
    subject_id: str,
    status: VerificationStatus = VerificationStatus.VERIFIED,
    details: dict | None = None,
    valid_until: datetime | None = None,
) -> Evidence:
    return Evidence(
        id=evidence_id,
        company_id=DEMO_COMPANY_ID,
        type=evidence_type,
        title=title,
        subject_type=subject_type,
        subject_id=subject_id,
        source_file=f"synthetic/{evidence_id.lower()}.pdf",
        details=details or {},
        valid_from=datetime(2025, 1, 1),
        valid_until=valid_until or datetime(2027, 12, 31),
        verified_at=DEMO_NOW if status == VerificationStatus.VERIFIED else None,
        verification_status=status.value,
        created_at=DEMO_NOW,
        updated_at=DEMO_NOW,
    )


def _assessment(
    key: str,
    status: AssessmentStatus,
    reason: str,
    evidence_ids: list[str] | None = None,
) -> Assessment:
    return Assessment(
        id=f"ASM-{key}-V1",
        requirement_id=f"REQ-{key}-V1",
        requirement_version=1,
        status=status.value,
        evidence_ids=evidence_ids or [],
        reason_summary=reason,
        assessed_at=DEMO_NOW,
        assessment_method="RULE",
    )


def _task(
    number: int,
    title: str,
    status: TaskStatus,
    owner: str,
    due_at: datetime,
    priority: TaskPriority = TaskPriority.MEDIUM,
    requirement_id: str | None = None,
) -> Task:
    completed_at = DEMO_NOW if status == TaskStatus.DONE else None
    return Task(
        id=f"TASK-SEED-{number:02d}",
        tender_id=DEMO_BID_ID,
        requirement_id=requirement_id,
        title=title,
        description=f"Bid preparation task: {title}.",
        owner=owner,
        status=status.value,
        priority=priority.value,
        due_at=due_at,
        latest_safe_at=due_at,
        estimated_duration_hours=1.0,
        recovery_path=False,
        created_at=datetime(2026, 8, 19, 2, 0),
        updated_at=DEMO_NOW,
        completed_at=completed_at,
    )


def seed_demo(session: Session) -> Tender:
    existing = session.scalar(select(Tender).where(Tender.id == DEMO_BID_ID))
    if existing:
        return existing

    company = Company(
        id=DEMO_COMPANY_ID,
        name="NexusFort Technologies Pte. Ltd.",
        uen="202612345N",
        industry="Cybersecurity / Managed IT Services",
        employee_count=68,
        annual_revenue="S$4.8M",
    )
    tender = Tender(
        id=DEMO_BID_ID,
        company_id=DEMO_COMPANY_ID,
        title="Managed Cybersecurity Monitoring and Response Services",
        agency="Digital Government Agency",
        reference_number="DGA/ICT/2026/017",
        closing_at=DEMO_CLOSING,
        source_type="SYNTHETIC_DEMO",
        operational_status="FEASIBLE",
        submission_coverage=91,
        deadline_risk="LOW",
        human_action_required=True,
        created_at=datetime(2026, 8, 18, 1, 0),
        updated_at=DEMO_NOW,
    )
    session.add_all(
        [
            company,
            tender,
            _document("DOC-MAIN", "DGA_ICT_2026_017_Main_Tender.pdf", "MAIN_TENDER"),
            _document(
                "DOC-TECH",
                "DGA_ICT_2026_017_Technical_Specification.pdf",
                "TECHNICAL_SPECIFICATION",
            ),
            _document("DOC-ANNEX", "DGA_ICT_2026_017_Annexes.pdf", "ANNEX"),
        ]
    )

    employees = [
        Employee(
            id="EMP-A",
            company_id=DEMO_COMPANY_ID,
            name="Aisha Rahman",
            role="Engineer A · Senior Security Engineer",
            employment_status="ACTIVE",
            availability_status=AvailabilityStatus.AVAILABLE.value,
            experience_years=9,
        ),
        Employee(
            id="EMP-B",
            company_id=DEMO_COMPANY_ID,
            name="Benjamin Lee",
            role="Engineer B · SOC Lead",
            employment_status="ACTIVE",
            availability_status=AvailabilityStatus.AVAILABLE.value,
            experience_years=11,
        ),
        Employee(
            id="EMP-C",
            company_id=DEMO_COMPANY_ID,
            name="Cheryl Ng",
            role="Engineer C · Incident Response Lead",
            employment_status="ACTIVE",
            availability_status=AvailabilityStatus.AVAILABLE.value,
            experience_years=8,
        ),
        Employee(
            id="EMP-D",
            company_id=DEMO_COMPANY_ID,
            name="Daniel Tan",
            role="Engineer D · Security Architect",
            employment_status="ACTIVE",
            availability_status=AvailabilityStatus.UNKNOWN.value,
            experience_years=10,
        ),
        Employee(
            id="EMP-E",
            company_id=DEMO_COMPANY_ID,
            name="Evelyn Koh",
            role="Project Manager",
            employment_status="ACTIVE",
            availability_status=AvailabilityStatus.AVAILABLE.value,
            experience_years=12,
        ),
        Employee(
            id="EMP-F",
            company_id=DEMO_COMPANY_ID,
            name="Farid Ismail",
            role="Cloud Security Engineer",
            employment_status="ACTIVE",
            availability_status=AvailabilityStatus.AVAILABLE.value,
            experience_years=6,
        ),
        Employee(
            id="EMP-G",
            company_id=DEMO_COMPANY_ID,
            name="Grace Lim",
            role="GRC Consultant",
            employment_status="ACTIVE",
            availability_status=AvailabilityStatus.AVAILABLE.value,
            experience_years=7,
        ),
        Employee(
            id="EMP-H",
            company_id=DEMO_COMPANY_ID,
            name="Harish Nair",
            role="Service Delivery Manager",
            employment_status="ACTIVE",
            availability_status=AvailabilityStatus.AVAILABLE.value,
            experience_years=13,
        ),
    ]
    session.add_all(employees)

    requirements = [
        _requirement(
            "R01",
            "Tenderer must hold an active GeBIZ Trading Partner registration.",
            "REGISTRATION",
            GateType.MANDATORY,
            5,
            "2.1",
        ),
        _requirement(
            "R02",
            "Average annual revenue over the last two financial years must exceed S$3 million.",
            "FINANCIAL",
            GateType.SCORED,
            6,
            "2.3",
        ),
        _requirement(
            "R03",
            "Tenderer must maintain ISO/IEC 27001 certification through the contract term.",
            "CERTIFICATION",
            GateType.MANDATORY,
            7,
            "2.5",
        ),
        _requirement(
            "R04",
            "Provide at least three comparable managed cybersecurity service engagements.",
            "EXPERIENCE",
            GateType.SCORED,
            11,
            "3.2",
        ),
        _requirement(
            "R05",
            "Attendance at the tender briefing is compulsory.",
            "BRIEFING",
            GateType.MANDATORY,
            4,
            "1.6",
        ),
        _requirement(
            "R06",
            "The proposed project manager should have at least eight years of relevant experience.",
            "MANPOWER",
            GateType.SCORED,
            14,
            "4.1",
            "DOC-TECH",
        ),
        _requirement(
            "R07",
            "Maintain professional indemnity insurance of at least S$2 million.",
            "INSURANCE",
            GateType.MANDATORY,
            9,
            "2.8",
        ),
        _requirement(
            "R08",
            "Submit the signed tender declaration and conflict-of-interest declaration.",
            "DECLARATION",
            GateType.MANDATORY,
            22,
            "7.1",
        ),
        _requirement(
            "R09",
            "Complete the pricing schedule using the prescribed annex without structural changes.",
            "PRICING",
            GateType.SCORED,
            3,
            "Annex B",
            "DOC-ANNEX",
        ),
        _requirement(
            "R10",
            "Describe the proposed 24x7 monitoring and escalation operating model.",
            "TECHNICAL",
            GateType.SCORED,
            8,
            "3.1",
            "DOC-TECH",
        ),
        _requirement(
            "R11",
            "Provide a transition plan covering the first sixty calendar days.",
            "DOCUMENT",
            GateType.INFORMATIONAL,
            10,
            "3.5",
            "DOC-TECH",
        ),
        _requirement(
            "R12",
            "All security monitoring data must remain hosted in Singapore.",
            "TECHNICAL",
            GateType.MANDATORY,
            12,
            "3.8",
            "DOC-TECH",
        ),
        _requirement(
            "R13",
            "Describe threat-intelligence sources and update cadence.",
            "TECHNICAL",
            GateType.SCORED,
            13,
            "3.9",
            "DOC-TECH",
        ),
        _requirement(
            "R14",
            "Provide sample monthly service reports and KPI definitions.",
            "DOCUMENT",
            GateType.SCORED,
            15,
            "5.2",
            "DOC-TECH",
        ),
        _requirement(
            "R15",
            "Identify subcontractors proposed for service delivery, if any.",
            "DECLARATION",
            GateType.INFORMATIONAL,
            18,
            "6.1",
        ),
        _requirement(
            "R16",
            "Tender validity period is 120 days from closing.",
            "CONTRACTUAL",
            GateType.INFORMATIONAL,
            20,
            "6.7",
        ),
        _requirement(
            "R17",
            "The Tenderer shall propose not fewer than three personnel holding valid CISSP certification.",
            "MANPOWER",
            GateType.MANDATORY,
            17,
            "4.3 Named Technical Personnel",
            "DOC-TECH",
            {"kind": "certified_staff", "certification": "CISSP", "minimum_count": 3},
        ),
        _requirement(
            "R18",
            "The complete tender response must be submitted before the stated closing time.",
            "DEADLINE",
            GateType.MANDATORY,
            2,
            "1.2",
        ),
    ]
    session.add_all(requirements)

    evidence = [
        _evidence(
            "EV-ACRA", "COMPANY_REGISTRATION", "ACRA business profile", "COMPANY", DEMO_COMPANY_ID
        ),
        _evidence(
            "EV-SUPPLIER",
            "SUPPLIER_REGISTRATION",
            "GeBIZ Trading Partner registration",
            "COMPANY",
            DEMO_COMPANY_ID,
        ),
        _evidence(
            "EV-ISO",
            "CERTIFICATION",
            "ISO/IEC 27001:2022 certificate",
            "COMPANY",
            DEMO_COMPANY_ID,
            valid_until=datetime(2027, 5, 31),
        ),
        _evidence(
            "EV-INSURANCE",
            "INSURANCE",
            "Professional indemnity insurance · S$2M",
            "COMPANY",
            DEMO_COMPANY_ID,
            valid_until=datetime(2027, 2, 28),
        ),
        _evidence(
            "EV-FINANCE",
            "FINANCIAL_DOCUMENT",
            "FY2024–FY2025 audited statements",
            "COMPANY",
            DEMO_COMPANY_ID,
            details={"average_revenue_sgd": 4800000},
        ),
        _evidence(
            "EV-BRIEFING",
            "DECLARATION",
            "Compulsory briefing attendance record",
            "COMPANY",
            DEMO_COMPANY_ID,
        ),
        _evidence(
            "EV-DECLARATION",
            "DECLARATION",
            "Tender declarations prepared for signature",
            "COMPANY",
            DEMO_COMPANY_ID,
        ),
        _evidence(
            "EV-DATACENTRE",
            "OTHER",
            "Singapore data-residency architecture attestation",
            "COMPANY",
            DEMO_COMPANY_ID,
        ),
        _evidence(
            "EV-PROJECT-1",
            "PAST_PROJECT",
            "MSS engagement · regional logistics provider",
            "COMPANY",
            DEMO_COMPANY_ID,
        ),
        _evidence(
            "EV-PROJECT-2",
            "PAST_PROJECT",
            "SOC modernisation · healthcare group",
            "COMPANY",
            DEMO_COMPANY_ID,
        ),
        _evidence(
            "EV-PROJECT-3",
            "PAST_PROJECT",
            "24x7 monitoring · financial services SME",
            "COMPANY",
            DEMO_COMPANY_ID,
        ),
        _evidence(
            "EV-PROJECT-4",
            "PAST_PROJECT",
            "Cloud monitoring · retail group",
            "COMPANY",
            DEMO_COMPANY_ID,
            VerificationStatus.UNVERIFIED,
        ),
        _evidence(
            "EV-A-CERT",
            "EMPLOYEE_CERTIFICATION",
            "Engineer A · CISSP",
            "EMPLOYEE",
            "EMP-A",
            details={"certification": "CISSP", "member_id": "CISSP-A-1042"},
            valid_until=datetime(2027, 6, 30),
        ),
        _evidence(
            "EV-B-CERT",
            "EMPLOYEE_CERTIFICATION",
            "Engineer B · CISSP",
            "EMPLOYEE",
            "EMP-B",
            details={"certification": "CISSP", "member_id": "CISSP-B-2177"},
            valid_until=datetime(2028, 1, 31),
        ),
        _evidence(
            "EV-C-CERT",
            "EMPLOYEE_CERTIFICATION",
            "Engineer C · CISSP",
            "EMPLOYEE",
            "EMP-C",
            details={"certification": "CISSP", "member_id": "CISSP-C-3308"},
            valid_until=datetime(2027, 11, 30),
        ),
        _evidence(
            "EV-D-CERT",
            "EMPLOYEE_CERTIFICATION",
            "Engineer D · CISSP",
            "EMPLOYEE",
            "EMP-D",
            details={"certification": "CISSP", "member_id": "CISSP-D-4419"},
            valid_until=datetime(2027, 9, 30),
        ),
        _evidence("EV-A-CV", "CV", "Engineer A · current CV", "EMPLOYEE", "EMP-A"),
        _evidence("EV-B-CV", "CV", "Engineer B · current CV", "EMPLOYEE", "EMP-B"),
        _evidence("EV-C-CV", "CV", "Engineer C · current CV", "EMPLOYEE", "EMP-C"),
        _evidence(
            "EV-D-CV",
            "CV",
            "Engineer D · CV last updated 2024",
            "EMPLOYEE",
            "EMP-D",
            VerificationStatus.STALE,
            valid_until=datetime(2025, 12, 31),
        ),
    ]
    session.add_all(evidence)

    assessments = [
        _assessment(
            "R01",
            AssessmentStatus.SATISFIED,
            "Active supplier registration verified.",
            ["EV-SUPPLIER"],
        ),
        _assessment(
            "R02",
            AssessmentStatus.SATISFIED,
            "Average revenue exceeds S$3 million.",
            ["EV-FINANCE"],
        ),
        _assessment(
            "R03",
            AssessmentStatus.SATISFIED,
            "ISO/IEC 27001 remains valid through the closing date.",
            ["EV-ISO"],
        ),
        _assessment(
            "R04",
            AssessmentStatus.SATISFIED,
            "Three verified comparable engagements are available.",
            ["EV-PROJECT-1", "EV-PROJECT-2", "EV-PROJECT-3"],
        ),
        _assessment(
            "R05",
            AssessmentStatus.SATISFIED,
            "Compulsory briefing attendance is recorded.",
            ["EV-BRIEFING"],
        ),
        _assessment(
            "R06",
            AssessmentStatus.SATISFIED,
            "Proposed project manager has 12 years of experience.",
        ),
        _assessment(
            "R07",
            AssessmentStatus.SATISFIED,
            "Required S$2 million insurance cover is verified.",
            ["EV-INSURANCE"],
        ),
        _assessment(
            "R08",
            AssessmentStatus.SATISFIED,
            "Prescribed declarations are prepared and operationally covered.",
            ["EV-DECLARATION"],
        ),
        _assessment("R09", AssessmentStatus.SATISFIED, "Pricing schedule structure is complete."),
        _assessment(
            "R10",
            AssessmentStatus.PARTIAL,
            "Core operating model is drafted; escalation graphic remains.",
        ),
        _assessment("R11", AssessmentStatus.SATISFIED, "Transition plan is included."),
        _assessment(
            "R12",
            AssessmentStatus.SATISFIED,
            "Singapore data residency is verified.",
            ["EV-DATACENTRE"],
        ),
        _assessment(
            "R13",
            AssessmentStatus.SATISFIED,
            "Threat-intelligence sources and cadence are documented.",
        ),
        _assessment(
            "R14",
            AssessmentStatus.PARTIAL,
            "Report sample is ready; two KPI definitions need copy edit.",
        ),
        _assessment("R15", AssessmentStatus.SATISFIED, "No subcontractors are proposed."),
        _assessment("R16", AssessmentStatus.SATISFIED, "Tender validity period acknowledged."),
        _assessment(
            "R17",
            AssessmentStatus.SATISFIED,
            "Three available employees have valid CISSP certificates and current CVs.",
            ["EV-A-CERT", "EV-A-CV", "EV-B-CERT", "EV-B-CV", "EV-C-CERT", "EV-C-CV"],
        ),
        _assessment(
            "R18", AssessmentStatus.SATISFIED, "Submission plan completes before the closing time."
        ),
    ]
    session.add_all(assessments)

    tasks = [
        _task(
            1,
            "Confirm solution architecture",
            TaskStatus.DONE,
            "Cheryl Ng",
            datetime(2026, 8, 20, 9, 0),
        ),
        _task(
            2,
            "Validate commercial assumptions",
            TaskStatus.DONE,
            "Finance",
            datetime(2026, 8, 20, 10, 0),
        ),
        _task(
            3,
            "Check project references",
            TaskStatus.DONE,
            "Grace Lim",
            datetime(2026, 8, 20, 11, 0),
        ),
        _task(
            4, "Prepare pricing schedule", TaskStatus.DONE, "Bid Team", datetime(2026, 8, 21, 3, 0)
        ),
        _task(
            5,
            "Review security controls",
            TaskStatus.DONE,
            "Benjamin Lee",
            datetime(2026, 8, 21, 4, 0),
        ),
        _task(
            6,
            "Assemble personnel evidence",
            TaskStatus.DONE,
            "Aisha Rahman",
            datetime(2026, 8, 21, 4, 30),
        ),
        _task(
            7, "Draft transition plan", TaskStatus.DONE, "Harish Nair", datetime(2026, 8, 21, 5, 0)
        ),
        _task(
            8,
            "Run mandatory-gate review",
            TaskStatus.DONE,
            "Grace Lim",
            datetime(2026, 8, 21, 5, 0),
        ),
        _task(
            9,
            "Director declaration final review",
            TaskStatus.OPEN,
            "Managing Director",
            datetime(2026, 8, 24, 9, 0),
            TaskPriority.HIGH,
            "REQ-R08-V1",
        ),
        _task(
            10,
            "Confirm briefing record in submission index",
            TaskStatus.OPEN,
            "Bid Team",
            datetime(2026, 8, 25, 9, 0),
            TaskPriority.MEDIUM,
            "REQ-R05-V1",
        ),
    ]
    session.add_all(tasks)

    initial_activity = [
        (
            "DOCUMENT_PARSED",
            "DOC-TECH",
            "Technical specification parsed; 18 obligations are tracked.",
        ),
        (
            "EVIDENCE_SEARCHED",
            DEMO_COMPANY_ID,
            "Evidence Registry matched 18 verified records to the bid.",
        ),
        (
            "ASSESSMENT_UPDATED",
            "R17",
            "R17 verified with three eligible CISSP-certified engineers.",
        ),
        (
            "OPERATIONAL_STATUS_CHANGED",
            DEMO_BID_ID,
            "Operational feasibility established as FEASIBLE.",
        ),
    ]
    for index, (event_type, entity_id, summary) in enumerate(initial_activity, start=1):
        session.add(
            ActivityEvent(
                id=f"ACT-SEED-{index}",
                tender_id=DEMO_BID_ID,
                event_type=event_type,
                actor="system",
                entity_id=entity_id,
                summary=summary,
                timestamp=datetime(2026, 8, 21, 4, 50 + index),
            )
        )

    session.commit()
    return tender


def reset_demo(session: Session) -> Tender:
    for model in (
        HumanApproval,
        ActivityEvent,
        ChangeEvent,
        TaskDependency,
        Task,
        Assessment,
        Requirement,
        Evidence,
        Employee,
        TenderDocument,
        Tender,
        Company,
    ):
        session.execute(delete(model))
    session.commit()
    return seed_demo(session)
