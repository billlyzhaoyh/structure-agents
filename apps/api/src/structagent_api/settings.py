"""Typed settings for the StructAgent API shell."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from STRUCTAGENT-prefixed environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="STRUCTAGENT_",
        env_file=".env",
        extra="ignore",
    )

    service_name: str = "structagent-api"
    environment: str = "local"
    log_level: str = Field(default="INFO", pattern=r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
