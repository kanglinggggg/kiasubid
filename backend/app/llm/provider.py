import json
from collections.abc import Mapping
from typing import Any, Protocol

import httpx

from app.config import Settings, settings


class ModelUnavailable(RuntimeError):
    pass


class BedrockUnavailable(ModelUnavailable):
    pass


class GroqUnavailable(ModelUnavailable):
    pass


class JsonModelClient(Protocol):
    model_id: str
    mode: str

    def generate_json(
        self, *, system: str, prompt: str, schema: dict[str, Any], schema_name: str
    ) -> str: ...


def _bedrock_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Remove Pydantic annotations unsupported by Bedrock's JSON Schema subset."""
    unsupported = {
        "default",
        "examples",
        "maximum",
        "minimum",
        "maxLength",
        "minLength",
        "multipleOf",
        "title",
    }
    cleaned: dict[str, Any] = {}
    for key, value in schema.items():
        if key in unsupported:
            continue
        if isinstance(value, dict):
            cleaned[key] = _bedrock_schema(value)
        elif isinstance(value, list):
            cleaned[key] = [
                _bedrock_schema(item) if isinstance(item, dict) else item for item in value
            ]
        else:
            cleaned[key] = value
    return cleaned


class BedrockConverseClient:
    mode = "BEDROCK"

    def __init__(self, app_settings: Settings = settings):
        if not app_settings.bedrock_configured or not app_settings.bedrock_model_id:
            raise BedrockUnavailable("BEDROCK_MODEL_ID is not configured")
        self.model_id = app_settings.bedrock_model_id
        self._settings = app_settings
        self._client: Any | None = None

    def _runtime(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import boto3

            session_args: dict[str, str] = {}
            if self._settings.aws_profile:
                session_args["profile_name"] = self._settings.aws_profile
            access_key = (
                self._settings.aws_access_key_id.get_secret_value()
                if self._settings.aws_access_key_id
                else ""
            )
            secret_key = (
                self._settings.aws_secret_access_key.get_secret_value()
                if self._settings.aws_secret_access_key
                else ""
            )
            session_token = (
                self._settings.aws_session_token.get_secret_value()
                if self._settings.aws_session_token
                else ""
            )
            if bool(access_key) != bool(secret_key):
                raise BedrockUnavailable(
                    "AWS temporary credentials are incomplete; both access key and secret key "
                    "are required"
                )
            if access_key and secret_key:
                session_args["aws_access_key_id"] = access_key
                session_args["aws_secret_access_key"] = secret_key
                if session_token:
                    session_args["aws_session_token"] = session_token
            aws = boto3.Session(**session_args)
            self._client = aws.client(
                "bedrock-runtime", region_name=self._settings.aws_default_region
            )
            return self._client
        except Exception as exc:
            raise BedrockUnavailable(f"Bedrock client could not be created: {exc}") from exc

    def generate_json(
        self, *, system: str, prompt: str, schema: dict[str, Any], schema_name: str
    ) -> str:
        effective_prompt = prompt
        if not self._settings.bedrock_structured_output:
            effective_prompt = (
                f"{prompt}\n\nOUTPUT JSON SCHEMA ({schema_name}):\n"
                f"{json.dumps(_bedrock_schema(schema), ensure_ascii=False)}"
            )
        request: dict[str, Any] = {
            "modelId": self.model_id,
            "system": [{"text": system}],
            "messages": [{"role": "user", "content": [{"text": effective_prompt}]}],
            "inferenceConfig": {"maxTokens": 2500, "temperature": 0},
        }
        if self._settings.bedrock_structured_output:
            request["outputConfig"] = {
                "textFormat": {
                    "type": "json_schema",
                    "structure": {
                        "jsonSchema": {
                            "schema": json.dumps(_bedrock_schema(schema)),
                            "name": schema_name,
                            "description": "Validated procurement interpretation",
                        }
                    },
                }
            }
        try:
            response: Mapping[str, Any] = self._runtime().converse(**request)
            blocks = response["output"]["message"]["content"]
            text_blocks = [block["text"] for block in blocks if "text" in block]
            if not text_blocks:
                raise BedrockUnavailable("Bedrock returned no text content")
            return "".join(text_blocks)
        except BedrockUnavailable:
            raise
        except Exception as exc:
            raise BedrockUnavailable(f"Bedrock Converse failed: {exc}") from exc


class GroqChatClient:
    mode = "GROQ"

    def __init__(self, app_settings: Settings = settings):
        model_id = app_settings.effective_groq_model_id
        if not app_settings.groq_configured or not model_id:
            raise GroqUnavailable(
                "GROQ_API_KEY and GROQ_MODEL_ID (or GROQ_MODEL) are not configured"
            )
        self.model_id = model_id
        self._settings = app_settings

    def generate_json(
        self, *, system: str, prompt: str, schema: dict[str, Any], schema_name: str
    ) -> str:
        api_key = self._settings.groq_api_key
        if api_key is None:
            raise GroqUnavailable("GROQ_API_KEY is not configured")
        request: dict[str, Any] = {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 1e-8,
            "max_completion_tokens": 2500,
        }
        if self._settings.groq_structured_output:
            request["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": False,
                    "schema": _bedrock_schema(schema),
                },
            }
        else:
            request["response_format"] = {"type": "json_object"}
        endpoint = f"{self._settings.groq_base_url.rstrip('/')}/chat/completions"
        try:
            response = httpx.post(
                endpoint,
                headers={
                    "Authorization": f"Bearer {api_key.get_secret_value()}",
                    "Content-Type": "application/json",
                },
                json=request,
                timeout=self._settings.groq_timeout_seconds,
            )
            response.raise_for_status()
            payload: Mapping[str, Any] = response.json()
            choices = payload.get("choices")
            if not isinstance(choices, list) or not choices:
                raise GroqUnavailable("Groq returned no completion choices")
            message = choices[0].get("message", {})
            content = message.get("content")
            if not isinstance(content, str) or not content.strip():
                raise GroqUnavailable("Groq returned no text content")
            return content
        except GroqUnavailable:
            raise
        except httpx.HTTPStatusError as exc:
            try:
                error = exc.response.json().get("error", {}).get("message")
            except (AttributeError, TypeError, ValueError):
                error = None
            detail = str(error or exc.response.reason_phrase)[:500]
            raise GroqUnavailable(
                f"Groq request failed with HTTP {exc.response.status_code}: {detail}"
            ) from exc
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            raise GroqUnavailable(f"Groq request failed: {exc}") from exc


def get_model_client(app_settings: Settings = settings) -> JsonModelClient:
    if app_settings.llm_provider == "bedrock":
        return BedrockConverseClient(app_settings)
    if app_settings.llm_provider == "groq":
        return GroqChatClient(app_settings)
    raise ModelUnavailable(f"Unsupported LLM provider: {app_settings.llm_provider}")
