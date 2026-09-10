from datetime import date
from decimal import Decimal

import pytest
from app.company_profile import BusinessProfileIngestionError, ingest_business_profile
from app.tender_lab.extractor import extract_document
from app.tender_lab.schemas import DocumentExtractionResponse, DocumentPage


def _document(*pages: str, text_override: str | None = None) -> DocumentExtractionResponse:
    extracted_pages = [
        DocumentPage(page=index, text=text, character_count=len(text))
        for index, text in enumerate(pages, start=1)
    ]
    combined = "\n\n".join(
        f"[Page {page.page}]\n{page.text}" for page in extracted_pages if page.text
    )
    return DocumentExtractionResponse(
        filename="acra-business-profile.pdf",
        content_type="application/pdf",
        page_count=len(extracted_pages),
        character_count=sum(page.character_count for page in extracted_pages),
        text=text_override if text_override is not None else combined,
        pages=extracted_pages,
        truncated=False,
        warnings=[],
    )


def test_ingests_explicit_profile_fields_with_page_evidence():
    document = _document(
        """BUSINESS PROFILE
Entity Name: Lumen Analytics Pte. Ltd.
Unique Entity Number (UEN): 202012345K
Entity Type: EXEMPT PRIVATE COMPANY LIMITED BY SHARES
Company Status: Live Company
Date of Incorporation: 3 September 2020""",
        """Primary Business Activity
62011 - DEVELOPMENT OF SOFTWARE AND APPLICATIONS (EXCEPT GAMES)
Secondary SSIC Code: 62021
INFORMATION TECHNOLOGY CONSULTANCY
Paid-Up Capital: SGD 250,000.00""",
    )

    result = ingest_business_profile(document)

    assert result.source_type == "USER_SUPPLIED"
    assert result.verification_status == "NOT_OFFICIALLY_VERIFIED"
    assert result.entity_name.value == "Lumen Analytics Pte. Ltd."
    assert result.uen.value == "202012345K"
    assert result.entity_type.value == "EXEMPT PRIVATE COMPANY LIMITED BY SHARES"
    assert result.status.value == "Live Company"
    assert result.registration_or_incorporation_date.value is not None
    assert result.registration_or_incorporation_date.value.date == date(2020, 9, 3)
    assert result.registration_or_incorporation_date.value.kind == "INCORPORATION"
    assert result.primary_ssic.value is not None
    assert result.primary_ssic.value.code == "62011"
    assert result.primary_ssic.value.description == (
        "DEVELOPMENT OF SOFTWARE AND APPLICATIONS (EXCEPT GAMES)"
    )
    assert result.secondary_ssic.value is not None
    assert result.secondary_ssic.value.code == "62021"
    assert result.secondary_ssic.value.description == "INFORMATION TECHNOLOGY CONSULTANCY"
    assert result.paid_up_capital.value is not None
    assert result.paid_up_capital.value.amount == Decimal("250000.00")
    assert result.paid_up_capital.value.currency == "SGD"
    assert result.primary_ssic.sources[0].page == 2
    assert "Primary Business Activity" in result.primary_ssic.sources[0].excerpt
    assert all(
        field.confidence == "HIGH"
        for field in (
            result.entity_name,
            result.uen,
            result.entity_type,
            result.status,
            result.registration_or_incorporation_date,
            result.primary_ssic,
            result.secondary_ssic,
            result.paid_up_capital,
        )
    )


def test_missing_fields_are_null_and_require_review():
    result = ingest_business_profile(
        _document("Entity Name: Example Services\nUEN: 53456789A")
    )

    for field in (
        result.entity_type,
        result.status,
        result.registration_or_incorporation_date,
        result.primary_ssic,
        result.secondary_ssic,
        result.paid_up_capital,
    ):
        assert field.value is None
        assert field.confidence == "REVIEW"
        assert field.sources == []
        assert field.review_reason
    assert "6 profile field(s) require human review." in result.warnings


def test_consumes_actual_selectable_text_extractor_output():
    extracted = extract_document(
        filename="profile.txt",
        content_type="text/plain",
        raw=(
            b"Entity Name: Extracted Services Pte. Ltd.\n"
            b"Unique Entity Number (UEN): 201912345N\n"
            b"Date of Registration: 01/04/2019"
        ),
    )

    result = ingest_business_profile(extracted)

    assert result.source_document == "profile.txt"
    assert result.entity_name.value == "Extracted Services Pte. Ltd."
    assert result.uen.value == "201912345N"
    assert result.registration_or_incorporation_date.value is not None
    assert result.registration_or_incorporation_date.value.kind == "REGISTRATION"
    assert result.registration_or_incorporation_date.value.date == date(2019, 4, 1)
    assert result.entity_name.sources[0].page == 1


def test_ssic_description_without_explicit_code_requires_review():
    result = ingest_business_profile(
        _document("Primary Business Activity: SOFTWARE DEVELOPMENT")
    )

    assert result.primary_ssic.value is not None
    assert result.primary_ssic.value.code is None
    assert result.primary_ssic.value.description == "SOFTWARE DEVELOPMENT"
    assert result.primary_ssic.confidence == "REVIEW"
    assert "no five-digit SSIC code" in result.primary_ssic.review_reason


def test_conflicting_values_fail_closed_and_retain_both_sources():
    result = ingest_business_profile(
        _document(
            "Entity Name: Example Pte. Ltd.\nUEN: 202012345K",
            "Unique Entity Number: 202099999N",
        )
    )

    assert result.uen.value is None
    assert result.uen.confidence == "REVIEW"
    assert "Conflicting" in result.uen.review_reason
    assert [source.page for source in result.uen.sources] == [1, 2]


def test_invalid_labelled_values_are_not_returned_as_facts():
    result = ingest_business_profile(
        _document(
            """Entity Name: Example Pte. Ltd.
UEN: not-a-uen
Date of Registration: 31/02/2020
Paid-Up Capital: not available"""
        )
    )

    assert result.uen.value is None
    assert result.uen.confidence == "REVIEW"
    assert result.registration_or_incorporation_date.value is None
    assert result.registration_or_incorporation_date.confidence == "REVIEW"
    assert result.paid_up_capital.value is None
    assert result.paid_up_capital.confidence == "REVIEW"
    assert result.uen.sources[0].page == 1


def test_explicit_unknown_markers_are_null_review_values():
    result = ingest_business_profile(
        _document(
            """Entity Name: Example Pte. Ltd.
UEN: 202012345K
Entity Type: Not stated
Company Status: UNKNOWN
Secondary Business Activity: N/A"""
        )
    )

    for field in (result.entity_type, result.status, result.secondary_ssic):
        assert field.value is None
        assert field.confidence == "REVIEW"
        assert field.sources[0].page == 1


def test_profile_text_limits_match_tender_lab_company_schema():
    result = ingest_business_profile(
        _document(
            "\n".join(
                (
                    f"Entity Name: {'N' * 161}",
                    f"Entity Type: {'T' * 161}",
                    f"Company Status: {'S' * 121}",
                )
            )
        )
    )

    for field in (result.entity_name, result.entity_type, result.status):
        assert field.value is None
        assert field.confidence == "REVIEW"
        assert "could not be parsed safely" in field.review_reason


def test_oversized_normalized_values_fail_closed_instead_of_raising():
    result = ingest_business_profile(
        _document(
            "\n".join(
                (
                    f"Primary SSIC Code: 62011 {'D' * 501}",
                    "Paid-Up Capital: SGD 999999999999999999999999999999.00",
                )
            )
        )
    )

    assert result.primary_ssic.value is None
    assert result.primary_ssic.confidence == "REVIEW"
    assert result.paid_up_capital.value is None
    assert result.paid_up_capital.confidence == "REVIEW"


def test_epu_and_sca_grades_are_never_inferred_even_when_text_mentions_them():
    result = ingest_business_profile(
        _document(
            """Entity Name: Example Pte. Ltd.
UEN: 202012345K
Entity Type: Local Company
Company Status: Live
EPU Grade: S10
SCA Grade: L6"""
        )
    )

    assert result.epu_grade.value is None
    assert result.epu_grade.confidence == "REVIEW"
    assert result.epu_grade.sources == []
    assert "was not inferred" in result.epu_grade.review_reason
    assert result.sca_grade.value is None
    assert result.sca_grade.confidence == "REVIEW"
    assert any("neither grade is inferred" in boundary for boundary in result.boundaries)


def test_uses_per_page_extractor_text_not_forged_combined_text():
    result = ingest_business_profile(
        _document(
            "Entity Name: Real Supplied Name\nUEN: 202012345K",
            text_override="[Page 99]\nEntity Name: Forged Combined Name\nUEN: 202099999N",
        )
    )

    assert result.entity_name.value == "Real Supplied Name"
    assert result.uen.value == "202012345K"
    assert result.entity_name.sources[0].page == 1


def test_requires_existing_extractor_output_and_selectable_text():
    with pytest.raises(TypeError, match="DocumentExtractionResponse"):
        ingest_business_profile({"pages": []})  # type: ignore[arg-type]

    blank = _document("")
    with pytest.raises(BusinessProfileIngestionError, match="No selectable text"):
        ingest_business_profile(blank)

    long_name = _document("Entity Name: Example Pte. Ltd.").model_copy(
        update={"filename": f"{'x' * 256}.pdf"}
    )
    with pytest.raises(BusinessProfileIngestionError, match="filename must be"):
        ingest_business_profile(long_name)
