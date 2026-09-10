from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Confidence = Literal["HIGH", "REVIEW"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceExcerpt(StrictModel):
    page: int = Field(ge=1)
    excerpt: str = Field(min_length=1, max_length=800)


class ExtractedField[T](StrictModel):
    """A value and the selectable-text evidence that supports it."""

    value: T | None = None
    confidence: Confidence
    sources: list[SourceExcerpt] = Field(default_factory=list, max_length=3)
    review_reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def enforce_fail_closed_contract(self) -> "ExtractedField[T]":
        if self.value is None and self.confidence != "REVIEW":
            raise ValueError("A null extracted value must have REVIEW confidence")
        if self.value is not None and not self.sources:
            raise ValueError("A non-null extracted value must have selectable-text evidence")
        if self.confidence == "HIGH" and (self.value is None or not self.sources):
            raise ValueError("HIGH confidence requires a value and selectable-text evidence")
        if self.confidence == "REVIEW" and not self.review_reason:
            raise ValueError("REVIEW confidence requires a review_reason")
        return self


class RegistrationDate(StrictModel):
    date: date
    kind: Literal["REGISTRATION", "INCORPORATION"]


class SSICClassification(StrictModel):
    code: str | None = Field(default=None, pattern=r"^\d{5}$")
    description: str | None = Field(default=None, min_length=2, max_length=500)

    @model_validator(mode="after")
    def require_explicit_classification_content(self) -> "SSICClassification":
        if self.code is None and self.description is None:
            raise ValueError("An SSIC classification requires a code or description")
        return self


class PaidUpCapital(StrictModel):
    amount: Decimal = Field(ge=0, max_digits=24, decimal_places=2)
    currency: str | None = Field(default=None, min_length=3, max_length=3)


class BusinessProfileIngestionResult(StrictModel):
    source_type: Literal["USER_SUPPLIED"] = "USER_SUPPLIED"
    verification_status: Literal["NOT_OFFICIALLY_VERIFIED"] = "NOT_OFFICIALLY_VERIFIED"
    source_document: str = Field(min_length=1, max_length=255)
    entity_name: ExtractedField[str]
    uen: ExtractedField[str]
    entity_type: ExtractedField[str]
    status: ExtractedField[str]
    registration_or_incorporation_date: ExtractedField[RegistrationDate]
    primary_ssic: ExtractedField[SSICClassification]
    secondary_ssic: ExtractedField[SSICClassification]
    paid_up_capital: ExtractedField[PaidUpCapital]
    epu_grade: ExtractedField[str]
    sca_grade: ExtractedField[str]
    warnings: list[str]
    boundaries: list[str]
