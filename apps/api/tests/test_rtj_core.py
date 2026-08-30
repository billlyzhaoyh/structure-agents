from __future__ import annotations

import importlib
import os
import shutil
import sys
from pathlib import Path

import duckdb
import pytest
from structagent_api.contracts import (
    CompletedPredictionPackage,
    MaterializationResult,
    MaterializedFileReference,
    RTJInferenceConfig,
    RTJRuntimeProvenance,
)
from structagent_api.inference import (
    InferenceEvaluationError,
    build_inference_request,
    build_upload_inventory,
    checkpoint_for_task,
    evaluate_predictions,
)
from structagent_api.inference.artifacts import sha256_file
from structagent_api.inference.payload import ModelUpload
from structagent_api.materialization import (
    SYNTHETIC_CUTOFFS,
    create_synthetic_hm,
    materialize_default_task,
)
from structagent_api.materialization.task_sql import TaskId

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
prepare_worker_dataset = importlib.import_module("workers.rtj.runtime").prepare_worker_dataset


def _materialize(tmp_path: Path, task_id: TaskId) -> tuple[Path, Path, MaterializationResult]:
    dataset = create_synthetic_hm(tmp_path / "dataset")
    task_root = tmp_path / "task"
    result = materialize_default_task(task_id, dataset, task_root, cutoffs=SYNTHETIC_CUTOFFS)
    return dataset.root, task_root, result


def _perfect_prediction(
    task_root: Path, result: MaterializationResult
) -> CompletedPredictionPackage:
    task = result.model_input.task
    path = task_root / "predictions.parquet"
    connection = duckdb.connect(":memory:")
    try:
        connection.from_parquet(str(task_root / "test-truth.parquet")).create_view("truth")
        connection.execute(
            f'COPY (SELECT timestamp, "{task.entity_column}", '
            f'CAST("{task.target_column}" AS DOUBLE) AS prediction FROM truth '
            "ORDER BY 1, 2) TO ? (FORMAT PARQUET, COMPRESSION ZSTD)",
            [str(path)],
        )
    finally:
        connection.close()
    return CompletedPredictionPackage(
        contract_version="v1",
        status="synthetic",
        dataset_id="rel-hm",
        task_id=task.task_id,
        task_type=task.task_type,
        entity_column=task.entity_column,
        dataset_revision=result.model_input.dataset_revision,
        materialization_package_sha256=result.package_sha256,
        model_input_sha256=result.model_input_sha256,
        query_sha256=task.query_sha256,
        prediction_file=MaterializedFileReference(
            path="predictions.parquet",
            sha256=sha256_file(path),
            row_count=result.model_input.test_rows.row_count,
            byte_count=path.stat().st_size,
            columns=["timestamp", task.entity_column, "prediction"],
        ),
        checkpoint=checkpoint_for_task(task.task_type),
        config=RTJInferenceConfig(),
        runtime=RTJRuntimeProvenance(
            provider="fake",
            gpu="none",
            duration_seconds=0,
            source_revision="synthetic",
            checkpoint_revision="synthetic",
        ),
    )


@pytest.mark.parametrize("task_id", ["rel-hm/user-churn", "rel-hm/item-sales"])
def test_adapter_and_inventory_expose_only_verified_model_inputs(
    tmp_path: Path, task_id: TaskId, monkeypatch: pytest.MonkeyPatch
) -> None:
    dataset_root, task_root, result = _materialize(tmp_path, task_id)
    sentinel = "provider-token-must-not-cross-boundary"
    monkeypatch.setenv("MODAL_TOKEN_SECRET", sentinel)
    monkeypatch.setenv("OPENAI_API_KEY", sentinel)
    monkeypatch.setenv("DAYTONA_API_KEY", sentinel)

    request = build_inference_request(result)
    inventory = build_upload_inventory(result, dataset_root=dataset_root, task_root=task_root)

    assert request.model_input_sha256 == result.model_input_sha256
    assert len(inventory) == 6
    assert all(upload.source.is_file() for upload in inventory)
    assert len({upload.remote_path for upload in inventory}) == 6
    serialized = request.model_dump_json() + "".join(str(item) for item in inventory)
    assert sentinel not in serialized
    assert "test-truth" not in serialized
    assert "manifest.json" not in serialized
    assert os.environ["MODAL_TOKEN_SECRET"] == sentinel


def _stage_worker_input(root: Path, inventory: tuple[ModelUpload, ...]) -> None:
    for upload in inventory:
        destination = root / upload.remote_path.relative_to("/run/input")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(upload.source, destination)


@pytest.mark.parametrize(
    ("task_id", "target", "expected_dummy"),
    [
        ("rel-hm/user-churn", "churn", 0),
        ("rel-hm/item-sales", "sales", 0.0),
    ],
)
def test_worker_adds_placeholder_only_to_private_masked_test_copy(
    tmp_path: Path,
    task_id: TaskId,
    target: str,
    expected_dummy: float,
) -> None:
    dataset_root, task_root, result = _materialize(tmp_path, task_id)
    input_root = tmp_path / "input"
    inventory = build_upload_inventory(result, dataset_root=dataset_root, task_root=task_root)
    _stage_worker_input(input_root, inventory)

    dataset = prepare_worker_dataset(
        input_root,
        tmp_path / "worker",
        task_id=task_id,
        task_type=result.model_input.task.task_type,
    )
    task_name = task_id.rsplit("/", maxsplit=1)[1]
    private_test = dataset / "tasks" / task_name / "test.parquet"
    source_test = input_root / "rel-hm" / "tasks" / task_name / "test.parquet"
    connection = duckdb.connect(":memory:")
    try:
        assert [
            row[0]
            for row in connection.execute(
                "DESCRIBE SELECT * FROM read_parquet(?)", [str(source_test)]
            ).fetchall()
        ] == ["timestamp", result.model_input.task.entity_column]
        columns = [
            row[0]
            for row in connection.execute(
                "DESCRIBE SELECT * FROM read_parquet(?)", [str(private_test)]
            ).fetchall()
        ]
        observed = connection.execute(
            f'SELECT DISTINCT "{target}" FROM read_parquet(?)', [str(private_test)]
        ).fetchall()
    finally:
        connection.close()
    assert columns == ["timestamp", result.model_input.task.entity_column, target]
    assert observed == [(expected_dummy,)]
    assert not list(input_root.rglob("*truth*"))
    assert not list(dataset.rglob("*truth*"))


@pytest.mark.parametrize("task_id", ["rel-hm/user-churn", "rel-hm/item-sales"])
def test_trusted_evaluator_reports_perfect_metrics_with_full_provenance(
    tmp_path: Path, task_id: TaskId
) -> None:
    _, task_root, result = _materialize(tmp_path, task_id)
    prediction = _perfect_prediction(task_root, result)

    evaluation = evaluate_predictions(prediction, task_root, result, task_root)

    assert evaluation.coverage == 1
    assert evaluation.model_input_sha256 == result.model_input_sha256
    assert evaluation.query_sha256 == result.model_input.task.query_sha256
    assert evaluation.runtime.provider == "fake"
    assert evaluation.checkpoint == prediction.checkpoint
    assert any(
        check.name == "relbench_evaluator_revision"
        and "9a223758cea1fd486a8d20f9e2f7ac4f42c88d0f" in check.detail
        for check in evaluation.integrity_checks
    )
    if evaluation.task_type == "binary_classification":
        assert evaluation.metrics.auroc == 1
        assert evaluation.metrics.accuracy == 1
    else:
        assert evaluation.metrics.mae == 0
        assert evaluation.metrics.nmae == 0


def test_trusted_evaluator_rejects_incomplete_predictions(tmp_path: Path) -> None:
    _, task_root, result = _materialize(tmp_path, "rel-hm/user-churn")
    prediction = _perfect_prediction(task_root, result)
    path = task_root / "predictions.parquet"
    connection = duckdb.connect(":memory:")
    try:
        connection.from_parquet(str(path)).create_view("predictions")
        connection.execute(
            "COPY (SELECT * FROM predictions LIMIT 1) TO ? (FORMAT PARQUET)",
            [str(task_root / "incomplete.parquet")],
        )
    finally:
        connection.close()
    incomplete = task_root / "incomplete.parquet"
    reference = prediction.prediction_file.model_copy(
        update={
            "sha256": sha256_file(incomplete),
            "byte_count": incomplete.stat().st_size,
            "row_count": 1,
        }
    )
    shutil.copyfile(incomplete, path)
    rejected = prediction.model_copy(update={"prediction_file": reference})

    with pytest.raises(InferenceEvaluationError) as raised:
        evaluate_predictions(rejected, task_root, result, task_root)

    assert raised.value.code == "prediction_coverage"
