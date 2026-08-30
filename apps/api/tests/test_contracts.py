from __future__ import annotations

from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError
from structagent_api.contracts import DatasetDescriptor, TaskDraftOutcome


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
