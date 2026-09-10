from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AwardRecord(StrictModel):
    tender_no: str
    tender_description: str
    agency: str
    award_date: str
    supplier_name: str
    awarded_amt_sgd: float = Field(gt=0)


class AwardSummary(StrictModel):
    sample_count: int = Field(ge=0)
    distinct_tenders: int = Field(ge=0)
    median_sgd: float | None
    lower_quartile_sgd: float | None
    upper_quartile_sgd: float | None
    minimum_sgd: float | None
    maximum_sgd: float | None


class PublicDataProvenance(StrictModel):
    status: Literal["LIVE_PUBLIC", "CACHED_PUBLIC", "UNAVAILABLE"]
    publisher: str
    dataset_title: str
    dataset_id: str
    source_url: str
    retrieved_at: str
    coverage: str
    methodology: list[str]
    limitation: str


class SupplierPattern(StrictModel):
    supplier_name: str
    award_rows: int = Field(ge=1)
    total_awarded_sgd: float = Field(gt=0)
    row_share_percent: float = Field(ge=0, le=100)
    value_share_percent: float = Field(ge=0, le=100)


class AnnualAwardPattern(StrictModel):
    year: int = Field(ge=2000, le=2100)
    award_rows: int = Field(ge=1)
    median_sgd: float = Field(gt=0)
    total_awarded_sgd: float = Field(gt=0)


class AwardIntelligence(StrictModel):
    sample_strength: Literal["NO_SAMPLE", "THIN", "DIRECTIONAL"]
    date_start: str | None
    date_end: str | None
    supplier_count: int = Field(ge=0)
    recurring_supplier_count: int = Field(ge=0)
    price_dispersion_percent: float | None = Field(default=None, ge=0)
    top_suppliers: list[SupplierPattern]
    annual_patterns: list[AnnualAwardPattern]
    observations: list[str]
    boundary: str


class AwardContextResponse(StrictModel):
    query: str
    agency: str | None
    source_total_matches: int
    excluded_rows: int
    summary: AwardSummary
    records: list[AwardRecord]
    provenance: PublicDataProvenance
    intelligence: AwardIntelligence
