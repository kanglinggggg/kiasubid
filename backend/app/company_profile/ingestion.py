import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app.company_profile.schemas import (
    BusinessProfileIngestionResult,
    ExtractedField,
    PaidUpCapital,
    RegistrationDate,
    SourceExcerpt,
    SSICClassification,
)
from app.tender_lab.schemas import DocumentExtractionResponse

MAX_ENTITY_NAME_LENGTH = 160
MAX_ENTITY_TYPE_LENGTH = 160
MAX_STATUS_LENGTH = 120
MAX_SOURCE_DOCUMENT_LENGTH = 255


class BusinessProfileIngestionError(ValueError):
    """Raised when extractor output cannot be safely ingested."""


@dataclass(frozen=True)
class _Candidate:
    raw_value: str
    label: str
    source: SourceExcerpt


_ENTITY_NAME_LABELS = (
    "entity name",
    "company name",
    "business name",
    "name of company",
    "name of business",
    "name",
)
_UEN_LABELS = (
    "registration no. / unique entity number",
    "registration no / unique entity number",
    "registration number / unique entity number",
    "unique entity number (uen)",
    "unique entity number",
    "registration number",
    "registration no.",
    "registration no",
    "uen",
)
_ENTITY_TYPE_LABELS = (
    "entity type",
    "company type",
    "business type",
    "type of entity",
)
_STATUS_LABELS = (
    "entity status",
    "company status",
    "business status",
    "status",
)
_REGISTRATION_DATE_LABELS = (
    "date of registration",
    "registration date",
)
_INCORPORATION_DATE_LABELS = (
    "date of incorporation",
    "incorporation date",
)
_PRIMARY_SSIC_LABELS = (
    "primary ssic code",
    "primary ssic",
    "primary business activity",
    "primary activity",
    "principal activity",
)
_SECONDARY_SSIC_LABELS = (
    "secondary ssic code",
    "secondary ssic",
    "secondary business activity",
    "secondary activity",
)
_PAID_UP_CAPITAL_LABELS = (
    "total paid-up capital",
    "total paid up capital",
    "paid-up share capital",
    "paid up share capital",
    "paid-up capital",
    "paid up capital",
)

_FIELD_LABELS = (
    _ENTITY_NAME_LABELS
    + _UEN_LABELS
    + _ENTITY_TYPE_LABELS
    + _STATUS_LABELS
    + _REGISTRATION_DATE_LABELS
    + _INCORPORATION_DATE_LABELS
    + _PRIMARY_SSIC_LABELS
    + _SECONDARY_SSIC_LABELS
    + _PAID_UP_CAPITAL_LABELS
)

# These headings delimit a value block but are deliberately not extracted by this slice.
_OTHER_BOUNDARY_LABELS = (
    "former name",
    "former name if any",
    "status date",
    "date of status",
    "registered office address",
    "principal place of business",
    "business address",
    "address",
    "date of address",
    "financial year end",
    "date of last annual general meeting",
    "date of last agm",
    "date of last annual return",
    "issued share capital",
    "share capital",
    "number of officers",
    "business constitution",
    "expiry date",
)

_PLACEHOLDERS = {
    "-",
    "--",
    "n/a",
    "na",
    "nil",
    "none",
    "not applicable",
    "not available",
    "not known",
    "not provided",
    "not stated",
    "unavailable",
    "unknown",
}

_DATE_PATTERNS = (
    (re.compile(r"\b\d{4}-\d{2}-\d{2}\b"), ("%Y-%m-%d",)),
    (re.compile(r"\b\d{1,2}/\d{1,2}/\d{4}\b"), ("%d/%m/%Y",)),
    (re.compile(r"\b\d{1,2}-\d{1,2}-\d{4}\b"), ("%d-%m-%Y",)),
    (
        re.compile(r"\b\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}\b"),
        ("%d %B %Y", "%d %b %Y"),
    ),
)
_SSIC_CODE = re.compile(r"(?<!\d)(\d{5})(?!\d)")
_AMOUNT = re.compile(r"(?<![\w.])(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?(?![\w.])")

_CURRENCIES = (
    (re.compile(r"\b(?:SGD|SINGAPORE\s+DOLLARS?)\b|S\$", re.I), "SGD"),
    (re.compile(r"\b(?:USD|US\s+DOLLARS?|UNITED\s+STATES\s+DOLLARS?)\b|US\$", re.I), "USD"),
    (re.compile(r"\b(?:EUR|EUROS?)\b|€", re.I), "EUR"),
    (re.compile(r"\b(?:GBP|POUNDS?\s+STERLING)\b|£", re.I), "GBP"),
    (re.compile(r"\b(?:MYR|MALAYSIAN\s+RINGGIT)\b", re.I), "MYR"),
)


def _normalise_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _is_placeholder(value: str) -> bool:
    return _normalise_space(value).casefold().strip(".: ") in _PLACEHOLDERS


def _split_label(line: str, aliases: tuple[str, ...]) -> tuple[str, str | None] | None:
    cleaned = _normalise_space(line)
    folded = cleaned.casefold()
    for alias in sorted(aliases, key=len, reverse=True):
        alias_folded = alias.casefold()
        if folded == alias_folded:
            return alias, None
        if not folded.startswith(alias_folded):
            continue
        remainder = cleaned[len(alias) :]
        if remainder.startswith((":", "：", "=")):
            return alias, remainder[1:].strip() or None
        if re.match(r"^\s+[–—-]\s+", remainder):
            return alias, re.sub(r"^\s+[–—-]\s+", "", remainder, count=1).strip() or None
        # Distinctive multi-word labels are sometimes emitted as a flattened table row.
        if alias not in {"name", "status"} and remainder.startswith(" "):
            return alias, remainder.strip() or None
    return None


def _looks_like_boundary(line: str) -> bool:
    aliases = _FIELD_LABELS + _OTHER_BOUNDARY_LABELS
    return _split_label(line, aliases) is not None


def _collect_candidates(
    document: DocumentExtractionResponse,
    aliases: tuple[str, ...],
    *,
    following_lines: int,
) -> list[_Candidate]:
    candidates: list[_Candidate] = []
    for page in document.pages:
        lines = [line.strip() for line in page.text.splitlines() if line.strip()]
        for index, line in enumerate(lines):
            matched = _split_label(line, aliases)
            if matched is None:
                continue
            label, inline_value = matched
            values: list[str] = []
            if inline_value:
                values.append(inline_value)
            cursor = index + 1
            while cursor < len(lines) and len(values) < following_lines:
                next_line = lines[cursor]
                if _looks_like_boundary(next_line):
                    break
                values.append(next_line)
                cursor += 1
            raw_value = _normalise_space(" ".join(values))
            source_lines = [line]
            source_lines.extend(lines[index + 1 : cursor])
            excerpt = "\n".join(source_lines)
            candidates.append(
                _Candidate(
                    raw_value=raw_value,
                    label=label,
                    source=SourceExcerpt(page=page.page, excerpt=excerpt[:800]),
                )
            )
    return candidates


def _sources(candidates: list[_Candidate]) -> list[SourceExcerpt]:
    result: list[SourceExcerpt] = []
    seen: set[tuple[int, str]] = set()
    for candidate in candidates:
        key = (candidate.source.page, candidate.source.excerpt)
        if key not in seen:
            result.append(candidate.source)
            seen.add(key)
        if len(result) == 3:
            break
    return result


def _missing(field_name: str) -> ExtractedField:
    return ExtractedField(
        value=None,
        confidence="REVIEW",
        sources=[],
        review_reason=(
            f"No explicit {field_name} label and value were found in the supplied selectable text."
        ),
    )


def _resolve[TValue](
    *,
    field_name: str,
    candidates: list[_Candidate],
    parse: Callable[[_Candidate], TValue | None],
    key: Callable[[TValue], object],
) -> ExtractedField[TValue]:
    if not candidates:
        return _missing(field_name)

    parsed: list[tuple[_Candidate, TValue]] = []
    for candidate in candidates:
        if not candidate.raw_value or _is_placeholder(candidate.raw_value):
            continue
        try:
            value = parse(candidate)
        except ValueError:
            # Pydantic-normalized sub-values can reject excessive precision or length. Those are
            # untrusted source-data failures, so keep them at field-level REVIEW instead of leaking
            # an internal validation error through the upload endpoint.
            value = None
        if value is not None:
            parsed.append((candidate, value))

    if not parsed:
        return ExtractedField(
            value=None,
            confidence="REVIEW",
            sources=_sources(candidates),
            review_reason=f"The labelled {field_name} value is empty or could not be parsed safely.",
        )

    unique: dict[object, tuple[_Candidate, TValue]] = {}
    for candidate, value in parsed:
        unique.setdefault(key(value), (candidate, value))
    if len(unique) > 1:
        return ExtractedField(
            value=None,
            confidence="REVIEW",
            sources=_sources([candidate for candidate, _ in parsed]),
            review_reason=f"Conflicting labelled {field_name} values require human review.",
        )

    selected_candidate, selected_value = next(iter(unique.values()))
    invalid_count = len(candidates) - len(parsed)
    if invalid_count:
        return ExtractedField(
            value=selected_value,
            confidence="REVIEW",
            sources=_sources(candidates),
            review_reason=(
                f"A labelled {field_name} value was parsed, but another occurrence was empty or invalid."
            ),
        )
    return ExtractedField(
        value=selected_value,
        confidence="HIGH",
        sources=[selected_candidate.source],
        review_reason=None,
    )


def _text(candidate: _Candidate, *, max_length: int) -> str | None:
    value = _normalise_space(candidate.raw_value).strip(" :")
    if not value or len(value) > max_length:
        return None
    return value


def _uen(candidate: _Candidate) -> str | None:
    value = re.sub(r"[\s-]", "", candidate.raw_value).upper()
    if not re.fullmatch(r"[A-Z0-9]{9,10}", value):
        return None
    if not any(character.isdigit() for character in value) or not value[-1].isalpha():
        return None
    return value


def _date(candidate: _Candidate) -> RegistrationDate | None:
    matches: list[date] = []
    for pattern, formats in _DATE_PATTERNS:
        for raw_match in pattern.findall(candidate.raw_value):
            for format_string in formats:
                try:
                    matches.append(datetime.strptime(raw_match, format_string).date())
                    break
                except ValueError:
                    continue
    unique = list(dict.fromkeys(matches))
    if len(unique) != 1:
        return None
    kind = "INCORPORATION" if candidate.label in _INCORPORATION_DATE_LABELS else "REGISTRATION"
    return RegistrationDate(date=unique[0], kind=kind)


def _ssic(candidate: _Candidate) -> SSICClassification | None:
    codes = list(dict.fromkeys(_SSIC_CODE.findall(candidate.raw_value)))
    if len(codes) > 1:
        return None

    description = candidate.raw_value
    description = re.sub(
        r"\b(?:SSIC\s+CODE|SSIC|CODE)\b\s*[:：=-]?",
        " ",
        description,
        flags=re.I,
    )
    if codes:
        description = re.sub(rf"(?<!\d){re.escape(codes[0])}(?!\d)", " ", description)
    description = _normalise_space(description).strip("-–—:;,. ")
    if _is_placeholder(description):
        description = ""
    if not codes and not description:
        return None
    return SSICClassification(code=codes[0] if codes else None, description=description or None)


def _currency(value: str) -> str | None:
    matches = {code for pattern, code in _CURRENCIES if pattern.search(value)}
    return next(iter(matches)) if len(matches) == 1 else None


def _decimal_values(value: str) -> list[Decimal]:
    result: list[Decimal] = []
    for match in _AMOUNT.findall(value):
        try:
            parsed = Decimal(match.replace(",", ""))
        except InvalidOperation:
            continue
        if parsed not in result:
            result.append(parsed)
    return result


def _capital(candidate: _Candidate) -> PaidUpCapital | None:
    lines = [line.strip() for line in candidate.raw_value.splitlines() if line.strip()]
    prioritized: list[Decimal] = []
    for line in lines:
        if re.search(r"\bamount\b", line, re.I) or _currency(line):
            prioritized.extend(_decimal_values(line))
    amounts = list(dict.fromkeys(prioritized)) or _decimal_values(candidate.raw_value)
    if len(amounts) != 1:
        return None
    return PaidUpCapital(amount=amounts[0], currency=_currency(candidate.raw_value))


def _review_qualification(scheme: str) -> ExtractedField[str]:
    return ExtractedField(
        value=None,
        confidence="REVIEW",
        sources=[],
        review_reason=(
            f"{scheme} grade is not established by an ACRA Business Profile and was not inferred. "
            "Separate scheme-specific evidence is required."
        ),
    )


def ingest_business_profile(
    document: DocumentExtractionResponse,
) -> BusinessProfileIngestionResult:
    """Parse explicit ACRA-profile fields from existing selectable-text extractor output.

    This function performs no I/O, OCR, network lookup, or official verification. It only consumes
    the per-page text already returned by ``app.tender_lab.extractor.extract_document``.
    """
    if not isinstance(document, DocumentExtractionResponse):
        raise TypeError("document must be a DocumentExtractionResponse from extract_document")
    if not any(page.text.strip() for page in document.pages):
        raise BusinessProfileIngestionError("No selectable text is available for profile ingestion.")
    if not document.filename.strip() or len(document.filename) > MAX_SOURCE_DOCUMENT_LENGTH:
        raise BusinessProfileIngestionError(
            f"Source document filename must be 1 to {MAX_SOURCE_DOCUMENT_LENGTH} characters."
        )

    entity_name = _resolve(
        field_name="entity name",
        candidates=_collect_candidates(document, _ENTITY_NAME_LABELS, following_lines=1),
        parse=lambda candidate: _text(candidate, max_length=MAX_ENTITY_NAME_LENGTH),
        key=lambda value: value.casefold(),
    )
    uen = _resolve(
        field_name="UEN",
        candidates=_collect_candidates(document, _UEN_LABELS, following_lines=1),
        parse=_uen,
        key=lambda value: value,
    )
    entity_type = _resolve(
        field_name="entity type",
        candidates=_collect_candidates(document, _ENTITY_TYPE_LABELS, following_lines=1),
        parse=lambda candidate: _text(candidate, max_length=MAX_ENTITY_TYPE_LENGTH),
        key=lambda value: value.casefold(),
    )
    status = _resolve(
        field_name="entity status",
        candidates=_collect_candidates(document, _STATUS_LABELS, following_lines=1),
        parse=lambda candidate: _text(candidate, max_length=MAX_STATUS_LENGTH),
        key=lambda value: value.casefold(),
    )
    registration_date = _resolve(
        field_name="registration/incorporation date",
        candidates=_collect_candidates(
            document,
            _REGISTRATION_DATE_LABELS + _INCORPORATION_DATE_LABELS,
            following_lines=1,
        ),
        parse=_date,
        key=lambda value: (value.kind, value.date),
    )
    primary_ssic = _resolve(
        field_name="primary SSIC",
        candidates=_collect_candidates(document, _PRIMARY_SSIC_LABELS, following_lines=3),
        parse=_ssic,
        key=lambda value: (value.code, (value.description or "").casefold()),
    )
    secondary_ssic = _resolve(
        field_name="secondary SSIC",
        candidates=_collect_candidates(document, _SECONDARY_SSIC_LABELS, following_lines=3),
        parse=_ssic,
        key=lambda value: (value.code, (value.description or "").casefold()),
    )
    if primary_ssic.value is not None and primary_ssic.value.code is None:
        primary_ssic = ExtractedField(
            value=primary_ssic.value,
            confidence="REVIEW",
            sources=primary_ssic.sources,
            review_reason="A primary activity description is explicit, but no five-digit SSIC code is.",
        )
    if secondary_ssic.value is not None and secondary_ssic.value.code is None:
        secondary_ssic = ExtractedField(
            value=secondary_ssic.value,
            confidence="REVIEW",
            sources=secondary_ssic.sources,
            review_reason=(
                "A secondary activity description is explicit, but no five-digit SSIC code is."
            ),
        )
    paid_up_capital = _resolve(
        field_name="paid-up capital",
        candidates=_collect_candidates(document, _PAID_UP_CAPITAL_LABELS, following_lines=8),
        parse=_capital,
        key=lambda value: (value.amount, value.currency),
    )
    if paid_up_capital.value is not None and paid_up_capital.value.currency is None:
        paid_up_capital = ExtractedField(
            value=paid_up_capital.value,
            confidence="REVIEW",
            sources=paid_up_capital.sources,
            review_reason="The paid-up capital amount is explicit, but its currency is not.",
        )

    fields = (
        entity_name,
        uen,
        entity_type,
        status,
        registration_date,
        primary_ssic,
        secondary_ssic,
        paid_up_capital,
    )
    warnings = list(document.warnings)
    review_count = sum(field.confidence == "REVIEW" for field in fields)
    if review_count:
        warnings.append(f"{review_count} profile field(s) require human review.")

    return BusinessProfileIngestionResult(
        source_document=document.filename,
        entity_name=entity_name,
        uen=uen,
        entity_type=entity_type,
        status=status,
        registration_or_incorporation_date=registration_date,
        primary_ssic=primary_ssic,
        secondary_ssic=secondary_ssic,
        paid_up_capital=paid_up_capital,
        epu_grade=_review_qualification("EPU"),
        sca_grade=_review_qualification("SCA"),
        warnings=warnings,
        boundaries=[
            "Source content is USER_SUPPLIED selectable text; no ACRA lookup was performed.",
            "The extracted profile is NOT_OFFICIALLY_VERIFIED and must be checked against the source.",
            "ACRA profile content does not establish EPU or SCA grades; neither grade is inferred.",
        ],
    )
