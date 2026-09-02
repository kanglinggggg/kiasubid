import re

from app.llm.schemas import (
    ChangeInterpretationRequest,
    ChangeInterpretationResult,
    FieldChange,
    RequirementInterpretationRequest,
    RequirementInterpretationResult,
    RequirementSource,
    StructuredRequirement,
)

NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}

MODEL_DIRECTIVE_PATTERN = re.compile(
    r"\b(?:system\s+instruction|instruction\s+to\s+(?:ai|model|assistant)|"
    r"ignore\s+(?:all\s+|any\s+|the\s+)?(?:previous|prior|system|developer)\s+instructions?|"
    r"reveal\s+(?:the\s+)?(?:system\s+)?prompt)\b",
    re.IGNORECASE,
)


def _counts(text: str) -> list[int]:
    matches = re.findall(
        r"(?:not\s+fewer\s+than|at\s+least|minimum(?:\s+of)?)\s+(\d+|"
        + "|".join(NUMBER_WORDS)
        + r")\b",
        text,
        re.IGNORECASE,
    )
    return [int(token) if token.isdigit() else NUMBER_WORDS[token.lower()] for token in matches]


def _count(text: str) -> int | None:
    counts = _counts(text)
    return counts[0] if counts else None


def _source(document: str, page: int, section: str, snippet: str) -> RequirementSource:
    return RequirementSource(document=document, page=page, section=section, snippet=snippet)


def _contains_model_directive(text: str) -> bool:
    return bool(MODEL_DIRECTIVE_PATTERN.search(text))


def interpret_requirement_fallback(
    payload: RequirementInterpretationRequest,
) -> RequirementInterpretationResult:
    text = payload.text.strip()
    lower = text.lower()
    if not text:
        return RequirementInterpretationResult(
            requirements=[
                StructuredRequirement(
                    stable_key=payload.stable_key_hint,
                    text="Source text unavailable.",
                    requirement_type="OTHER",
                    gate_type="INFORMATIONAL",
                    interpretation_status="UNCERTAIN",
                    uncertainty_reason="Tender document text was not supplied.",
                    source=_source(
                        payload.document_name,
                        payload.page,
                        payload.section,
                        "",
                    ),
                )
            ]
        )
    if _contains_model_directive(text):
        return RequirementInterpretationResult(
            requirements=[
                StructuredRequirement(
                    stable_key=payload.stable_key_hint,
                    text=text,
                    requirement_type="OTHER",
                    gate_type="INFORMATIONAL",
                    interpretation_status="UNCERTAIN",
                    uncertainty_reason=(
                        "The source contains model-directed instruction text; deterministic "
                        "fallback will not interpret or operationalize it."
                    ),
                    source=_source(
                        payload.document_name,
                        payload.page,
                        payload.section,
                        text,
                    ),
                )
            ]
        )
    count = _count(text)
    certification_match = re.search(r"\b(CISSP|CISA|CISM|PMP|ISO\s*27001)\b", text, re.I)
    certification = (
        certification_match.group(1).upper().replace(" ", "")
        if certification_match
        else None
    )
    explicit_obligation = bool(re.search(r"\b(shall|must|required|compulsory)\b", lower))
    vague = bool(re.search(r"\b(adequate|sufficient|suitably|appropriate|as needed)\b", lower))
    status = "UNCERTAIN" if vague or ("personnel" in lower and count is None) else "INTERPRETED"
    reason = (
        "The clause does not state an objective mandatory quantity or qualification."
        if status == "UNCERTAIN"
        else None
    )
    requirement_type = (
        "MANPOWER"
        if any(word in lower for word in ("personnel", "staff", "engineer", "manpower"))
        else "OTHER"
    )
    requirement = StructuredRequirement(
        stable_key=payload.stable_key_hint,
        text=text,
        requirement_type=requirement_type,
        gate_type="MANDATORY" if explicit_obligation else "INFORMATIONAL",
        deadline=None,
        minimum_count=count,
        certification=certification,
        compulsory=True if explicit_obligation else None,
        interpretation_status=status,
        uncertainty_reason=reason,
        source=_source(payload.document_name, payload.page, payload.section, text),
    )
    return RequirementInterpretationResult(requirements=[requirement])


def interpret_change_fallback(
    payload: ChangeInterpretationRequest,
) -> ChangeInterpretationResult:
    existing = payload.existing_requirement
    text = payload.text.strip()
    lower = text.lower()
    source = _source(payload.corrigendum_document, payload.page, payload.section, text)
    if _contains_model_directive(text):
        return ChangeInterpretationResult(
            change_type="UNCHANGED",
            affected_stable_key=None,
            changed_fields=[],
            resulting_requirement=None,
            interpretation_status="UNCERTAIN",
            uncertainty_reason=(
                "The source contains model-directed instruction text; deterministic fallback "
                "will not apply a semantic change."
            ),
            reason_summary="No change was applied because the source failed the fallback safety check.",
        )
    identifies_existing = bool(
        (existing.stable_key and existing.stable_key.lower() in lower)
        or existing.source.section.lower() in lower
        or "clause 4.3" in lower
        or (existing.certification and existing.certification.lower() in lower)
    )
    removed = bool(re.search(r"\b(deleted|removed|withdrawn|no longer required)\b", lower))
    if removed and identifies_existing:
        return ChangeInterpretationResult(
            change_type="REMOVED",
            affected_stable_key=existing.stable_key,
            changed_fields=[
                FieldChange(field="compulsory", old_value=existing.compulsory, new_value=False)
            ],
            resulting_requirement=None,
            interpretation_status="INTERPRETED",
            reason_summary="The corrigendum explicitly removes the existing requirement.",
        )

    amendment_counts = _counts(text)
    new_count = amendment_counts[-1] if amendment_counts else None
    if identifies_existing and new_count is not None and new_count != existing.minimum_count:
        count_label = next(
            (word for word, value in NUMBER_WORDS.items() if value == new_count), str(new_count)
        )
        updated_text = (
            f"The Tenderer shall propose not fewer than {count_label} personnel holding valid "
            f"{existing.certification} certification."
        )
        resulting = existing.model_copy(
            update={
                "text": updated_text,
                "minimum_count": new_count,
                "interpretation_status": "INTERPRETED",
                "uncertainty_reason": None,
                "source": source,
            }
        )
        return ChangeInterpretationResult(
            change_type="MODIFIED",
            affected_stable_key=existing.stable_key,
            changed_fields=[
                FieldChange(field="text", old_value=existing.text, new_value=updated_text),
                FieldChange(
                    field="minimum_count", old_value=existing.minimum_count, new_value=new_count
                ),
            ],
            resulting_requirement=resulting,
            interpretation_status="INTERPRETED",
            reason_summary=(
                f"The minimum personnel count changes from {existing.minimum_count} to {new_count}."
            ),
        )

    deadline_only = bool(re.search(r"\b(deadline|closing|submission date|submit by)\b", lower))
    if deadline_only and not identifies_existing:
        return ChangeInterpretationResult(
            change_type="UNCHANGED",
            affected_stable_key=None,
            changed_fields=[],
            resulting_requirement=None,
            interpretation_status="INTERPRETED",
            reason_summary=(
                "The amendment concerns a deadline and does not affect this manpower requirement."
            ),
        )
    if identifies_existing and new_count == existing.minimum_count:
        return ChangeInterpretationResult(
            change_type="UNCHANGED",
            affected_stable_key=existing.stable_key,
            changed_fields=[],
            resulting_requirement=None,
            interpretation_status="INTERPRETED",
            reason_summary="The wording is semantically equivalent to the existing requirement.",
        )
    return ChangeInterpretationResult(
        change_type="UNCHANGED",
        affected_stable_key=existing.stable_key if identifies_existing else None,
        changed_fields=[],
        resulting_requirement=None,
        interpretation_status="UNCERTAIN",
        uncertainty_reason="The demo fallback cannot determine a precise semantic change.",
        reason_summary="The text does not match a supported demo change pattern.",
    )
