from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter
from structagent_api.catalog import REL_HM_DEFAULT_TASKS
from structagent_api.contracts import (
    ClassificationEvaluationResult,
    DatasetDescriptor,
    DefaultTaskCatalog,
    DraftReady,
    EvaluationResult,
    NeedsClarification,
    RegressionEvaluationResult,
    RunRecord,
    TaskDraftOutcome,
    TaskDraftRequest,
)

EXAMPLE_ROOT = Path(__file__).resolve().parents[3] / "contracts" / "v1" / "examples"


def load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict), f"{path} must contain a JSON object"
    return payload


def fixture_paths(filename: str) -> list[Path]:
    return sorted(EXAMPLE_ROOT.glob(f"*/{filename}"))


@pytest.mark.parametrize("path", fixture_paths("dataset.json"), ids=lambda path: path.parent.name)
def test_dataset_fixtures_are_metadata_only(path: Path) -> None:
    descriptor = DatasetDescriptor.model_validate_json(path.read_text(encoding="utf-8"))

    assert descriptor.dataset_id == path.parent.name
    assert descriptor.fixture is True
    assert descriptor.implementation_status == "metadata_only"
    assert set(descriptor.supported_task_types) == {"binary_classification", "regression"}


@pytest.mark.parametrize(
    "path",
    fixture_paths("task-draft-request.json"),
    ids=lambda path: path.parent.name,
)
def test_task_request_fixtures_target_their_dataset(path: Path) -> None:
    request = TaskDraftRequest.model_validate_json(path.read_text(encoding="utf-8"))

    assert request.dataset_id == path.parent.name


@pytest.mark.parametrize(
    "path",
    fixture_paths("needs-clarification.json") + fixture_paths("task-contract.json"),
    ids=lambda path: f"{path.parent.name}-{path.stem}",
)
def test_task_outcome_fixtures_are_valid_placeholders(path: Path) -> None:
    outcome: NeedsClarification | DraftReady = TypeAdapter(TaskDraftOutcome).validate_json(
        path.read_text(encoding="utf-8")
    )

    assert outcome.fixture is True
    assert outcome.implementation_status == "placeholder"
    if outcome.outcome == "draft_ready":
        assert outcome.contract.source == "custom"
        assert outcome.contract.dataset_id == path.parent.name
        assert {artifact.status for artifact in outcome.contract.query_artifacts} == {
            "not_generated"
        }
        assert all(artifact.sql is None for artifact in outcome.contract.query_artifacts)


@pytest.mark.parametrize(
    "path", fixture_paths("run-record.json"), ids=lambda path: path.parent.name
)
def test_run_fixtures_disclose_that_no_execution_occurred(path: Path) -> None:
    run = RunRecord.model_validate_json(path.read_text(encoding="utf-8"))

    assert run.fixture is True
    assert "no execution occurred" in run.message.lower()


@pytest.mark.parametrize(
    "path",
    fixture_paths("evaluation-result.json"),
    ids=lambda path: path.parent.name,
)
def test_result_fixtures_are_synthetic_and_unexecuted(path: Path) -> None:
    result: ClassificationEvaluationResult | RegressionEvaluationResult = TypeAdapter(
        EvaluationResult
    ).validate_json(path.read_text(encoding="utf-8"))

    assert result.fixture is True
    assert result.dataset_id == path.parent.name
    assert result.provenance.dataset_revision == "fixture-only"
    assert result.provenance.model_revision == "fixture-only"
    assert {check.status for check in result.integrity_checks} == {"not_run"}


def test_hm_default_task_fixture_matches_the_reviewed_catalog() -> None:
    path = EXAMPLE_ROOT / "rel-hm" / "default-tasks.json"
    catalog = DefaultTaskCatalog.model_validate_json(path.read_text(encoding="utf-8"))

    assert catalog == REL_HM_DEFAULT_TASKS
    assert [task.task_id for task in catalog.tasks] == [
        "rel-hm/user-churn",
        "rel-hm/item-sales",
    ]

    churn, item_sales = catalog.tasks
    assert churn.entity.model_dump() == {
        "table": "customer",
        "key_column": "customer_id",
    }
    assert churn.task_type == "binary_classification"
    assert churn.target.model_dump() == {
        "name": "churn",
        "description": (
            "One when an eligible customer makes no transaction in the next seven "
            "days; otherwise zero."
        ),
        "positive_class": "No transaction in (timestamp, timestamp + 7 days].",
        "unit": None,
    }
    assert churn.eligibility_definition == (
        "Customer has at least one transaction in (timestamp - 7 days, timestamp]."
    )
    assert churn.label_definition == (
        "One when no customer transaction occurs in "
        "(timestamp, timestamp + 7 days]; otherwise zero."
    )
    assert churn.benchmark_metric == "roc_auc"
    assert churn.diagnostic_metrics == [
        "average_precision",
        "accuracy",
        "f1",
        "log_loss",
        "brier_score",
    ]
    assert churn.upstream_manifest.sha256 == (
        "546bef09917d3453e00bd25d356493c7dd97c9a9039fc9af37c4997fef8aa9f9"
    )
    assert churn.upstream_manifest.revision == ("d8e976fd0a4b78877204bc8dfbcfc9a9f7f48600")
    assert churn.upstream_manifest.path == "rel-hm/tasks/user-churn/manifest.yaml"

    assert item_sales.entity.model_dump() == {
        "table": "article",
        "key_column": "article_id",
    }
    assert item_sales.task_type == "regression"
    assert item_sales.target.model_dump() == {
        "name": "sales",
        "description": (
            "Sum of transaction price values for the article over the next seven days, "
            "or zero when no transaction occurs."
        ),
        "positive_class": None,
        "unit": "sum of transaction price values",
    }
    assert item_sales.eligibility_definition == (
        "Every known article at each prediction timestamp."
    )
    assert item_sales.label_definition == (
        "Sum transaction price for the article in "
        "(timestamp, timestamp + 7 days], defaulting to zero."
    )
    assert item_sales.benchmark_metric == "nmae"
    assert item_sales.diagnostic_metrics == ["mae", "rmse", "r2"]
    assert item_sales.upstream_manifest.sha256 == (
        "fc3f971da007d7c17872d3c0d840ca79609af5942ebec166154d4aaf9e7a6675"
    )
    assert item_sales.upstream_manifest.revision == ("d8e976fd0a4b78877204bc8dfbcfc9a9f7f48600")
    assert item_sales.upstream_manifest.path == "rel-hm/tasks/item-sales/manifest.yaml"

    assert all(task.prediction_time.table == "timestamps" for task in catalog.tasks)
    assert all(task.prediction_time.column == "timestamp" for task in catalog.tasks)
    assert all(task.horizon.model_dump() == {"value": 7, "unit": "days"} for task in catalog.tasks)
    assert catalog.benchmark_evaluator.sha256 == (
        "bc2f1fad23405e2f8c195d6079cb8883b9e652aec4f2868a5ccd884aba08f5c5"
    )
    assert catalog.benchmark_evaluator.revision == ("9a223758cea1fd486a8d20f9e2f7ac4f42c88d0f")


def test_every_example_json_has_a_known_contract_role() -> None:
    expected_names = {
        "dataset.json",
        "default-tasks.json",
        "evaluation-result.json",
        "needs-clarification.json",
        "run-record.json",
        "task-contract.json",
        "task-draft-request.json",
    }

    paths = sorted(EXAMPLE_ROOT.rglob("*.json"))
    assert {path.name for path in paths} == expected_names
    assert {path.parent.name for path in paths} == {"rel-amazon", "rel-hm"}
    assert all(load_object(path) for path in paths)
