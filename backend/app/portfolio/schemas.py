from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

OperationalState = Literal["FEASIBLE", "RECOVERABLE", "BLOCKED", "UNCERTAIN"]
DecisionRoute = Literal["BID", "RECOVER", "CLARIFY", "PARTNER", "WALK_AWAY"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CapabilityPool(StrictModel):
    capability: str = Field(min_length=2, max_length=80)
    label: str = Field(min_length=2, max_length=120)
    proven_count: int = Field(ge=0)
    potential_count: int = Field(ge=0)
    provenance: str = Field(min_length=2, max_length=240)

    @model_validator(mode="after")
    def potential_includes_proven(self) -> "CapabilityPool":
        if self.potential_count < self.proven_count:
            raise ValueError("potential_count must be greater than or equal to proven_count")
        return self


class CapabilityDemand(StrictModel):
    capability: str = Field(min_length=2, max_length=80)
    count: int | None = Field(default=None, ge=1)
    starts_at: datetime
    ends_at: datetime
    source: str = Field(min_length=2, max_length=240)

    @field_validator("starts_at", "ends_at")
    @classmethod
    def normalise_to_utc_naive(cls, value: datetime) -> datetime:
        """Keep interval arithmetic deterministic across mixed ISO-8601 offsets."""
        if value.tzinfo is None:
            return value
        return value.astimezone(UTC).replace(tzinfo=None)

    @model_validator(mode="after")
    def valid_window(self) -> "CapabilityDemand":
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be later than starts_at")
        return self


class PortfolioOpportunity(StrictModel):
    id: str = Field(min_length=2, max_length=80)
    title: str = Field(min_length=2, max_length=180)
    agency: str = Field(min_length=2, max_length=120)
    reference_number: str = Field(min_length=2, max_length=80)
    stage: Literal["ACTIVE_BID", "DELIVERY_COMMITMENT", "QUALIFYING", "WATCHLIST"]
    demands: list[CapabilityDemand] = Field(min_length=1, max_length=32)
    synthetic: bool = True


class PortfolioSimulationRequest(StrictModel):
    capabilities: list[CapabilityPool] = Field(min_length=1, max_length=20)
    opportunities: list[PortfolioOpportunity] = Field(min_length=1, max_length=8)
    scenario_label: str = Field(default="Portfolio scenario", min_length=2, max_length=160)

    @model_validator(mode="after")
    def unique_ids_and_capabilities(self) -> "PortfolioSimulationRequest":
        capability_ids = [item.capability for item in self.capabilities]
        if len(capability_ids) != len(set(capability_ids)):
            raise ValueError("capability identifiers must be unique")
        opportunity_ids = [item.id.casefold() for item in self.opportunities]
        if len(opportunity_ids) != len(set(opportunity_ids)):
            raise ValueError("opportunity identifiers must be unique ignoring case")
        demanded = {
            demand.capability
            for opportunity in self.opportunities
            for demand in opportunity.demands
        }
        missing = sorted(demanded - set(capability_ids))
        if missing:
            raise ValueError(f"No capability pool is configured for: {', '.join(missing)}")
        return self


class PeakDemandReference(StrictModel):
    opportunity_id: str
    demand_index: int = Field(ge=0)


class PeakWindow(StrictModel):
    window_start: datetime
    window_end: datetime
    active_opportunity_ids: list[str]
    known_demand: int = Field(ge=0)
    minimum_demand: int = Field(ge=0)
    uncertain_demand: bool


class CapabilitySimulationResult(StrictModel):
    capability: str
    label: str
    proven_count: int = Field(ge=0)
    potential_count: int = Field(ge=0)
    peak_demand: int | None = Field(default=None, ge=0)
    minimum_peak_demand: int = Field(ge=0)
    shortfall: int | None = Field(default=None, ge=0)
    minimum_shortfall: int = Field(ge=0)
    evidence_gap: int | None = Field(default=None, ge=0)
    minimum_evidence_gap: int = Field(ge=0)
    state: OperationalState
    active_opportunity_ids: list[str]
    peak_demand_refs: list[PeakDemandReference]
    peak_windows: list[PeakWindow]
    window_start: datetime | None
    window_end: datetime | None
    uncertain_demand: bool
    uncertain_opportunity_ids: list[str]
    provenance: str


class PortfolioCalculation(StrictModel):
    rule: str
    precedence: list[OperationalState]


class PortfolioStrategyRoute(StrictModel):
    id: str
    route: DecisionRoute
    title: str
    resulting_state: OperationalState
    included_opportunity_ids: list[str]
    tradeoff: str
    requires_human_decision: bool


class CapabilityRoadmapItem(StrictModel):
    priority: int = Field(ge=1)
    capability: str
    opportunity_ids: list[str]
    opportunities_affected: int = Field(ge=1)
    requirement_count: int = Field(ge=1)
    earliest_window_start: datetime
    sources: list[str]
    gap_type: Literal["ADDITIONAL_CAPACITY_REQUIRED", "EVIDENCE_OR_AVAILABILITY"]
    known_gap: int = Field(ge=1)
    action: str
    effect: str
    basis: str


class PortfolioSimulationResponse(StrictModel):
    scenario_label: str
    state: OperationalState
    reason: str
    capabilities: list[CapabilitySimulationResult]
    constrained_capabilities: list[str]
    opportunities: list[PortfolioOpportunity]
    calculation: PortfolioCalculation
    routes: list[PortfolioStrategyRoute]
    capability_roadmap: list[CapabilityRoadmapItem]
