from pydantic import BaseModel, Field


class HumanApprovalRequest(BaseModel):
    approved_by: str = Field(min_length=2, max_length=100)
    note: str | None = Field(default=None, max_length=500)


class EvidenceVerificationRequest(BaseModel):
    verified_by: str = Field(min_length=2, max_length=100)
