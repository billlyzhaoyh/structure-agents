from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from structagent_api.contracts import TaskSqlArtifact
from structagent_api.contracts.models import TaskValidationReport
from structagent_api.materialization import (
    SYNTHETIC_CUTOFFS,
    MaterializationError,
    build_default_task_sql,
    create_synthetic_hm,
    materialize_default_task,
    materialize_task,
)
from structagent_api.materialization.task_sql import TaskId, validate_task_sql


@pytest.mark.parametrize(
    ("task_id", "entity_column", "target_column"),
    [
        ("rel-hm/user-churn", "customer_id", "churn"),
        ("rel-hm/item-sales", "article_id", "sales"),
    ],
)
def test_default_tasks_materialize_with_sealed_truth(
    tmp_path: Path,
    task_id: TaskId,
    entity_column: str,
    target_column: str,
) -> None:
    dataset = create_synthetic_hm(tmp_path / "dataset")
    output_dir = tmp_path / "output"

    result = materialize_default_task(
        task_id,
        dataset,
        output_dir,
        cutoffs=SYNTHETIC_CUTOFFS,
    )

    assert result.validation_report.status == "passed"
    assert result.model_input.test_rows.columns == ["timestamp", entity_column]
    assert result.evaluator_truth.test_truth.columns == [
        "timestamp",
        entity_column,
        target_column,
    ]
    assert result.model_input.test_rows.row_count == result.evaluator_truth.test_truth.row_count
    assert "test_truth" not in result.model_input.model_dump(mode="json")
    model_input_payload = result.model_input.model_dump(mode="json")
    expected_model_digest = hashlib.sha256(
        json.dumps(model_input_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    assert result.model_input_sha256 == expected_model_digest
    assert (output_dir / "manifest.json").is_file()
    assert result.package_sha256 in (output_dir / "manifest.json").read_text(encoding="utf-8")


def _replace_task_sql(task_id: TaskId, sql: str) -> TaskSqlArtifact:
    base = build_default_task_sql(task_id)
    validated = validate_task_sql(
        sql,
        entity_column=base.entity_column,
        target_column=base.target_column,
        horizon_days=base.horizon_days,
    )
    return base.model_copy(
        update={
            "sql": sql,
            "normalized_sql": validated.normalized,
            "query_sha256": validated.sha256,
            "validation_report": TaskValidationReport(
                status="passed", checks=list(validated.checks)
            ),
        }
    )


def test_materializer_rejects_duplicate_rows(tmp_path: Path) -> None:
    dataset = create_synthetic_hm(tmp_path / "dataset")
    task = _replace_task_sql(
        "rel-hm/user-churn",
        """
        SELECT timestamp, customer.customer_id, CAST(0 AS INTEGER) AS churn
        FROM timestamps, customer, transactions
        WHERE transactions.t_dat <= timestamp + INTERVAL '7 days'
        """,
    )

    with pytest.raises(MaterializationError) as raised:
        materialize_task(task, dataset, tmp_path / "output", cutoffs=SYNTHETIC_CUTOFFS)

    assert raised.value.code == "unique_keys"


def test_materializer_rejects_invalid_binary_targets(tmp_path: Path) -> None:
    dataset = create_synthetic_hm(tmp_path / "dataset")
    task = _replace_task_sql(
        "rel-hm/user-churn",
        """
        SELECT timestamp, customer_id, CAST(2 AS INTEGER) AS churn
        FROM timestamps, customer
        WHERE timestamp < timestamp + INTERVAL '7 days'
        """,
    )

    with pytest.raises(MaterializationError) as raised:
        materialize_task(task, dataset, tmp_path / "output", cutoffs=SYNTHETIC_CUTOFFS)

    assert raised.value.code == "binary_targets"


def test_materializer_rejects_non_finite_regression_targets(tmp_path: Path) -> None:
    dataset = create_synthetic_hm(tmp_path / "dataset")
    task = _replace_task_sql(
        "rel-hm/item-sales",
        """
        SELECT timestamp, article_id, CAST('NaN' AS DOUBLE) AS sales
        FROM timestamps, article
        WHERE timestamp < timestamp + INTERVAL '7 days'
        """,
    )

    with pytest.raises(MaterializationError) as raised:
        materialize_task(task, dataset, tmp_path / "output", cutoffs=SYNTHETIC_CUTOFFS)

    assert raised.value.code == "finite_targets"


def test_materializer_rejects_incomplete_test_window(tmp_path: Path) -> None:
    dataset = create_synthetic_hm(tmp_path / "dataset", complete_test_window=False)

    with pytest.raises(MaterializationError) as raised:
        materialize_default_task(
            "rel-hm/item-sales",
            dataset,
            tmp_path / "output",
            cutoffs=SYNTHETIC_CUTOFFS,
        )

    assert raised.value.code == "outcome_windows"
