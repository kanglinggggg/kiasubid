"""Cost-bounded Bedrock smoke and canonical R17 validation for an approved sandbox."""

import json
from uuid import uuid4

from app.config import Settings
from app.database import Base
from app.demo.seed import DEMO_BID_ID, seed_demo
from app.graph.workflow import CORRIGENDUM_TEXT, build_corrigendum_graph
from app.llm.interpreter import TenderInterpreter
from app.llm.schemas import RequirementInterpretationRequest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


def run() -> dict[str, object]:
    app_settings = Settings()
    if app_settings.llm_provider != "bedrock":
        raise RuntimeError("LLM_PROVIDER must be bedrock for the AWS post-approval check.")
    if app_settings.aws_default_region != "us-east-1":
        raise RuntimeError("AWS_DEFAULT_REGION must be us-east-1 for the hackathon sandbox.")
    if not app_settings.bedrock_configured or not app_settings.bedrock_model_id:
        raise RuntimeError("BEDROCK_MODEL_ID must be an explicitly selected on-demand model.")

    interpreter = TenderInterpreter(app_settings=app_settings)
    smoke_text = "The tenderer must submit a signed Form of Tender."
    smoke = interpreter.interpret_requirements(
        RequirementInterpretationRequest(
            document_name="bedrock-smoke.txt",
            page=1,
            section="Submission documents",
            text=smoke_text,
            stable_key_hint="SMOKE-1",
        ),
        allow_fallback=False,
    )
    if smoke.mode != "BEDROCK" or not smoke.result.requirements:
        raise RuntimeError("The minimal structured interpretation was not produced by Bedrock.")
    smoke_requirement = smoke.result.requirements[0]
    if smoke_requirement.source.snippet not in smoke_text:
        raise RuntimeError("Bedrock smoke output failed exact source-provenance validation.")

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    try:
        with factory() as session:
            seed_demo(session)
        workflow = build_corrigendum_graph(
            session_factory=factory,
            interpretation_service=interpreter,
            corrigendum_text=CORRIGENDUM_TEXT,
        )
        state = workflow(
            {
                "session_id": f"aws-validation-{uuid4().hex[:8]}",
                "tender_id": DEMO_BID_ID,
                "errors": [],
            }
        )
    finally:
        engine.dispose()

    expected = {
        "previous_operational_status": "FEASIBLE",
        "operational_status": "RECOVERABLE",
        "interpretation_mode": "BEDROCK",
        "changed_requirement_id": "REQ-R17-V2",
        "previous_requirement_id": "REQ-R17-V1",
    }
    mismatches = {
        key: {"expected": value, "actual": state.get(key)}
        for key, value in expected.items()
        if state.get(key) != value
    }
    gate_summary = state.get("critical_gate_summary") or {}
    if gate_summary.get("verified") != 7 or gate_summary.get("total") != 8:
        mismatches["critical_gate_summary"] = {
            "expected": {"verified": 7, "total": 8},
            "actual": gate_summary,
        }
    if mismatches:
        raise RuntimeError(f"R17 Bedrock workflow validation failed: {mismatches}")

    return {
        "provider": "BEDROCK",
        "model_id": app_settings.bedrock_model_id,
        "region": app_settings.aws_default_region,
        "minimal_structured_output": {
            "status": "PASS",
            "requirement_type": smoke_requirement.requirement_type,
            "gate_type": smoke_requirement.gate_type,
            "interpretation_status": smoke_requirement.interpretation_status,
            "source_provenance": "PASS",
        },
        "r17_corrigendum_path": {
            "status": "PASS",
            "input": "natural-language corrigendum",
            "affected_requirement": "R17",
            "minimum_count": {"old": 3, "new": 4},
            "operational_transition": "FEASIBLE -> RECOVERABLE",
            "critical_gates": "8/8 -> 7/8",
        },
    }


def main() -> None:
    print(json.dumps(run(), indent=2))


if __name__ == "__main__":
    main()
