from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import pytest
from structagent_api.contracts import TaskSqlArtifact
from structagent_api.contracts.models import TaskValidationReport
from structagent_api.materialization import (
    HMDatasetFiles,
    MaterializationError,
    TemporalCutoffs,
    build_default_task_sql,
    materialize_default_task,
    materialize_task,
)
from structagent_api.materialization.task_sql import TaskId, validate_task_sql

TEST_CUTOFFS = TemporalCutoffs(
    validation=datetime(2020, 1, 22),
    test=datetime(2020, 1, 29),
)


def _copy_table(connection: duckdb.DuckDBPyConnection, table: str, path: Path) -> None:
    connection.execute(
        f"COPY {table} TO ? (FORMAT PARQUET, COMPRESSION ZSTD)",
        [str(path)],
    )


def synthetic_hm(tmp_path: Path, *, complete_test_window: bool = True) -> HMDatasetFiles:
    root = tmp_path / "dataset"
    root.mkdir()
    connection = duckdb.connect()
    try:
        connection.execute("CREATE TABLE customer(customer_id VARCHAR PRIMARY KEY, age DOUBLE)")
        connection.execute(
            """
            CREATE TABLE article(
                article_id BIGINT PRIMARY KEY,
                product_type_name VARCHAR,
                detail_desc VARCHAR
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE transactions(
                customer_id VARCHAR,
                article_id BIGINT,
                t_dat TIMESTAMP,
                price DOUBLE,
                sales_channel_id BIGINT
            )
            """
        )
        connection.executemany(
            "INSERT INTO article VALUES (?, ?, ?)",
            [(1, "shirt", "Synthetic shirt"), (2, "trouser", "Synthetic trouser")],
        )

        prediction_times = [datetime(2020, 1, 1) + timedelta(days=7 * index) for index in range(5)]
        customers: list[tuple[str, float]] = [("sentinel", 30.0)]
        transactions: list[tuple[str, int, datetime, float, int]] = []
        for index, timestamp in enumerate(prediction_times):
            churner = f"churn-{index}"
            retained = f"retained-{index}"
            customers.extend([(churner, 20.0 + index), (retained, 40.0 + index)])
            transactions.extend(
                [
                    (churner, 1, timestamp - timedelta(days=1), 1.0, 1),
                    (retained, 1, timestamp - timedelta(days=1), 1.0, 1),
                    (retained, 1, timestamp + timedelta(days=1), 2.0, 2),
                ]
            )
        if complete_test_window:
            transactions.append(("sentinel", 2, TEST_CUTOFFS.test + timedelta(days=7), 3.0, 1))

        connection.executemany("INSERT INTO customer VALUES (?, ?)", customers)
        connection.executemany("INSERT INTO transactions VALUES (?, ?, ?, ?, ?)", transactions)
        for table in ("article", "customer", "transactions"):
            _copy_table(connection, table, root / f"{table}.parquet")
    finally:
        connection.close()
    return HMDatasetFiles.from_directory(root, revision="synthetic")


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
    dataset = synthetic_hm(tmp_path)
    output_dir = tmp_path / "output"

    result = materialize_default_task(
        task_id,
        dataset,
        output_dir,
        cutoffs=TEST_CUTOFFS,
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
    dataset = synthetic_hm(tmp_path)
    task = _replace_task_sql(
        "rel-hm/user-churn",
        """
        SELECT timestamp, customer.customer_id, CAST(0 AS INTEGER) AS churn
        FROM timestamps, customer, transactions
        WHERE transactions.t_dat <= timestamp + INTERVAL '7 days'
        """,
    )

    with pytest.raises(MaterializationError) as raised:
        materialize_task(task, dataset, tmp_path / "output", cutoffs=TEST_CUTOFFS)

    assert raised.value.code == "unique_keys"


def test_materializer_rejects_invalid_binary_targets(tmp_path: Path) -> None:
    dataset = synthetic_hm(tmp_path)
    task = _replace_task_sql(
        "rel-hm/user-churn",
        """
        SELECT timestamp, customer_id, CAST(2 AS INTEGER) AS churn
        FROM timestamps, customer
        WHERE timestamp < timestamp + INTERVAL '7 days'
        """,
    )

    with pytest.raises(MaterializationError) as raised:
        materialize_task(task, dataset, tmp_path / "output", cutoffs=TEST_CUTOFFS)

    assert raised.value.code == "binary_targets"


def test_materializer_rejects_non_finite_regression_targets(tmp_path: Path) -> None:
    dataset = synthetic_hm(tmp_path)
    task = _replace_task_sql(
        "rel-hm/item-sales",
        """
        SELECT timestamp, article_id, CAST('NaN' AS DOUBLE) AS sales
        FROM timestamps, article
        WHERE timestamp < timestamp + INTERVAL '7 days'
        """,
    )

    with pytest.raises(MaterializationError) as raised:
        materialize_task(task, dataset, tmp_path / "output", cutoffs=TEST_CUTOFFS)

    assert raised.value.code == "finite_targets"


def test_materializer_rejects_incomplete_test_window(tmp_path: Path) -> None:
    dataset = synthetic_hm(tmp_path, complete_test_window=False)

    with pytest.raises(MaterializationError) as raised:
        materialize_default_task(
            "rel-hm/item-sales",
            dataset,
            tmp_path / "output",
            cutoffs=TEST_CUTOFFS,
        )

    assert raised.value.code == "outcome_windows"
