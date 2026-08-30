from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError
from structagent_api.contracts import (
    CustomTaskSqlArtifact,
    DefaultTaskSqlArtifact,
    RTJCheckpointReference,
    RTJInferenceConfig,
    RTJInferenceRequest,
    TaskClarificationRequest,
    TaskSqlArtifact,
)
from structagent_api.contracts.models import ModelTaskPackage
from structagent_api.materialization import (
    SYNTHETIC_CUTOFFS,
    create_synthetic_hm,
    materialize_default_task,
)


def custom_sql_payload() -> dict[str, object]:
    return {
        "contract_version": "v1",
        "dataset_id": "rel-hm",
        "task_id": f"rel-hm/custom/{'a' * 64}",
        "source": "custom",
        "dialect": "duckdb",
        "sql": "SELECT timestamp, customer_id, 1 AS target",
        "normalized_sql": "SELECT timestamp, customer_id, 1 AS target",
        "query_sha256": "b" * 64,
        "entity_table": "customer",
        "entity_column": "customer_id",
        "target_column": "target",
        "task_type": "binary_classification",
        "horizon_days": 7,
        "provenance": {
            "model": "gpt-5.6-terra",
            "prompt_sha256": "c" * 64,
            "schema_sha256": "d" * 64,
            "instructions_sha256": "e" * 64,
            "attempt_count": 1,
        },
        "validation_report": {
            "status": "passed",
            "checks": [{"code": "static", "status": "passed", "detail": "Validated."}],
        },
    }


def test_task_sql_union_accepts_custom_artifacts() -> None:
    artifact: DefaultTaskSqlArtifact | CustomTaskSqlArtifact = TypeAdapter(
        TaskSqlArtifact
    ).validate_python(custom_sql_payload())

    assert isinstance(artifact, CustomTaskSqlArtifact)
    assert artifact.target_column == "target"


def test_custom_task_entity_must_use_reviewed_key() -> None:
    payload = custom_sql_payload()
    payload["entity_column"] = "article_id"

    with pytest.raises(ValidationError, match="reviewed key"):
        TypeAdapter(TaskSqlArtifact).validate_python(payload)


def test_clarification_request_is_stateless_and_typed() -> None:
    request = TaskClarificationRequest.model_validate(
        {
            "contract_version": "v1",
            "dataset_id": "rel-hm",
            "original_prompt": "Predict customers likely to become inactive.",
            "prior_questions": [
                {
                    "question_id": "horizon",
                    "prompt": "Which horizon?",
                    "answer_kind": "single_choice",
                    "choices": ["1 day", "7 days"],
                }
            ],
            "answers": [
                {
                    "question_id": "horizon",
                    "answer_kind": "single_choice",
                    "value": "7 days",
                }
            ],
        }
    )

    assert request.answers[0].value == "7 days"


def test_clarification_request_rejects_unanswered_questions() -> None:
    with pytest.raises(ValidationError, match="must match"):
        TaskClarificationRequest.model_validate(
            {
                "contract_version": "v1",
                "dataset_id": "rel-hm",
                "original_prompt": "Predict demand.",
                "prior_questions": [
                    {
                        "question_id": "horizon",
                        "prompt": "Which horizon?",
                        "answer_kind": "free_text",
                        "choices": [],
                    }
                ],
                "answers": [
                    {
                        "question_id": "entity",
                        "answer_kind": "free_text",
                        "value": "article",
                    }
                ],
            }
        )


def test_rtj_request_rejects_checkpoint_task_mismatch(tmp_path: Path) -> None:
    dataset = create_synthetic_hm(tmp_path / "dataset")
    materialized = materialize_default_task(
        "rel-hm/user-churn",
        dataset,
        tmp_path / "output",
        cutoffs=SYNTHETIC_CUTOFFS,
    )

    with pytest.raises(ValidationError, match="does not match"):
        RTJInferenceRequest(
            contract_version="v1",
            materialization_package_sha256=materialized.package_sha256,
            model_input_sha256=materialized.model_input_sha256,
            model_input=materialized.model_input,
            source_revision="455df27c1458e093eac00133d5bbf41a8263a2e3",
            checkpoint=RTJCheckpointReference(
                repository_url="https://huggingface.co/stanford-star/rt-j",
                revision="a2c204c79d493ed0056661140e6fd24db3118381",
                variant="regression",
                config_path="regression/config.json",
                weights_path="regression/model.safetensors",
                license="CC-BY-NC-SA-4.0",
            ),
            config=RTJInferenceConfig(),
        )


def test_rtj_request_schema_cannot_carry_evaluator_truth() -> None:
    schema = RTJInferenceRequest.model_json_schema()
    rendered = str(schema)

    assert "EvaluatorTruthPackage" not in rendered
    assert "test_truth" not in rendered


def test_model_package_rejects_truth_named_test_input(tmp_path: Path) -> None:
    dataset = create_synthetic_hm(tmp_path / "dataset")
    materialized = materialize_default_task(
        "rel-hm/user-churn",
        dataset,
        tmp_path / "output",
        cutoffs=SYNTHETIC_CUTOFFS,
    )
    payload = materialized.model_input.model_dump(mode="json")
    payload["test_rows"]["path"] = "test-truth.parquet"

    with pytest.raises(ValidationError, match="allowlist"):
        ModelTaskPackage.model_validate(payload)
