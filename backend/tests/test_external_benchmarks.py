import json
from pathlib import Path

import pytest
from app.database import Base
from app.models import (
    Assessment,
    Company,
    Employee,
    Evidence,
    Requirement,
    Task,
    Tender,
    TenderDocument,
)
from app.services.assessment import assess_requirement
from app.services.metrics import derive_operational_status
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from tests.benchmarks.schema import BenchmarkCase

CASES_DIRECTORY = Path(__file__).parent / "benchmarks" / "cases"


def load_benchmark_cases() -> list[BenchmarkCase]:
    cases: list[BenchmarkCase] = []
    for path in sorted(CASES_DIRECTORY.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        records = payload if isinstance(payload, list) else [payload]
        cases.extend(BenchmarkCase.model_validate(record) for record in records)
    if not cases:
        raise RuntimeError(f"No benchmark cases found in {CASES_DIRECTORY}")
    return cases


BENCHMARK_CASES = load_benchmark_cases()


@pytest.mark.parametrize("case", BENCHMARK_CASES, ids=lambda case: case.id)
def test_external_benchmark_case(case: BenchmarkCase):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        company = Company(
            id="BENCHMARK-COMPANY",
            name="Benchmark Supplier",
            uen="BENCHMARK",
            industry="Benchmark",
            employee_count=len(case.employees),
            annual_revenue="N/A",
        )
        tender = Tender(
            id="BENCHMARK-BID",
            company_id=company.id,
            title=case.description,
            agency="Benchmark source",
            reference_number=case.id,
            closing_at=case.tender_closing_at,
            source_type=case.source,
        )
        document = TenderDocument(
            id="BENCHMARK-DOC",
            tender_id=tender.id,
            filename=f"{case.id}.txt",
            document_type="OTHER",
            version=1,
        )
        requirement = Requirement(
            id=f"REQ-{case.requirement.stable_key}-V1",
            stable_key=case.requirement.stable_key,
            tender_id=tender.id,
            version=1,
            text=case.requirement.text,
            requirement_type=case.requirement.requirement_type,
            gate_type=case.requirement.gate_type,
            source_document_id=document.id,
            source_page=case.requirement.source_page,
            source_section=case.requirement.source_section,
            source_snippet=case.requirement.text,
            rule_config=case.requirement.rule_config,
        )
        session.add_all([company, tender, document, requirement])
        session.add_all(
            Employee(
                id=employee.id,
                company_id=company.id,
                name=employee.name,
                role="Benchmark employee",
                employment_status="ACTIVE",
                availability_status=employee.availability_status,
                experience_years=employee.experience_years,
            )
            for employee in case.employees
        )
        session.add_all(
            Evidence(
                id=item.id,
                company_id=company.id,
                type=item.type,
                title=item.title,
                subject_type="EMPLOYEE",
                subject_id=item.subject_id,
                details=item.details,
                valid_until=item.valid_until,
                verification_status=item.verification_status,
            )
            for item in case.evidence
        )
        session.flush()

        result = assess_requirement(session, requirement)
        session.add(
            Assessment(
                id=f"ASM-{case.requirement.stable_key}-V1",
                requirement_id=requirement.id,
                requirement_version=1,
                status=result.status.value,
                evidence_ids=result.evidence_ids,
                reason_summary=result.reason,
                assessment_method="RULE",
            )
        )
        session.add_all(
            Task(
                id=task.id,
                tender_id=tender.id,
                requirement_id=requirement.id,
                title=f"Benchmark recovery task {task.id}",
                description="Normalized external benchmark recovery task.",
                owner="Benchmark",
                status=task.status,
                priority="CRITICAL",
                due_at=task.due_at,
                latest_safe_at=task.latest_safe_at,
                estimated_duration_hours=task.estimated_duration_hours,
                recovery_path=True,
            )
            for task in case.recovery_tasks
        )
        session.flush()

        assert result.status.value == case.expected.assessment_status
        assert len(result.usable_employee_ids) == case.expected.usable_employee_count
        assert len(result.recovery_candidate_ids) == case.expected.recovery_candidate_count
        assert derive_operational_status(session, tender).value == case.expected.operational_status
