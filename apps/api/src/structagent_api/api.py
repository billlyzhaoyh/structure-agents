"""FastAPI application factory for the StructAgent API shell."""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

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

    return app
