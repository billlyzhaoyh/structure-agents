"""Local DuckDB implementation of the guarded task materialization boundary."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import duckdb

from structagent_api.catalog import RELBENCH_V1_REVISION
from structagent_api.contracts import (
    EvaluatorTruthPackage,
    MaterializationResult,
    MaterializedFileReference,
    ModelTaskPackage,
    TaskSqlArtifact,
)
from structagent_api.contracts.models import (
    DatasetTableReference,
    TaskValidationCheck,
    TaskValidationReport,
)
from structagent_api.materialization.task_sql import TaskId, build_default_task_sql

MAX_MATERIALIZED_ROWS = 25_000_000


class MaterializationError(RuntimeError):
    """Sanitized validation or execution failure."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class HMDatasetFiles:
    """Three checksum-addressable Parquet tables exposed to task SQL."""

    root: Path
    article: Path
    customer: Path
    transactions: Path
    revision: str = RELBENCH_V1_REVISION

    @classmethod
    def from_directory(
        cls,
        root: Path,
        *,
        revision: str = RELBENCH_V1_REVISION,
    ) -> HMDatasetFiles:
        return cls(
            root=root,
            article=root / "article.parquet",
            customer=root / "customer.parquet",
            transactions=root / "transactions.parquet",
            revision=revision,
        )

    def validated_paths(self) -> dict[str, Path]:
        root = self.root.resolve(strict=True)
        paths = {
            "article": self.article.resolve(strict=True),
            "customer": self.customer.resolve(strict=True),
            "transactions": self.transactions.resolve(strict=True),
        }
        for path in paths.values():
            if not path.is_relative_to(root) or path.suffix != ".parquet":
                raise MaterializationError(
                    "dataset_path", "dataset files must be Parquet files below the dataset root"
                )
        return paths


@dataclass(frozen=True)
class TemporalCutoffs:
    validation: datetime
    test: datetime


REL_HM_CUTOFFS = TemporalCutoffs(
    validation=datetime(2020, 9, 7),
    test=datetime(2020, 9, 14),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sql_literal(value: Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _required_row(
    cursor: duckdb.DuckDBPyConnection,
    *,
    code: str = "duckdb_result",
) -> tuple[Any, ...]:
    row = cursor.fetchone()
    if row is None:
        raise MaterializationError(code, "DuckDB returned no aggregate result")
    return row


def _timestamps(
    minimum: datetime,
    cutoffs: TemporalCutoffs,
    horizon_days: int,
) -> dict[Literal["train", "validation", "test"], list[datetime]]:
    horizon = timedelta(days=horizon_days)
    current = cutoffs.validation - horizon
    train: list[datetime] = []
    while current >= minimum:
        train.append(current)
        current -= horizon
    if len(train) < 3:
        raise MaterializationError(
            "training_windows", "at least three complete training timestamps are required"
        )
    train.reverse()
    return {"train": train, "validation": [cutoffs.validation], "test": [cutoffs.test]}


def _file_reference(
    path: Path,
    *,
    row_count: int,
    columns: list[str],
) -> MaterializedFileReference:
    return MaterializedFileReference(
        path=path.name,
        sha256=_sha256(path),
        row_count=row_count,
        byte_count=path.stat().st_size,
        columns=columns,
    )


def _dataset_references(
    connection: duckdb.DuckDBPyConnection,
    paths: dict[str, Path],
) -> list[DatasetTableReference]:
    references: list[DatasetTableReference] = []
    for table in ("article", "customer", "transactions"):
        row_count = _required_row(connection.execute(f"SELECT COUNT(*) FROM {table}"))[0]
        references.append(
            DatasetTableReference(
                table=table,
                path=paths[table].name,
                sha256=_sha256(paths[table]),
                row_count=int(row_count),
                byte_count=paths[table].stat().st_size,
                columns=[row[0] for row in connection.execute(f"DESCRIBE {table}").fetchall()],
            )
        )
    return references


def _validate_labels(
    connection: duckdb.DuckDBPyConnection,
    *,
    split: str,
    entity_column: str,
    target_column: str,
    task_type: str,
) -> tuple[int, list[TaskValidationCheck]]:
    entity = _quote_identifier(entity_column)
    target = _quote_identifier(target_column)
    columns = [row[0] for row in connection.execute("DESCRIBE task_labels").fetchall()]
    expected_columns = ["timestamp", entity_column, target_column]
    if columns != expected_columns:
        raise MaterializationError(
            "output_schema", "materialized labels do not match the declared output schema"
        )

    row = _required_row(
        connection.execute(
            f"""
            SELECT
                COUNT(*) AS row_count,
                COUNT(*) FILTER (WHERE timestamp IS NULL OR {entity} IS NULL) AS key_nulls,
                COUNT(*) FILTER (WHERE {target} IS NULL) AS target_nulls,
                COUNT(*) FILTER (
                    WHERE NOT isfinite(TRY_CAST({target} AS DOUBLE))
                ) AS non_finite,
                COUNT(DISTINCT {target}) AS distinct_targets
            FROM task_labels
            """
        )
    )
    row_count, key_nulls, target_nulls, non_finite, distinct_targets = (int(value) for value in row)
    duplicate_count = int(
        _required_row(
            connection.execute(
                f"""
                SELECT COUNT(*)
                FROM (
                    SELECT timestamp, {entity}
                    FROM task_labels
                    GROUP BY timestamp, {entity}
                    HAVING COUNT(*) > 1
                )
                """
            )
        )[0]
    )

    if row_count == 0:
        raise MaterializationError("non_empty", f"{split} labels are empty")
    if row_count > MAX_MATERIALIZED_ROWS:
        raise MaterializationError("bounded_rows", f"{split} labels exceed the row limit")
    if key_nulls or target_nulls:
        raise MaterializationError("null_values", f"{split} labels contain null required values")
    if duplicate_count:
        raise MaterializationError("unique_keys", f"{split} labels contain duplicate keys")
    if non_finite:
        raise MaterializationError("finite_targets", f"{split} labels contain non-finite targets")

    checks = [
        TaskValidationCheck(
            code=f"{split}_non_empty",
            status="passed",
            detail=f"{split} contains {row_count} rows.",
        ),
        TaskValidationCheck(
            code=f"{split}_unique_keys",
            status="passed",
            detail=f"{split} has one row per timestamp and entity.",
        ),
        TaskValidationCheck(
            code=f"{split}_finite_targets",
            status="passed",
            detail=f"{split} required values are non-null and finite.",
        ),
    ]
    if task_type == "binary_classification":
        invalid_binary = int(
            _required_row(
                connection.execute(f"SELECT COUNT(*) FROM task_labels WHERE {target} NOT IN (0, 1)")
            )[0]
        )
        if invalid_binary or distinct_targets != 2:
            raise MaterializationError(
                "binary_targets", f"{split} labels must contain both binary classes"
            )
        prevalence = float(
            _required_row(
                connection.execute(f"SELECT AVG(CAST({target} AS DOUBLE)) FROM task_labels")
            )[0]
        )
        if not math.isfinite(prevalence):
            raise MaterializationError("binary_targets", f"{split} prevalence is invalid")
        checks.append(
            TaskValidationCheck(
                code=f"{split}_class_balance",
                status="passed",
                detail=f"{split} contains both classes; prevalence={prevalence:.6f}.",
            )
        )
    return row_count, checks


def _write_split(
    connection: duckdb.DuckDBPyConnection,
    *,
    split: Literal["train", "validation", "test"],
    timestamps: list[datetime],
    sql: str,
    output_dir: Path,
    entity_column: str,
    target_column: str,
    task_type: str,
) -> tuple[MaterializedFileReference, MaterializedFileReference | None, list[TaskValidationCheck]]:
    connection.execute("DROP VIEW IF EXISTS task_labels")
    connection.execute("DROP TABLE IF EXISTS timestamps")
    connection.execute("CREATE TEMP TABLE timestamps(timestamp TIMESTAMP NOT NULL)")
    connection.executemany("INSERT INTO timestamps VALUES (?)", [(value,) for value in timestamps])
    connection.execute(f"CREATE TEMP VIEW task_labels AS {sql}")

    row_count, checks = _validate_labels(
        connection,
        split=split,
        entity_column=entity_column,
        target_column=target_column,
        task_type=task_type,
    )
    entity = _quote_identifier(entity_column)
    target = _quote_identifier(target_column)
    labelled_columns = ["timestamp", entity_column, target_column]
    labelled_path = output_dir / ("test-truth.parquet" if split == "test" else f"{split}.parquet")
    ordered_labels = f"SELECT timestamp, {entity}, {target} FROM task_labels ORDER BY 1, 2"
    connection.execute(
        f"COPY ({ordered_labels}) TO ? (FORMAT PARQUET, COMPRESSION ZSTD)",
        [str(labelled_path)],
    )
    labelled_reference = _file_reference(
        labelled_path,
        row_count=row_count,
        columns=labelled_columns,
    )

    if split != "test":
        return labelled_reference, None, checks

    test_path = output_dir / "test.parquet"
    connection.execute(
        f"COPY (SELECT timestamp, {entity} FROM task_labels ORDER BY 1, 2) "
        "TO ? (FORMAT PARQUET, COMPRESSION ZSTD)",
        [str(test_path)],
    )
    test_reference = _file_reference(
        test_path,
        row_count=row_count,
        columns=["timestamp", entity_column],
    )
    return test_reference, labelled_reference, checks


def materialize_task(
    task: TaskSqlArtifact,
    dataset: HMDatasetFiles,
    output_dir: Path,
    *,
    cutoffs: TemporalCutoffs = REL_HM_CUTOFFS,
) -> MaterializationResult:
    """Materialize one default task into model-visible and sealed artifacts."""
    paths = dataset.validated_paths()
    output_dir.mkdir(parents=True, exist_ok=True)
    expected_outputs = {
        output_dir / "manifest.json",
        output_dir / "test-truth.parquet",
        output_dir / "test.parquet",
        output_dir / "train.parquet",
        output_dir / "validation.parquet",
    }
    if any(path.exists() for path in expected_outputs):
        raise MaterializationError("output_exists", "materialization output already exists")

    connection = duckdb.connect(database=":memory:")
    try:
        for table, path in paths.items():
            connection.execute(
                f"CREATE VIEW {table} AS SELECT * FROM read_parquet({_sql_literal(path)})"
            )
        connection.execute(
            "SET allowed_directories = ?",
            [[str(dataset.root.resolve()), str(output_dir.resolve())]],
        )
        connection.execute("SET enable_external_access = false")
        connection.execute("SET lock_configuration = true")

        transaction_bounds = _required_row(
            connection.execute("SELECT MIN(t_dat), MAX(t_dat) FROM transactions"),
            code="time_bounds",
        )
        minimum, maximum = transaction_bounds
        if not isinstance(minimum, datetime) or not isinstance(maximum, datetime):
            raise MaterializationError("time_bounds", "transactions require timestamp bounds")
        required_maximum = cutoffs.test + timedelta(days=task.horizon_days)
        if maximum < required_maximum:
            raise MaterializationError(
                "outcome_windows", "the test outcome window is not fully observable"
            )

        schedule = _timestamps(minimum, cutoffs, task.horizon_days)
        runtime_checks = [
            TaskValidationCheck(
                code="outcome_windows",
                status="passed",
                detail="Every prediction timestamp has a complete future outcome window.",
            )
        ]
        train, _, train_checks = _write_split(
            connection,
            split="train",
            timestamps=schedule["train"],
            sql=task.normalized_sql,
            output_dir=output_dir,
            entity_column=task.entity_column,
            target_column=task.target_column,
            task_type=task.task_type,
        )
        validation, _, validation_checks = _write_split(
            connection,
            split="validation",
            timestamps=schedule["validation"],
            sql=task.normalized_sql,
            output_dir=output_dir,
            entity_column=task.entity_column,
            target_column=task.target_column,
            task_type=task.task_type,
        )
        test_rows, test_truth, test_checks = _write_split(
            connection,
            split="test",
            timestamps=schedule["test"],
            sql=task.normalized_sql,
            output_dir=output_dir,
            entity_column=task.entity_column,
            target_column=task.target_column,
            task_type=task.task_type,
        )
        if test_truth is None:  # pragma: no cover - guarded by the split literal
            raise MaterializationError("sealed_truth", "test truth was not materialized")

        report = TaskValidationReport(
            status="passed",
            checks=[
                *task.validation_report.checks,
                *runtime_checks,
                *train_checks,
                *validation_checks,
                *test_checks,
            ],
        )
        task = task.model_copy(update={"validation_report": report})
        model_input = ModelTaskPackage(
            contract_version="v1",
            dataset_id="rel-hm",
            dataset_revision=dataset.revision,
            task=task,
            database_files=_dataset_references(connection, paths),
            train_labels=train,
            validation_labels=validation,
            test_rows=test_rows,
        )
        evaluator_truth = EvaluatorTruthPackage(
            contract_version="v1",
            dataset_id="rel-hm",
            task_id=task.task_id,
            query_sha256=task.query_sha256,
            test_truth=test_truth,
        )
        model_input_payload = model_input.model_dump(mode="json")
        model_input_sha256 = hashlib.sha256(
            json.dumps(model_input_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        package_payload = {
            "evaluator_truth": evaluator_truth.model_dump(mode="json"),
            "model_input": model_input_payload,
            "validation_report": report.model_dump(mode="json"),
        }
        package_sha256 = hashlib.sha256(
            json.dumps(package_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        result = MaterializationResult(
            contract_version="v1",
            package_sha256=package_sha256,
            model_input_sha256=model_input_sha256,
            model_input=model_input,
            evaluator_truth=evaluator_truth,
            validation_report=report,
        )
        (output_dir / "manifest.json").write_text(
            result.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
        return result
    except duckdb.Error as error:
        raise MaterializationError(
            "duckdb_execution", "DuckDB rejected task materialization"
        ) from error
    finally:
        connection.close()


def materialize_default_task(
    task_id: TaskId,
    dataset: HMDatasetFiles,
    output_dir: Path,
    *,
    cutoffs: TemporalCutoffs = REL_HM_CUTOFFS,
) -> MaterializationResult:
    """Build and materialize one reviewed default task."""
    return materialize_task(
        build_default_task_sql(task_id),
        dataset,
        output_dir,
        cutoffs=cutoffs,
    )
