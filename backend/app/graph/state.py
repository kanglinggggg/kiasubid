from typing import TypedDict


class BidState(TypedDict, total=False):
    session_id: str
    tender_id: str
    current_document_ids: list[str]
    changed_requirement_id: str
    previous_requirement_id: str
    requirements: list[dict]
    evidence: list[dict]
    assessments: list[dict]
    tasks: list[dict]
    change_events: list[dict]
    interpretation_mode: str
    recovery_candidate_ids: list[str]
    operational_status: str
    previous_operational_status: str
    critical_gate_summary: dict[str, int]
    submission_coverage: float
    deadline_risk: str
    activity_events: list[dict]
    human_action_required: bool
    errors: list[str]
