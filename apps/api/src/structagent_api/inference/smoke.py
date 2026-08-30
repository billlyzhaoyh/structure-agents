"""Private bounded-cohort construction for live RT-J validation."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import duckdb

from structagent_api.contracts import MaterializationResult, MaterializedFileReference
from structagent_api.contracts.models import TaskValidationCheck


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _reference(
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


def create_user_churn_smoke_materialization(
    source_root: Path,
    output_root: Path,
    *,
    sample_size: int,
) -> MaterializationResult:
    """Derive a balanced, deterministic real-data cohort without exposing truth to Modal."""
    if sample_size < 2 or sample_size % 2:
        raise ValueError("sample size must be an even integer of at least two")
    source = MaterializationResult.model_validate_json(
        (source_root / "manifest.json").read_text(encoding="utf-8")
    )
    task = source.model_input.task
    if task.task_id != "rel-hm/user-churn" or task.task_type != "binary_classification":
        raise ValueError("the bounded live smoke currently supports only reviewed user churn")
    output_root.mkdir(parents=True, exist_ok=False)

    train_path = output_root / "train.parquet"
    validation_path = output_root / "validation.parquet"
    shutil.copyfile(source_root / source.model_input.train_labels.path, train_path)
    shutil.copyfile(source_root / source.model_input.validation_labels.path, validation_path)
    truth_path = output_root / "test-truth.parquet"
    test_path = output_root / "test.parquet"
    per_class = sample_size // 2
    connection = duckdb.connect(":memory:")
    try:
        connection.from_parquet(
            str(source_root / source.evaluator_truth.test_truth.path)
        ).create_view("truth")
        connection.execute(
            "CREATE TEMP TABLE sampled AS "
            "(SELECT * FROM truth WHERE churn = 0 "
            "ORDER BY hash(customer_id, timestamp) LIMIT ?) "
            "UNION ALL "
            "(SELECT * FROM truth WHERE churn = 1 "
            "ORDER BY hash(customer_id, timestamp) LIMIT ?)",
            [per_class, per_class],
        )
        connection.execute(
            "COPY (SELECT timestamp, customer_id, churn FROM sampled ORDER BY 1, 2) "
            "TO ? (FORMAT PARQUET, COMPRESSION ZSTD)",
            [str(truth_path)],
        )
        observed = connection.execute(
            "SELECT COUNT(*), COUNT(*) FILTER (WHERE churn = 1) FROM read_parquet(?)",
            [str(truth_path)],
        ).fetchone()
        if observed != (sample_size, per_class):
            raise ValueError("the real H&M split cannot provide the requested balanced cohort")
        connection.execute(
            "COPY (SELECT timestamp, customer_id FROM sampled ORDER BY 1, 2) "
            "TO ? (FORMAT PARQUET, COMPRESSION ZSTD)",
            [str(test_path)],
        )
    finally:
        connection.close()

    labelled_columns = ["timestamp", task.entity_column, task.target_column]
    train = _reference(
        train_path,
        row_count=source.model_input.train_labels.row_count,
        columns=labelled_columns,
    )
    validation = _reference(
        validation_path,
        row_count=source.model_input.validation_labels.row_count,
        columns=labelled_columns,
    )
    test = _reference(
        test_path,
        row_count=sample_size,
        columns=["timestamp", task.entity_column],
    )
    truth = _reference(
        truth_path,
        row_count=sample_size,
        columns=labelled_columns,
    )
    checks = [
        check.model_copy(update={"detail": f"test contains {sample_size} sampled real rows."})
        if check.code == "test_non_empty"
        else check
        for check in source.validation_report.checks
    ]
    checks.append(
        TaskValidationCheck(
            code="private_smoke_cohort",
            status="passed",
            detail=(
                "A deterministic balanced real-data cohort was sealed for private smoke testing."
            ),
        )
    )
    report = source.validation_report.model_copy(update={"checks": checks})
    sampled_task = task.model_copy(update={"validation_report": report})
    model_input = source.model_input.model_copy(
        update={
            "task": sampled_task,
            "train_labels": train,
            "validation_labels": validation,
            "test_rows": test,
        }
    )
    evaluator_truth = source.evaluator_truth.model_copy(update={"test_truth": truth})
    model_payload = model_input.model_dump(mode="json")
    model_sha = hashlib.sha256(
        json.dumps(model_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    package_payload = {
        "evaluator_truth": evaluator_truth.model_dump(mode="json"),
        "model_input": model_payload,
        "validation_report": report.model_dump(mode="json"),
    }
    package_sha = hashlib.sha256(
        json.dumps(package_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    result = MaterializationResult(
        contract_version="v1",
        package_sha256=package_sha,
        model_input_sha256=model_sha,
        model_input=model_input,
        evaluator_truth=evaluator_truth,
        validation_report=report,
    )
    (output_root / "manifest.json").write_text(
        result.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    return result
