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

    assert set(schema["paths"]) == {"/healthz", "/v1/simulation-studies/defaults"}
    assert schema["info"]["title"] == "StructAgent API"
    assert schema["info"]["version"] == "0.1.0"


def test_simulation_catalog_exposes_the_reviewed_hm_default_as_metadata_only() -> None:
    response = TestClient(create_app(Settings(environment="test"))).get(
        "/v1/simulation-studies/defaults",
        params={"dataset_id": "rel-hm"},
    )

    assert response.status_code == 200
    studies = response.json()
    assert len(studies) == 1
    assert studies[0]["artifact_id"] == "rel-hm/promo-conjoint-v1"
    assert studies[0]["dataset"] == {
        "dataset_id": "rel-hm",
        "status": "metadata_only_placeholder",
        "revision": None,
        "manifest_digest": None,
    }
    assert studies[0]["study"]["study_type"] == "discrete_choice"
    assert studies[0]["study"]["include_no_choice"] is True


def test_simulation_catalog_rejects_an_unsupported_dataset() -> None:
    response = TestClient(create_app(Settings(environment="test"))).get(
        "/v1/simulation-studies/defaults",
        params={"dataset_id": "rel-amazon"},
    )

    assert response.status_code == 422


def test_invalid_log_level_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(log_level="TRACE")
