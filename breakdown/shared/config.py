"""Application/runtime settings schema."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment / .env.

    Secrets are never part of settings; a model backend authenticates
    through its own SDK environment convention.
    """

    model_config = SettingsConfigDict(env_file=".env", env_prefix="BREAKDOWN_", extra="ignore")

    workflow_path: Path = Path("breakdown.yaml")
    target_repo: Path = Path(".")
    state_root: Path = Path(".breakdown")
    backend_bindings_path: Path | None = None
    # Live OpenAI-compatible API (Databricks Model Serving, custom gateway,
    # or OpenAI). Secrets stay SecretStr: never logged, never persisted.
    api_base_url: str | None = None
    api_key: SecretStr | None = None
    model: str | None = None
    model_builder: str | None = None
    model_auditor: str | None = None
    model_researcher: str | None = None
    model_coder: str | None = None
    model_planner: str | None = None
    model_verifier: str | None = None
    api_max_tool_rounds: int = Field(default=8, ge=1)

