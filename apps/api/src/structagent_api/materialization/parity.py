"""Aggregate, row-aligned parity checks against pinned RelBench task labels."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import duckdb
from pydantic import BaseModel, ConfigDict

from structagent_api.contracts import MaterializationResult
from structagent_api.materialization.task_sql import TaskId


class ParityError(RuntimeError):
    """Sanitized mismatch between generated and reviewed task labels."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


class SplitParity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    split: Literal["train", "validation", "test"]
    generated_rows: int
    expected_rows: int
    key_mismatches: int
    target_mismatches: int
    maximum_absolute_error: float | None


class ParityReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["passed"]
    task_id: TaskId
    package_sha256: str
    splits: list[SplitParity]


def _sql_literal(path: Path) -> str:
    return "'" + str(path.resolve(strict=True)).replace("'", "''") + "'"


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _required_value(connection: duckdb.DuckDBPyConnection, query: str) -> Any:
    row = connection.execute(query).fetchone()
    if row is None:
        raise ParityError("parity_query", "DuckDB returned no parity aggregate")
    return row[0]


def _verify_split(
    connection: duckdb.DuckDBPyConnection,
    *,
    split: Literal["train", "validation", "test"],
    generated_path: Path,
    expected_path: Path,
    entity_column: str,
    target_column: str,
    task_type: str,
) -> SplitParity:
    connection.execute("DROP VIEW IF EXISTS generated_labels")
    connection.execute("DROP VIEW IF EXISTS expected_labels")
    generated_literal = _sql_literal(generated_path)
    expected_literal = _sql_literal(expected_path)
    connection.execute(
        f"CREATE TEMP VIEW generated_labels AS SELECT * FROM read_parquet({generated_literal})"
    )
    connection.execute(
        f"CREATE TEMP VIEW expected_labels AS SELECT * FROM read_parquet({expected_literal})"
    )

    expected_columns = ["timestamp", entity_column, target_column]
    generated_columns = [
        row[0] for row in connection.execute("DESCRIBE generated_labels").fetchall()
    ]
    reviewed_columns = [row[0] for row in connection.execute("DESCRIBE expected_labels").fetchall()]
    if generated_columns != expected_columns or reviewed_columns != expected_columns:
        raise ParityError("parity_schema", f"{split} label schemas are not aligned")

    entity = _quote_identifier(entity_column)
    target = _quote_identifier(target_column)
    generated_rows = int(_required_value(connection, "SELECT COUNT(*) FROM generated_labels"))
    expected_rows = int(_required_value(connection, "SELECT COUNT(*) FROM expected_labels"))
    expected_duplicates = int(
        _required_value(
            connection,
            f"""
            SELECT COUNT(*)
            FROM (
                SELECT timestamp, {entity}
                FROM expected_labels
                GROUP BY timestamp, {entity}
                HAVING COUNT(*) > 1
            )
            """,
        )
    )
    if expected_duplicates:
        raise ParityError("parity_keys", f"{split} reviewed labels contain duplicate keys")

    if task_type == "binary_classification":
        target_mismatch = f"g.{target} IS DISTINCT FROM e.{target}"
        maximum_error = "NULL"
    else:
        tolerance = (
            f"1e-12 + 1e-9 * GREATEST(ABS(CAST(g.{target} AS DOUBLE)), "
            f"ABS(CAST(e.{target} AS DOUBLE)))"
        )
        target_mismatch = (
            f"g.{target} IS NULL OR e.{target} IS NULL OR "
            f"NOT isfinite(CAST(g.{target} AS DOUBLE)) OR "
            f"NOT isfinite(CAST(e.{target} AS DOUBLE)) OR "
            f"ABS(CAST(g.{target} AS DOUBLE) - CAST(e.{target} AS DOUBLE)) > {tolerance}"
        )
        maximum_error = (
            f"MAX(ABS(CAST(g.{target} AS DOUBLE) - CAST(e.{target} AS DOUBLE))) "
            "FILTER (WHERE g.timestamp IS NOT NULL AND e.timestamp IS NOT NULL)"
        )

    row = connection.execute(
        f"""
        SELECT
            COUNT(*) FILTER (WHERE g.timestamp IS NULL OR e.timestamp IS NULL),
            COUNT(*) FILTER (
                WHERE g.timestamp IS NOT NULL AND e.timestamp IS NOT NULL
                  AND ({target_mismatch})
            ),
            {maximum_error}
        FROM generated_labels AS g
        FULL OUTER JOIN expected_labels AS e
          ON g.timestamp = e.timestamp AND g.{entity} = e.{entity}
        """
    ).fetchone()
    if row is None:
        raise ParityError("parity_query", "DuckDB returned no row-alignment evidence")
    key_mismatches = int(row[0])
    target_mismatches = int(row[1])
    maximum_absolute_error = None if row[2] is None else float(row[2])

    if generated_rows != expected_rows or key_mismatches or target_mismatches:
        raise ParityError("parity_mismatch", f"{split} labels differ from the reviewed artifact")
    return SplitParity(
        split=split,
        generated_rows=generated_rows,
        expected_rows=expected_rows,
        key_mismatches=key_mismatches,
        target_mismatches=target_mismatches,
        maximum_absolute_error=maximum_absolute_error,
    )


def verify_materialization_parity(
    task_id: TaskId,
    output_dir: Path,
    expected_labels: dict[str, Path],
) -> ParityReport:
    """Compare all generated labels with the pinned reviewed split artifacts."""
    try:
        result = MaterializationResult.model_validate_json(
            (output_dir / "manifest.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as error:
        raise ParityError(
            "parity_manifest", "materialization manifest is missing or invalid"
        ) from error
    if result.model_input.task.task_id != task_id:
        raise ParityError("parity_manifest", "materialization manifest has the wrong task ID")

    generated = {
        "train": output_dir / result.model_input.train_labels.path,
        "validation": output_dir / result.model_input.validation_labels.path,
        "test": output_dir / result.evaluator_truth.test_truth.path,
    }
    connection = duckdb.connect(database=":memory:")
    try:
        split_names: tuple[Literal["train", "validation", "test"], ...] = (
            "train",
            "validation",
            "test",
        )
        splits = [
            _verify_split(
                connection,
                split=split,
                generated_path=generated[split],
                expected_path=expected_labels[split],
                entity_column=result.model_input.task.entity_column,
                target_column=result.model_input.task.target_column,
                task_type=result.model_input.task.task_type,
            )
            for split in split_names
        ]
    except duckdb.Error as error:
        raise ParityError("parity_query", "DuckDB could not compare task artifacts") from error
    finally:
        connection.close()
    return ParityReport(
        status="passed",
        task_id=task_id,
        package_sha256=result.package_sha256,
        splits=splits,
    )
