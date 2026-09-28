"""FastAPI application factory for the StructAgent API shell."""

from __future__ import annotations

from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel
from structagent_contracts import SimulationStudyArtifact, hm_promo_conjoint_v1

from structagent_api import __version__
from structagent_api.settings import Settings


class HealthResponse(BaseModel):
    """Public liveness response."""

    status: str
    service: str
    environment: str
    version: str


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create an API instance without performing external work at import time."""

    resolved = settings or Settings()
    app = FastAPI(
        title="StructAgent API",
        description="Control-plane shell for the provisional StructAgent research demo.",
        version=__version__,
    )

    @app.get("/healthz", response_model=HealthResponse, tags=["operations"])
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            service=resolved.service_name,
            environment=resolved.environment,
            version=__version__,
        )

    @app.get(
        "/v1/simulation-studies/defaults",
        response_model=list[SimulationStudyArtifact],
        tags=["simulation studies"],
    )
    def simulation_study_defaults(
        dataset_id: Literal["rel-hm"],
    ) -> list[SimulationStudyArtifact]:
        """List reviewed simulation studies for the requested dataset."""

        return [hm_promo_conjoint_v1()]

    return app
