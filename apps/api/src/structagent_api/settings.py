"""Typed settings for the StructAgent API shell."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

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
    allow_real_hm: bool = False
    allow_rtj_modal: bool = False
    enable_modal_ui: bool = False
    rtj_dataset_root: Path | None = None
    rtj_materialization_root: Path | None = None
    rtj_output_root: Path = Path(".artifacts/ui-rtj")
    rtj_modal_gpu: Literal["L4", "L40S"] = "L4"
