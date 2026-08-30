from __future__ import annotations

from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError
from structagent_api.catalog import REL_HM_DEFAULT_TASKS
from structagent_api.contracts import (
    DatasetDescriptor,
    DaytonaMaterializationRequest,
    DefaultTaskCatalog,
    DefaultTaskSqlArtifact,
    MaterializedFileReference,
    TaskDraftOutcome,
)
from structagent_api.contracts.models import IntegrityCheck


def dataset_payload() -> dict[str, Any]:
    return {
        "contract_version": "v1",
        "fixture": True,
        "implementation_status": "metadata_only",
        "dataset_id": "sample-retail",
        "display_name": "Sample Retail",
        "description": "Synthetic metadata used by contract tests.",
        "supported_task_types": ["binary_classification", "regression"],
        "tables": [
            {
                "name": "customer",
                "columns": [
                    {
                        "name": "customer_id",
                        "data_type": "string",
                        "primary_key": True,
                    }
                ],
            },
            {
                "name": "event",
                "columns": [
                    {
                        "name": "customer_id",
                        "data_type": "string",
                        "foreign_key": {
                            "table": "customer",
                            "column": "customer_id",
                        },
                    },
                    {
                        "name": "occurred_at",
                        "data_type": "timestamp",
                        "time_column": True,
                    },
                ],
            },
        ],
    }


def test_dataset_descriptor_accepts_valid_relationships() -> None:
    descriptor = DatasetDescriptor.model_validate(dataset_payload())

    assert descriptor.dataset_id == "sample-retail"
    assert descriptor.tables[1].columns[0].foreign_key is not None
    assert descriptor.tables[1].columns[0].foreign_key.table == "customer"


def test_dataset_descriptor_rejects_unknown_relationship_target() -> None:
    payload = dataset_payload()
    payload["tables"][1]["columns"][0]["foreign_key"]["table"] = "missing"

    with pytest.raises(ValidationError, match="unknown table missing"):
        DatasetDescriptor.model_validate(payload)


def test_contract_version_and_unknown_fields_fail_closed() -> None:
    payload = dataset_payload()
    payload["contract_version"] = "v2"
    payload["unexpected"] = "value"

    with pytest.raises(ValidationError):
        DatasetDescriptor.model_validate(payload)


def test_clarification_requires_meaningful_choices() -> None:
    payload = {
        "contract_version": "v1",
        "fixture": True,
        "implementation_status": "placeholder",
        "outcome": "needs_clarification",
        "draft_id": "draft-1",
        "questions": [
            {
                "question_id": "window",
                "prompt": "Which prediction window should be used?",
                "answer_kind": "single_choice",
                "choices": ["seven days"],
            }
        ],
    }

    with pytest.raises(ValidationError, match="at least two choices"):
        TypeAdapter(TaskDraftOutcome).validate_python(payload)


def test_non_generated_query_cannot_contain_sql() -> None:
    query = {
        "purpose": "label",
        "status": "not_generated",
        "dialect": "duckdb",
        "sql": "SELECT 1",
    }

    draft = {
        "contract_version": "v1",
        "fixture": True,
        "implementation_status": "placeholder",
        "outcome": "draft_ready",
        "contract": {
            "draft_id": "draft-1",
            "dataset_id": "sample-retail",
            "task_type": "binary_classification",
            "entity": {"table": "customer", "key_column": "customer_id"},
            "prediction_time": {"table": "event", "column": "occurred_at"},
            "horizon": {"value": 7, "unit": "days"},
            "target": {
                "name": "churn",
                "description": "No future event in the prediction window.",
                "positive_class": "no future event",
                "unit": None,
            },
            "eligibility_definition": "Customers with a prior event.",
            "label_definition": "One when no future event exists, otherwise zero.",
            "query_artifacts": [
                query,
                {
                    "purpose": "eligibility",
                    "status": "not_generated",
                    "dialect": "duckdb",
                    "sql": None,
                },
            ],
            "recommended_metrics": ["auroc"],
        },
    }

    with pytest.raises(ValidationError, match="cannot contain SQL"):
        TypeAdapter(TaskDraftOutcome).validate_python(draft)


def test_integrity_check_distinguishes_not_run_from_passed() -> None:
    check = IntegrityCheck(
        name="point_in_time",
        status="not_run",
        detail="Synthetic fixture; no validation executed.",
    )

    assert check.status == "not_run"

    with pytest.raises(ValidationError):
        IntegrityCheck.model_validate(
            {
                "name": "point_in_time",
                "passed": True,
                "detail": "Legacy ambiguous representation.",
            }
        )


def test_default_task_catalog_rejects_duplicate_task_ids() -> None:
    payload = REL_HM_DEFAULT_TASKS.model_dump(mode="json")
    payload["tasks"].append(payload["tasks"][0])

    with pytest.raises(ValidationError, match="duplicate task IDs"):
        DefaultTaskCatalog.model_validate(payload)


def test_default_task_catalog_rejects_non_hm_dataset_or_custom_source() -> None:
    mismatched_dataset = REL_HM_DEFAULT_TASKS.model_dump(mode="json")
    mismatched_dataset["tasks"][0]["dataset_id"] = "rel-amazon"

    with pytest.raises(ValidationError):
        DefaultTaskCatalog.model_validate(mismatched_dataset)

    custom_source = REL_HM_DEFAULT_TASKS.model_dump(mode="json")
    custom_source["tasks"][0]["source"] = "custom"

    with pytest.raises(ValidationError):
        DefaultTaskCatalog.model_validate(custom_source)


def test_default_task_catalog_rejects_unknown_or_recommendation_tasks() -> None:
    unknown_task = REL_HM_DEFAULT_TASKS.model_dump(mode="json")
    unknown_task["tasks"][0]["task_id"] = "rel-hm/unknown"

    with pytest.raises(ValidationError):
        DefaultTaskCatalog.model_validate(unknown_task)

    recommendation = REL_HM_DEFAULT_TASKS.model_dump(mode="json")
    recommendation["tasks"][0]["task_type"] = "recommendation"

    with pytest.raises(ValidationError):
        DefaultTaskCatalog.model_validate(recommendation)


def test_daytona_materialization_request_requires_explicit_unique_reviewed_tasks() -> None:
    request = DaytonaMaterializationRequest(
        contract_version="v1",
        dataset_id="rel-hm",
        task_ids=["rel-hm/user-churn", "rel-hm/item-sales"],
        approved=True,
    )

    assert request.task_ids == ["rel-hm/user-churn", "rel-hm/item-sales"]
    with pytest.raises(ValidationError, match="duplicate task IDs"):
        DaytonaMaterializationRequest.model_validate(
            {
                **request.model_dump(mode="json"),
                "task_ids": ["rel-hm/user-churn", "rel-hm/user-churn"],
            }
        )


def test_materialized_file_paths_must_be_relative_and_normalized() -> None:
    payload = {
        "path": "../sealed/test-truth.parquet",
        "sha256": "a" * 64,
        "row_count": 1,
        "byte_count": 10,
        "columns": ["timestamp", "customer_id", "churn"],
    }

    with pytest.raises(ValidationError, match="normalized relative POSIX path"):
        MaterializedFileReference.model_validate(payload)


def test_task_sql_artifact_rejects_shape_that_disagrees_with_task_id() -> None:
    payload = {
        "contract_version": "v1",
        "dataset_id": "rel-hm",
        "task_id": "rel-hm/user-churn",
        "source": "default",
        "dialect": "duckdb",
        "sql": "SELECT 1",
        "normalized_sql": "SELECT 1",
        "query_sha256": "a" * 64,
        "entity_table": "article",
        "entity_column": "article_id",
        "target_column": "sales",
        "task_type": "regression",
        "horizon_days": 7,
        "provenance": {
            "repository_url": "https://example.com/repository",
            "revision": "b" * 40,
            "path": "manifest.yaml",
            "sha256": "c" * 64,
        },
        "validation_report": {
            "status": "passed",
            "checks": [{"code": "static", "status": "passed", "detail": "Reviewed."}],
        },
    }

    with pytest.raises(ValidationError, match="does not match its reviewed default"):
        DefaultTaskSqlArtifact.model_validate(payload)
