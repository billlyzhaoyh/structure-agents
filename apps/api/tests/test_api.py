from __future__ import annotations

from collections.abc import Sequence

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from structagent_api.api import create_app
from structagent_api.contracts import (
    DaytonaMaterializationResponse,
    ModalInferenceRequest,
    ModalInferenceResponse,
)
from structagent_api.materialization.daytona_executor import DaytonaExecutionError
from structagent_api.materialization.task_sql import TaskId
from structagent_api.settings import Settings


def successful_daytona_response() -> DaytonaMaterializationResponse:
    return DaytonaMaterializationResponse.model_validate(
        {
            "contract_version": "v1",
            "fixture": True,
            "implementation_status": "synthetic_execution",
            "execution_id": "mat-0123456789abcdef",
            "dataset_id": "rel-hm",
            "mode": "daytona-synthetic",
            "status": "succeeded",
            "cleanup_confirmed": True,
            "network_block_all": True,
            "sql_canary_confirmed": True,
            "resources": {"cpu_cores": 4, "memory_gib": 8, "disk_gib": 10},
            "tasks": [
                {
                    "task_id": "rel-hm/item-sales",
                    "package_sha256": "a" * 64,
                    "validation_status": "passed",
                    "train_rows": 12,
                    "validation_rows": 4,
                    "test_rows": 4,
                }
            ],
        }
    )


def observed_modal_contract_fixture() -> ModalInferenceResponse:
    """Return contract-only test values; this helper never represents a model run."""

    return ModalInferenceResponse.model_validate(
        {
            "contract_version": "v1",
            "fixture": False,
            "implementation_status": "observed",
            "run_id": "rtj-0123456789abcdef",
            "cleanup_confirmed": True,
            "evaluation": {
                "contract_version": "v1",
                "result_status": "observed",
                "dataset_id": "rel-hm",
                "task_id": "rel-hm/user-churn",
                "task_type": "binary_classification",
                "dataset_revision": "a" * 40,
                "query_sha256": "b" * 64,
                "materialization_package_sha256": "c" * 64,
                "model_input_sha256": "d" * 64,
                "checkpoint": {
                    "repository_url": "https://huggingface.co/stanford-star/rt-j",
                    "revision": "a2c204c79d493ed0056661140e6fd24db3118381",
                    "variant": "classification",
                    "config_path": "classification/config.json",
                    "weights_path": "classification/model.safetensors",
                    "license": "CC-BY-NC-SA-4.0",
                },
                "config": {"gpu": "L40S"},
                "runtime": {
                    "provider": "modal",
                    "gpu": "L40S",
                    "duration_seconds": 12.5,
                    "source_revision": "f" * 40,
                    "checkpoint_revision": "a2c204c79d493ed0056661140e6fd24db3118381",
                },
                "sample_count": 32,
                "coverage": 1.0,
                "prediction_sha256": "1" * 64,
                "truth_sha256": "2" * 64,
                "integrity_checks": [
                    {
                        "name": "sealed_truth_boundary",
                        "status": "passed",
                        "detail": "Contract test fixture only.",
                    }
                ],
                "prevalence": 0.5,
                "metrics": {
                    "auroc": 0.5,
                    "average_precision": 0.5,
                    "log_loss": 0.7,
                    "brier_score": 0.25,
                    "accuracy": 0.5,
                    "f1": 0.5,
                },
            },
        }
    )


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
        "/v1/inferences/modal",
        "/v1/inferences/simulated",
        "/v1/materializations/daytona",
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


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost"])
def test_local_frontend_origin_is_allowed_by_cors(host: str) -> None:
    origin = f"http://{host}:4174"
    response = TestClient(create_app(Settings(environment="test"))).options(
        "/v1/datasets/rel-hm",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


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


def test_simulated_inference_is_repeatable_and_explicitly_not_model_output() -> None:
    client = TestClient(create_app(Settings(environment="test")))
    request = {
        "contract_version": "v1",
        "dataset_id": "rel-hm",
        "task_id": "rel-hm/item-sales",
        "task_type": "regression",
    }

    first = client.post("/v1/inferences/simulated", json=request)
    second = client.post("/v1/inferences/simulated", json=request)

    assert first.status_code == 200
    assert first.json() == second.json()
    assert first.json()["implementation_status"] == "simulated"
    assert first.json()["run"]["message"] == (
        "Seeded pseudo-random demo result; no model inference occurred."
    )
    assert first.json()["evaluation"]["task_type"] == "regression"
    assert first.json()["evaluation"]["provenance"]["model_id"] == "seeded-random-demo"
    assert first.json()["evaluation"]["integrity_checks"][0]["status"] == "not_run"


def test_simulated_inference_supports_churn_and_rejects_misaligned_defaults() -> None:
    client = TestClient(create_app(Settings(environment="test")))
    request = {
        "contract_version": "v1",
        "dataset_id": "rel-hm",
        "task_id": "rel-hm/user-churn",
        "task_type": "binary_classification",
    }

    response = client.post("/v1/inferences/simulated", json=request)
    invalid = client.post(
        "/v1/inferences/simulated",
        json={**request, "task_type": "regression"},
    )

    assert response.status_code == 200
    assert response.json()["evaluation"]["task_type"] == "binary_classification"
    assert "auroc" in response.json()["evaluation"]["metrics"]
    assert invalid.status_code == 422


def test_modal_inference_is_disabled_by_default() -> None:
    settings = Settings(
        environment="test",
        enable_modal_ui=False,
        allow_real_hm=False,
        allow_rtj_modal=False,
    )
    response = TestClient(create_app(settings)).post(
        "/v1/inferences/modal",
        json={
            "contract_version": "v1",
            "dataset_id": "rel-hm",
            "task_id": "rel-hm/user-churn",
            "approved": True,
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "modal_ui_disabled",
        "message": "Observed Modal inference is disabled in the local API configuration.",
    }


def test_modal_inference_returns_only_sanitized_observed_evaluation() -> None:
    received: list[ModalInferenceRequest] = []

    def run(request: ModalInferenceRequest) -> ModalInferenceResponse:
        received.append(request)
        return observed_modal_contract_fixture()

    client = TestClient(create_app(Settings(environment="test"), modal_inference_runner=run))
    response = client.post(
        "/v1/inferences/modal",
        json={
            "contract_version": "v1",
            "dataset_id": "rel-hm",
            "task_id": "rel-hm/user-churn",
            "approved": True,
        },
    )

    assert response.status_code == 200
    assert received == [
        ModalInferenceRequest(
            contract_version="v1",
            dataset_id="rel-hm",
            task_id="rel-hm/user-churn",
            approved=True,
        )
    ]
    payload = response.json()
    assert payload["implementation_status"] == "observed"
    assert payload["evaluation"]["runtime"]["gpu"] == "L40S"
    assert payload["evaluation"]["sample_count"] == 32
    assert "prediction_file" not in payload
    assert "output_root" not in payload


@pytest.mark.parametrize(
    "request_update",
    [
        {"approved": False},
        {"task_id": "rel-hm/item-sales"},
    ],
)
def test_modal_inference_rejects_unapproved_or_unreviewed_ui_runs(
    request_update: dict[str, object],
) -> None:
    request = {
        "contract_version": "v1",
        "dataset_id": "rel-hm",
        "task_id": "rel-hm/user-churn",
        "approved": True,
        **request_update,
    }

    response = TestClient(create_app(Settings(environment="test"))).post(
        "/v1/inferences/modal", json=request
    )

    assert response.status_code == 422


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


def test_daytona_route_launches_only_the_explicitly_approved_reviewed_task() -> None:
    received_task_ids: list[str] = []

    def materialize(task_ids: Sequence[TaskId]) -> DaytonaMaterializationResponse:
        received_task_ids.extend(task_ids)
        return successful_daytona_response()

    client = TestClient(create_app(Settings(environment="test"), daytona_materializer=materialize))
    response = client.post(
        "/v1/materializations/daytona",
        json={
            "contract_version": "v1",
            "dataset_id": "rel-hm",
            "task_ids": ["rel-hm/item-sales"],
            "approved": True,
        },
    )

    assert response.status_code == 200
    assert received_task_ids == ["rel-hm/item-sales"]
    assert response.json()["tasks"] == [
        {
            "task_id": "rel-hm/item-sales",
            "package_sha256": "a" * 64,
            "validation_status": "passed",
            "train_rows": 12,
            "validation_rows": 4,
            "test_rows": 4,
        }
    ]
    assert response.json()["cleanup_confirmed"] is True


@pytest.mark.parametrize(
    "request_update",
    [
        {"approved": False},
        {"task_ids": ["rel-hm/unknown"]},
        {"task_ids": ["rel-hm/user-churn", "rel-hm/user-churn"]},
    ],
)
def test_daytona_route_rejects_unapproved_or_unreviewed_requests(
    request_update: dict[str, object],
) -> None:
    request = {
        "contract_version": "v1",
        "dataset_id": "rel-hm",
        "task_ids": ["rel-hm/user-churn"],
        "approved": True,
        **request_update,
    }
    response = TestClient(create_app(Settings(environment="test"))).post(
        "/v1/materializations/daytona",
        json=request,
    )

    assert response.status_code == 422


def test_daytona_route_sanitizes_missing_credentials_and_provider_failures() -> None:
    def missing_credential(_: Sequence[TaskId]) -> DaytonaMaterializationResponse:
        raise DaytonaExecutionError("missing_credential", "Server credential is unavailable")

    def provider_failure(_: Sequence[TaskId]) -> DaytonaMaterializationResponse:
        raise RuntimeError("secret provider detail")

    missing_response = TestClient(
        create_app(Settings(environment="test"), daytona_materializer=missing_credential)
    ).post(
        "/v1/materializations/daytona",
        json={
            "contract_version": "v1",
            "dataset_id": "rel-hm",
            "task_ids": ["rel-hm/user-churn"],
            "approved": True,
        },
    )
    failure_response = TestClient(
        create_app(Settings(environment="test"), daytona_materializer=provider_failure)
    ).post(
        "/v1/materializations/daytona",
        json={
            "contract_version": "v1",
            "dataset_id": "rel-hm",
            "task_ids": ["rel-hm/item-sales"],
            "approved": True,
        },
    )

    assert missing_response.status_code == 503
    assert missing_response.json()["detail"] == {
        "code": "missing_credential",
        "message": "Server credential is unavailable",
    }
    assert failure_response.status_code == 500
    assert failure_response.json()["detail"] == {
        "code": "materialization_failure",
        "message": "Synthetic Daytona materialization failed",
    }


def test_invalid_log_level_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(log_level="TRACE")
