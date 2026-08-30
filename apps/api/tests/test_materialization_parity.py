from __future__ import annotations

from pathlib import Path

import duckdb
import pytest
from structagent_api.materialization import (
    SYNTHETIC_CUTOFFS,
    create_synthetic_hm,
    materialize_default_task,
)
from structagent_api.materialization.parity import ParityError, verify_materialization_parity
from structagent_api.materialization.task_sql import TaskId


def sql_literal(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def generated_and_expected(
    tmp_path: Path,
    task_id: TaskId,
) -> tuple[Path, dict[str, Path]]:
    dataset = create_synthetic_hm(tmp_path / "dataset")
    generated = tmp_path / "generated"
    expected = tmp_path / "expected"
    materialize_default_task(
        task_id,
        dataset,
        generated,
        cutoffs=SYNTHETIC_CUTOFFS,
    )
    materialize_default_task(
        task_id,
        dataset,
        expected,
        cutoffs=SYNTHETIC_CUTOFFS,
    )
    return generated, {
        "train": expected / "train.parquet",
        "validation": expected / "validation.parquet",
        "test": expected / "test-truth.parquet",
    }


@pytest.mark.parametrize("task_id", ["rel-hm/user-churn", "rel-hm/item-sales"])
def test_parity_accepts_exact_generated_labels(tmp_path: Path, task_id: TaskId) -> None:
    generated, expected = generated_and_expected(tmp_path, task_id)

    report = verify_materialization_parity(
        task_id,
        generated,
        expected,
    )

    assert report.status == "passed"
    assert [split.split for split in report.splits] == ["train", "validation", "test"]
    assert all(split.key_mismatches == 0 for split in report.splits)
    assert all(split.target_mismatches == 0 for split in report.splits)


def test_parity_rejects_target_mismatch(tmp_path: Path) -> None:
    generated, expected = generated_and_expected(tmp_path, "rel-hm/user-churn")
    modified = tmp_path / "modified.parquet"
    connection = duckdb.connect()
    try:
        reviewed_path = sql_literal(expected["test"])
        connection.execute(
            f"CREATE TEMP VIEW reviewed AS SELECT * FROM read_parquet({reviewed_path})"
        )
        connection.execute(
            "COPY (SELECT timestamp, customer_id, 1 - churn AS churn FROM reviewed) "
            "TO ? (FORMAT PARQUET)",
            [str(modified)],
        )
    finally:
        connection.close()
    expected["test"] = modified

    with pytest.raises(ParityError) as raised:
        verify_materialization_parity("rel-hm/user-churn", generated, expected)

    assert raised.value.code == "parity_mismatch"


def test_parity_rejects_missing_entity(tmp_path: Path) -> None:
    generated, expected = generated_and_expected(tmp_path, "rel-hm/item-sales")
    modified = tmp_path / "modified.parquet"
    connection = duckdb.connect()
    try:
        connection.execute(
            "CREATE TEMP VIEW reviewed AS SELECT * FROM read_parquet("
            f"{sql_literal(expected['validation'])})"
        )
        connection.execute(
            "COPY (SELECT * FROM reviewed LIMIT 1) TO ? (FORMAT PARQUET)",
            [str(modified)],
        )
    finally:
        connection.close()
    expected["validation"] = modified

    with pytest.raises(ParityError) as raised:
        verify_materialization_parity("rel-hm/item-sales", generated, expected)

    assert raised.value.code == "parity_mismatch"
