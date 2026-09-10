from typing import Literal

from pydantic import Field, model_validator

from app.tender_lab.schemas import StrictModel, TenderLabRequest

AgentTask = Literal["COMPLIANCE", "COMMERCIAL", "TIMELINE"]
AgentMode = Literal["BEDROCK", "GROQ", "DETERMINISTIC_FALLBACK"]
AgentRunStatus = Literal["COMPLETED", "REVISED", "FALLBACK", "NEEDS_REVIEW"]


class AgentLoopRequest(StrictModel):
    tender: TenderLabRequest
    max_revision_rounds: Literal[0, 1] = 1


class AgentEvidence(StrictModel):
    id: str = Field(pattern=r"^(?:TENDER|PROPOSAL|FACT|POLICY)-[A-Z0-9-]+$")
    kind: Literal["TENDER", "PROPOSAL", "WORKSPACE_FACT", "PUBLIC_POLICY_CONTEXT"]
    label: str = Field(min_length=1, max_length=200)
    location: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=1_200)
    source_url: str | None = Field(default=None, max_length=1_000)


class PlannedAgentTask(StrictModel):
    agent: AgentTask
    objective: str = Field(min_length=1, max_length=500)
    focus: list[str] = Field(default_factory=list, max_length=8)


class AgentPlan(StrictModel):
    mission: str = Field(min_length=1, max_length=700)
    tasks: list[PlannedAgentTask] = Field(min_length=1, max_length=3)
    success_criteria: list[str] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def task_names_are_unique(self) -> "AgentPlan":
        names = [item.agent for item in self.tasks]
        if len(names) != len(set(names)):
            raise ValueError("planner tasks must be unique")
        return self


class AgentFinding(StrictModel):
    id: str = Field(pattern=r"^(?:CMP|COM|TIM)-[A-Z0-9-]{2,40}$")
    title: str = Field(min_length=1, max_length=200)
    status: Literal["SUPPORTED", "GAP", "UNCERTAIN"]
    severity: Literal["BLOCKER", "RISK", "INFO"]
    claim: str = Field(min_length=1, max_length=1_000)
    evidence_ids: list[str] = Field(min_length=1, max_length=6)
    evidence_gap: str | None = Field(default=None, max_length=700)
    downstream_effects: list[str] = Field(default_factory=list, max_length=6)
    recommended_action: str = Field(min_length=1, max_length=700)
    confidence: Literal["HIGH", "MEDIUM", "LOW"]


class SpecialistOutput(StrictModel):
    agent: AgentTask
    summary: str = Field(min_length=1, max_length=1_000)
    findings: list[AgentFinding] = Field(min_length=1, max_length=8)
    assumptions: list[str] = Field(default_factory=list, max_length=8)
    handoff: str = Field(min_length=1, max_length=700)

    @model_validator(mode="after")
    def finding_ids_are_unique(self) -> "SpecialistOutput":
        identifiers = [item.id for item in self.findings]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("specialist finding ids must be unique")
        return self


class CriticFindingReview(StrictModel):
    finding_id: str = Field(pattern=r"^(?:CMP|COM|TIM)-[A-Z0-9-]{2,40}$")
    verdict: Literal["PASS", "REVISE"]
    feedback: str = Field(min_length=1, max_length=700)


class CriticOutput(StrictModel):
    overall_verdict: Literal["PASS", "REVISE"]
    finding_reviews: list[CriticFindingReview] = Field(default_factory=list, max_length=24)
    cross_agent_conflicts: list[str] = Field(default_factory=list, max_length=8)
    human_checks: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def reviewed_finding_ids_are_unique(self) -> "CriticOutput":
        identifiers = [item.finding_id for item in self.finding_reviews]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("critic finding ids must be unique")
        return self


class AgentExecution(StrictModel):
    agent_id: Literal["PLANNER", "COMPLIANCE", "COMMERCIAL", "TIMELINE", "CRITIC"]
    label: str
    status: AgentRunStatus
    mode: AgentMode
    model_id: str | None = None
    attempts: int = Field(ge=0)
    revision_count: int = Field(default=0, ge=0, le=1)
    duration_ms: float = Field(default=0, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    detail: str


class SpecialistResult(StrictModel):
    agent: AgentTask
    output: SpecialistOutput
    critic_verdict: Literal["PASS", "REVISE"]
    critic_feedback: list[str] = Field(default_factory=list)
    revision_count: int = Field(default=0, ge=0, le=1)


class HumanDecisionPacket(StrictModel):
    readiness: Literal["READY_FOR_HUMAN_REVIEW", "NEEDS_EVIDENCE", "HOLD"]
    headline: str
    grounded_finding_ids: list[str]
    unresolved_finding_ids: list[str]
    decisions_required: list[str]
    next_step: str
    boundary: str


class AgentLoopResponse(StrictModel):
    source_type: Literal["USER_SUPPLIED", "SYNTHETIC_SAMPLE"]
    provider_state: Literal["LIVE", "MIXED", "FALLBACK"]
    model_id: str | None = None
    loop_iterations: int = Field(ge=1, le=2)
    plan: AgentPlan
    specialists: list[SpecialistResult]
    critic: CriticOutput
    decision: HumanDecisionPacket
    executions: list[AgentExecution]
    evidence_register: list[AgentEvidence]
    fallback_reasons: list[str]
    boundaries: list[str]
