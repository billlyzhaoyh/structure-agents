from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from structagent_api.api import create_app
from structagent_api.settings import Settings


def test_health_endpoint_uses_typed_settings() -> None:
    app = create_app(Settings(service_name="test-service", environment="test"))

    response = TestClient(app).get("/healthz")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "test-service",
        "environment": "test",
        "version": "0.1.0",
    }


def test_openapi_exposes_only_the_implemented_product_route() -> None:
    schema = create_app(Settings(environment="test")).openapi()

    assert set(schema["paths"]) == {"/healthz"}
    assert schema["info"]["title"] == "StructAgent API"
    assert schema["info"]["version"] == "0.1.0"


def test_invalid_log_level_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(log_level="TRACE")
