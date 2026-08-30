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


def test_openapi_exposes_catalog_and_fixture_backed_demo_routes() -> None:
    schema = create_app(Settings(environment="test")).openapi()

    assert set(schema["paths"]) == {
        "/healthz",
        "/v1/datasets/rel-hm",
        "/v1/runs/{run_id}",
        "/v1/runs/{run_id}/evaluation",
        "/v1/task-drafts",
        "/v1/task-drafts/{draft_id}/clarifications",
        "/v1/tasks/defaults",
    }
    assert schema["info"]["title"] == "StructAgent API"
    assert schema["info"]["version"] == "0.1.0"


def test_retail_dataset_route_returns_the_versioned_metadata_contract() -> None:
    response = TestClient(create_app(Settings(environment="test"))).get("/v1/datasets/rel-hm")

    assert response.status_code == 200
    payload = response.json()
    assert payload["contract_version"] == "v1"
    assert payload["implementation_status"] == "metadata_only"
    assert [table["name"] for table in payload["tables"]] == [
        "customer",
        "article",
        "transactions",
    ]


def test_unconfigured_task_compiler_and_fixture_run_routes_are_explicit() -> None:
    client = TestClient(create_app(Settings(environment="test")))

    draft = client.post(
        "/v1/task-drafts",
        json={
            "contract_version": "v1",
            "dataset_id": "rel-hm",
            "prompt": "How much will each article sell over the next seven days?",
        },
    )
    run = client.get("/v1/runs/fixture-hm-run")
    evaluation = client.get("/v1/runs/fixture-hm-run/evaluation")

    assert draft.status_code == 503
    assert draft.json()["detail"]["code"] == "compiler_unavailable"
    assert run.json()["status"] == "succeeded"
    assert evaluation.json()["metrics"] == {"mae": 12.4, "rmse": 18.9, "r2": 0.37}


def test_demo_routes_reject_unknown_contract_resources() -> None:
    client = TestClient(create_app(Settings(environment="test")))

    unsupported_dataset = client.post(
        "/v1/task-drafts",
        json={"contract_version": "v1", "dataset_id": "unknown", "prompt": "Forecast sales"},
    )

    assert unsupported_dataset.status_code == 200
    assert unsupported_dataset.json()["outcome"] == "unsupported"
    assert unsupported_dataset.json()["reason_code"] == "unsupported_dataset"
    assert client.get("/v1/runs/unknown").status_code == 404
    assert client.get("/v1/runs/unknown/evaluation").status_code == 404


def test_local_frontend_origin_is_allowed_by_cors() -> None:
    response = TestClient(create_app(Settings(environment="test"))).options(
        "/v1/datasets/rel-hm",
        headers={
            "Origin": "http://127.0.0.1:4174",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:4174"


def test_hm_catalog_routes_return_reviewed_metadata_without_credentials() -> None:
    client = TestClient(create_app(Settings(environment="test")))

    dataset_response = client.get("/v1/datasets/rel-hm")
    tasks_response = client.get("/v1/tasks/defaults", params={"dataset_id": "rel-hm"})

    assert dataset_response.status_code == 200
    assert dataset_response.json()["dataset_id"] == "rel-hm"
    assert dataset_response.json()["implementation_status"] == "metadata_only"
    assert tasks_response.status_code == 200
    assert [task["task_id"] for task in tasks_response.json()["tasks"]] == [
        "rel-hm/user-churn",
        "rel-hm/item-sales",
    ]
    assert {task["source"] for task in tasks_response.json()["tasks"]} == {"default"}


def test_default_task_catalog_rejects_unsupported_or_missing_dataset() -> None:
    client = TestClient(create_app(Settings(environment="test")))

    unsupported = client.get(
        "/v1/tasks/defaults",
        params={"dataset_id": "rel-amazon"},
    )
    missing = client.get("/v1/tasks/defaults")

    assert unsupported.status_code == 404
    assert unsupported.json() == {
        "detail": "Dataset 'rel-amazon' is not available in the V1 default catalog."
    }
    assert missing.status_code == 422


def test_invalid_log_level_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(log_level="TRACE")
