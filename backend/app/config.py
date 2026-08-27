from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "GeBIZ BidOps"
    database_url: str = f"sqlite:///{(PROJECT_ROOT / 'data' / 'bidops.db').as_posix()}"
    demo_mode: bool = True
    cors_origins: str = "http://localhost:5173"
    llm_provider: Literal["bedrock", "groq"] = "bedrock"
    aws_profile: str | None = None
    aws_default_region: str = "us-east-1"
    aws_access_key_id: SecretStr | None = None
    aws_secret_access_key: SecretStr | None = None
    aws_session_token: SecretStr | None = None
    bedrock_model_id: str | None = None
    bedrock_structured_output: bool = True
    groq_api_key: SecretStr | None = None
    groq_model_id: str | None = None
    groq_model: str | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_structured_output: bool = True
    groq_timeout_seconds: float = 60
    llm_max_retries: int = 1

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator(
        "aws_profile",
        "aws_access_key_id",
        "aws_secret_access_key",
        "aws_session_token",
        "bedrock_model_id",
        "groq_api_key",
        "groq_model_id",
        "groq_model",
        mode="before",
    )
    @classmethod
    def blank_optional_values_are_unconfigured(cls, value: object) -> object:
        return None if value == "" else value

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def bedrock_configured(self) -> bool:
        return self.llm_provider == "bedrock" and bool(self.bedrock_model_id)

    @property
    def groq_configured(self) -> bool:
        key = self.groq_api_key.get_secret_value() if self.groq_api_key else ""
        return self.llm_provider == "groq" and bool(key and self.effective_groq_model_id)

    @property
    def effective_groq_model_id(self) -> str | None:
        """Accept Groq's common GROQ_MODEL name without breaking GROQ_MODEL_ID setups."""
        return self.groq_model_id or self.groq_model

    @property
    def interpretation_configured(self) -> bool:
        return self.bedrock_configured or self.groq_configured

    @property
    def active_model_id(self) -> str | None:
        return (
            self.bedrock_model_id
            if self.llm_provider == "bedrock"
            else self.effective_groq_model_id
        )

    @property
    def interpretation_mode(self) -> Literal["BEDROCK", "GROQ"]:
        return "BEDROCK" if self.llm_provider == "bedrock" else "GROQ"


settings = Settings()
