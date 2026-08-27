import json
from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from app.config import Settings, settings
from app.llm.fallback import interpret_change_fallback, interpret_requirement_fallback
from app.llm.prompts import (
    SYSTEM_PROMPT,
    change_prompt,
    change_schema,
    repair_prompt,
    requirement_prompt,
    requirement_schema,
)
from app.llm.provider import JsonModelClient, ModelUnavailable, get_model_client
from app.llm.schemas import (
    ChangeInterpretationEnvelope,
    ChangeInterpretationRequest,
    ChangeInterpretationResult,
    RequirementInterpretationEnvelope,
    RequirementInterpretationRequest,
    RequirementInterpretationResult,
    RequirementSource,
)

OutputModel = TypeVar("OutputModel", bound=BaseModel)


class InterpretationFailure(ValueError):
    pass


def _json_object(raw: str) -> dict[str, Any]:
    candidate = raw.strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        candidate = "\n".join(lines[1:-1]).strip()
    if not candidate.startswith("{"):
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start >= 0 and end > start:
            candidate = candidate[start : end + 1]
    value = json.loads(candidate)
    if not isinstance(value, dict):
        raise ValueError("model output must be a JSON object")
    return value


def _scalar(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_scalar(item) for item in value]
    if isinstance(value, dict):
        return {key: _scalar(item) for key, item in value.items()}
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


class TenderInterpreter:
    def __init__(
        self,
        client: JsonModelClient | None = None,
        app_settings: Settings = settings,
    ):
        self._settings = app_settings
        self._client = client

    def _configured_client(self) -> JsonModelClient:
        if self._client is not None:
            return self._client
        return get_model_client(self._settings)

    def _invoke(
        self,
        *,
        prompt: str,
        schema: dict[str, Any],
        schema_name: str,
        output_model: type[OutputModel],
        validator: Callable[[OutputModel], None] | None = None,
    ) -> tuple[OutputModel, int, str, str]:
        client = self._configured_client()
        current_prompt = prompt
        last_error = ""
        last_output = ""
        total_attempts = self._settings.llm_max_retries + 1
        for attempt in range(1, total_attempts + 1):
            last_output = client.generate_json(
                system=SYSTEM_PROMPT,
                prompt=current_prompt,
                schema=schema,
                schema_name=schema_name,
            )
            try:
                result = output_model.model_validate(_json_object(last_output))
                if validator is not None:
                    validator(result)
                return result, attempt, client.model_id, getattr(client, "mode", "BEDROCK")
            except (ValidationError, ValueError, json.JSONDecodeError) as exc:
                last_error = str(exc)
                current_prompt = repair_prompt(prompt, last_output, last_error)
        raise InterpretationFailure(
            f"Model output failed validation after {total_attempts} attempts: {last_error}"
        )

    def interpret_requirements(
        self,
        payload: RequirementInterpretationRequest,
        *,
        allow_fallback: bool = True,
    ) -> RequirementInterpretationEnvelope:
        if not payload.text.strip():
            return RequirementInterpretationEnvelope(
                mode="DEMO_FALLBACK",
                fallback_reason="No source text supplied; deterministic safety result returned.",
                attempts=0,
                result=interpret_requirement_fallback(payload),
            )
        try:
            result, attempts, model_id, mode = self._invoke(
                prompt=requirement_prompt(payload),
                schema=requirement_schema(),
                schema_name="tender_requirements",
                output_model=RequirementInterpretationResult,
                validator=lambda result: self._validate_requirements_against_input(
                    payload, result
                ),
            )
            source_text = payload.text
            normalized = []
            for requirement in result.requirements:
                snippet = requirement.source.snippet
                if not snippet or snippet not in source_text:
                    snippet = source_text
                source = RequirementSource(
                    document=payload.document_name,
                    page=payload.page,
                    section=payload.section,
                    snippet=snippet,
                )
                stable_key = requirement.stable_key or payload.stable_key_hint
                normalized.append(
                    requirement.model_copy(update={"source": source, "stable_key": stable_key})
                )
            return RequirementInterpretationEnvelope(
                mode=mode,
                model_id=model_id,
                attempts=attempts,
                result=RequirementInterpretationResult(requirements=normalized),
            )
        except (ModelUnavailable, InterpretationFailure) as exc:
            if not allow_fallback:
                raise InterpretationFailure(str(exc)) from exc
            return RequirementInterpretationEnvelope(
                mode="DEMO_FALLBACK",
                fallback_reason=str(exc),
                attempts=(
                    0
                    if isinstance(exc, ModelUnavailable)
                    else self._settings.llm_max_retries + 1
                ),
                result=interpret_requirement_fallback(payload),
            )

    def interpret_change(
        self,
        payload: ChangeInterpretationRequest,
        *,
        allow_fallback: bool = True,
    ) -> ChangeInterpretationEnvelope:
        if not payload.text.strip():
            return ChangeInterpretationEnvelope(
                mode="DEMO_FALLBACK",
                fallback_reason="No corrigendum text supplied; deterministic safety result returned.",
                attempts=0,
                result=interpret_change_fallback(payload),
            )
        try:
            result, attempts, model_id, mode = self._invoke(
                prompt=change_prompt(payload),
                schema=change_schema(),
                schema_name="corrigendum_change",
                output_model=ChangeInterpretationResult,
                validator=lambda result: self._validate_change_against_input(payload, result),
            )
            if result.resulting_requirement is not None:
                candidate = result.resulting_requirement
                snippet = candidate.source.snippet
                if not snippet or snippet not in payload.text:
                    snippet = payload.text
                source = RequirementSource(
                    document=payload.corrigendum_document,
                    page=payload.page,
                    section=payload.section,
                    snippet=snippet,
                )
                result = result.model_copy(
                    update={
                        "resulting_requirement": candidate.model_copy(
                            update={"source": source, "stable_key": result.affected_stable_key}
                        )
                    }
                )
            return ChangeInterpretationEnvelope(
                mode=mode,
                model_id=model_id,
                attempts=attempts,
                result=result,
            )
        except (ModelUnavailable, InterpretationFailure, ValueError) as exc:
            if not allow_fallback:
                raise InterpretationFailure(str(exc)) from exc
            return ChangeInterpretationEnvelope(
                mode="DEMO_FALLBACK",
                fallback_reason=str(exc),
                attempts=(
                    0
                    if isinstance(exc, ModelUnavailable)
                    else self._settings.llm_max_retries + 1
                ),
                result=interpret_change_fallback(payload),
            )

    @staticmethod
    def _validate_requirements_against_input(
        payload: RequirementInterpretationRequest,
        result: RequirementInterpretationResult,
    ) -> None:
        for index, requirement in enumerate(result.requirements):
            snippet = requirement.source.snippet
            if not snippet or snippet not in payload.text:
                raise ValueError(
                    f"requirements.{index}.source.snippet must be an exact source substring"
                )

    @staticmethod
    def _validate_change_against_input(
        payload: ChangeInterpretationRequest, result: ChangeInterpretationResult
    ) -> None:
        existing = payload.existing_requirement
        resulting = result.resulting_requirement
        if resulting is not None:
            snippet = resulting.source.snippet
            if not snippet or snippet not in payload.text:
                raise ValueError(
                    "resulting_requirement.source.snippet must be an exact corrigendum substring"
                )
        if result.interpretation_status == "UNCERTAIN" and result.change_type != "UNCHANGED":
            raise ValueError("UNCERTAIN output cannot assert a state-changing classification")
        if result.change_type in {"MODIFIED", "REMOVED"}:
            if result.affected_stable_key != existing.stable_key:
                raise ValueError("state-changing output must target the supplied stable requirement")
        for change in result.changed_fields:
            old_value = _scalar(getattr(existing, change.field))
            if _scalar(change.old_value) != old_value:
                raise ValueError(f"changed_fields.{change.field}.old_value does not match input")
            if resulting is not None:
                new_value = _scalar(getattr(resulting, change.field))
                if _scalar(change.new_value) != new_value:
                    raise ValueError(
                        f"changed_fields.{change.field}.new_value does not match result"
                    )
        if result.change_type == "MODIFIED" and resulting is not None:
            semantic_fields = {
                "text",
                "requirement_type",
                "gate_type",
                "deadline",
                "minimum_count",
                "certification",
                "compulsory",
                "structured_fields",
                "procurement_rule",
            }
            actual_fields = {
                field
                for field in semantic_fields
                if _scalar(getattr(existing, field)) != _scalar(getattr(resulting, field))
            }
            reported_fields = {change.field for change in result.changed_fields}
            if actual_fields != reported_fields:
                raise ValueError(
                    "changed_fields must exactly match all changed structured fields: "
                    f"expected {sorted(actual_fields)}, got {sorted(reported_fields)}"
                )
