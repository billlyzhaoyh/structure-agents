"""Network-isolated RT-J data preparation and inference runtime."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

import duckdb

DB_NAME = "rel-hm"
EMBEDDING_MODEL = "all-MiniLM-L12-v2"
REVIEWED_TASKS: dict[str, tuple[str, str, str]] = {
    "rel-hm/user-churn": ("customer", "customer_id", "churn"),
    "rel-hm/item-sales": ("article", "article_id", "sales"),
}


class WorkerInputError(RuntimeError):
    """The sealed worker input did not match the reviewed protocol."""


def _columns(path: Path) -> list[str]:
    connection = duckdb.connect(":memory:")
    try:
        return [
            str(row[0])
            for row in connection.execute(
                "DESCRIBE SELECT * FROM read_parquet(?)", [str(path)]
            ).fetchall()
        ]
    finally:
        connection.close()


def _task_manifest(entity_table: str, entity_column: str, target: str, task_type: str) -> str:
    return (
        f"entity_table: {entity_table}\n"
        f"entity_col: {entity_column}\n"
        f"target_col: {target}\n"
        f"task_type: {task_type}\n"
        "time_col: timestamp\n"
    )


def prepare_worker_dataset(
    input_root: Path,
    work_root: Path,
    *,
    task_id: str,
    task_type: str,
) -> Path:
    """Create RT layout and add a zero target only to the worker-private test copy."""
    if task_id not in REVIEWED_TASKS:
        raise WorkerInputError("only the two reviewed H&M defaults are permitted")
    expected_type = {
        "rel-hm/user-churn": "binary_classification",
        "rel-hm/item-sales": "regression",
    }[task_id]
    if task_type != expected_type:
        raise WorkerInputError("task type does not match the reviewed default")

    entity_table, entity_column, target = REVIEWED_TASKS[task_id]
    task_name = task_id.rsplit("/", maxsplit=1)[1]
    source_database = input_root / DB_NAME / "db"
    source_task = input_root / DB_NAME / "tasks" / task_name
    dataset = work_root / DB_NAME
    database = dataset / "db"
    task = dataset / "tasks" / task_name
    database.mkdir(parents=True, exist_ok=False)
    task.mkdir(parents=True, exist_ok=False)

    for table in ("article", "customer", "transactions"):
        source = source_database / f"{table}.parquet"
        if not source.is_file():
            raise WorkerInputError("a reviewed database file is missing")
        shutil.copyfile(source, database / source.name)

    labelled_columns = ["timestamp", entity_column, target]
    for source_name, output_name in (
        ("train.parquet", "train.parquet"),
        ("val.parquet", "val.parquet"),
    ):
        source = source_task / source_name
        if _columns(source) != labelled_columns:
            raise WorkerInputError("a labelled split has an invalid schema")
        shutil.copyfile(source, task / output_name)

    masked_test = source_task / "test.parquet"
    if _columns(masked_test) != ["timestamp", entity_column]:
        raise WorkerInputError("masked test rows have an invalid schema or contain a target")
    dummy_expression = (
        "CAST(0 AS INTEGER)" if task_type == "binary_classification" else "CAST(0 AS DOUBLE)"
    )
    connection = duckdb.connect(":memory:")
    try:
        connection.from_parquet(str(masked_test)).create_view("masked_test")
        connection.execute(
            f'COPY (SELECT timestamp, "{entity_column}", {dummy_expression} AS "{target}" '
            "FROM masked_test ORDER BY 1, 2) TO ? (FORMAT PARQUET, COMPRESSION ZSTD)",
            [str(task / "test.parquet")],
        )
    finally:
        connection.close()

    (dataset / "manifest.yaml").write_text(
        """name: rel-hm
tables:
  article:
    pkey: article_id
  customer:
    pkey: customer_id
  transactions:
    time_col: t_dat
    fkeys:
      article_id: article
      customer_id: customer
""",
        encoding="utf-8",
    )
    (task / "manifest.yaml").write_text(
        _task_manifest(entity_table, entity_column, target, task_type), encoding="utf-8"
    )
    return dataset


def _prediction_file_reference(path: Path, entity_column: str, row_count: int) -> dict[str, Any]:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "path": "predictions.parquet",
        "sha256": digest.hexdigest(),
        "row_count": row_count,
        "byte_count": path.stat().st_size,
        "columns": ["timestamp", entity_column, "prediction"],
    }


def run_task_inference(
    input_root: str,
    output_root: str,
    assets_root: str,
    request: dict[str, Any],
    max_items: int | None,
) -> dict[str, Any]:
    """Run one reviewed RT-J task using only staged local assets."""
    started = time.monotonic()
    task_payload = request["model_input"]["task"]
    task_id = str(task_payload["task_id"])
    task_type = str(task_payload["task_type"])
    entity_column = str(task_payload["entity_column"])
    task_name = task_id.rsplit("/", maxsplit=1)[1]
    expected_entity = REVIEWED_TASKS.get(task_id, ("", "", ""))[1]
    if entity_column != expected_entity:
        raise WorkerInputError("entity column does not match the reviewed task")

    work_root = Path(output_root) / "work" / task_name
    dataset = prepare_worker_dataset(
        Path(input_root), work_root / "dataset", task_id=task_id, task_type=task_type
    )
    pre_root = work_root / "pre"

    from rt import _rustler  # type: ignore[import-not-found]
    from rt.embed import main as embed_text  # type: ignore[import-not-found]

    _rustler.preprocess(str(dataset), str(pre_root), source="private-hackathon")
    embed_text(DB_NAME, str(pre_root), "cuda", 256, EMBEDDING_MODEL)

    import numpy as np  # type: ignore[import-not-found]
    import torch  # type: ignore[import-not-found]
    from rt.checkpoints import load_rt_model  # type: ignore[import-not-found]
    from rt.eval_utils import build_evaluator  # type: ignore[import-not-found]
    from rt.tasks import tasks_from_preprocessed  # type: ignore[import-not-found]

    variant = "classification" if task_type == "binary_classification" else "regression"
    checkpoint_root = str(Path(assets_root) / "checkpoint")
    model, config = load_rt_model(
        checkpoint_root,
        device="cuda",
        compile=False,
        subfolder=variant,
    )
    wanted = "clf" if task_type == "binary_classification" else "reg"
    if config.get("task_type") != wanted:
        raise WorkerInputError("checkpoint head does not match the task")
    model = model.to(torch.bfloat16)
    model.eval()
    tasks = [
        task
        for task in tasks_from_preprocessed(
            str(pre_root), splits=("test",), task_types=(wanted,), dbs=[DB_NAME]
        )
        if task.table_name == task_name
    ]
    if len(tasks) != 1:
        raise WorkerInputError("preprocessing did not produce exactly one reviewed task")
    fixed = request["config"]
    evaluator = build_evaluator(
        tasks,
        str(pre_root),
        embedding_model=EMBEDDING_MODEL,
        d_text=384,
        device="cuda",
        ctx_size=int(fixed["context_length"]),
        local_ctx_size=int(fixed["local_context_length"]),
        bfs_width=int(fixed["bfs_width"]),
        num_walks=int(fixed["num_walks"]),
        walk_length=int(fixed["walk_length"]),
        tokens_per_gpu=int(fixed["context_length"]) * 16,
        items_per_task=max_items,
        num_workers=0,
        context_seed=int(fixed["context_seed"]),
        prefer_latest=True,
        shuffle_seed=int(fixed["shuffle_seed"]),
        mmap_populate=False,
    )
    outputs = list(
        evaluator.evaluate_raw([(model, "")], [int(fixed["context_length"])], with_node_idxs=True)
    )
    if len(outputs) != 1:
        raise WorkerInputError("RT-J returned an unexpected task batch")
    _, _, _, predictions_by_prefix, _, node_idxs = outputs[0]
    raw = np.asarray(predictions_by_prefix[""], dtype=float)
    if task_type == "binary_classification":
        predictions = 1.0 / (1.0 + np.exp(-raw))
    else:
        target = REVIEWED_TASKS[task_id][2]
        connection = duckdb.connect(":memory:")
        try:
            scale_row = connection.execute(
                f'SELECT AVG("{target}"), STDDEV_SAMP("{target}") FROM read_parquet(?)',
                [str(dataset / "tasks" / task_name / "train.parquet")],
            ).fetchone()
        finally:
            connection.close()
        if scale_row is None:
            raise WorkerInputError("training target scale is unavailable")
        mean, sample_std = scale_row
        scale = 0.0 if sample_std is None else float(sample_std)
        predictions = raw * scale + float(mean)
    if not np.isfinite(predictions).all():
        raise WorkerInputError("RT-J returned non-finite predictions")

    table_info = json.loads((pre_root / DB_NAME / "table_info.json").read_text(encoding="utf-8"))
    offset = int(table_info[f"{task_name}:Test"]["node_idx_offset"])
    row_indexes = np.asarray(node_idxs, dtype=np.int64) - offset
    if len(row_indexes) != len(predictions) or len(set(row_indexes.tolist())) != len(row_indexes):
        raise WorkerInputError("RT-J returned invalid prediction row indexes")
    if max_items is None and len(row_indexes) != int(
        request["model_input"]["test_rows"]["row_count"]
    ):
        raise WorkerInputError("full inference did not cover the official test split")

    output_dir = Path(output_root) / "outputs" / task_name
    output_dir.mkdir(parents=True, exist_ok=False)
    prediction_path = output_dir / "predictions.parquet"
    connection = duckdb.connect(":memory:")
    try:
        connection.execute("CREATE TEMP TABLE predicted(row_index BIGINT, prediction DOUBLE)")
        connection.executemany(
            "INSERT INTO predicted VALUES (?, ?)",
            [
                (int(index), float(value))
                for index, value in zip(row_indexes, predictions, strict=True)
            ],
        )
        connection.execute(
            f"COPY (WITH test AS (SELECT row_number() OVER () - 1 AS row_index, * "
            f'FROM read_parquet(?)) SELECT test.timestamp, test."{entity_column}", '
            "predicted.prediction FROM test JOIN predicted USING(row_index) ORDER BY 1, 2) "
            "TO ? (FORMAT PARQUET, COMPRESSION ZSTD)",
            [str(dataset / "tasks" / task_name / "test.parquet"), str(prediction_path)],
        )
    finally:
        connection.close()
    duration_seconds = time.monotonic() - started
    return {
        "task_id": task_id,
        "duration_seconds": duration_seconds,
        "prediction_file": _prediction_file_reference(
            prediction_path, entity_column, len(predictions)
        ),
        "remote_prediction_path": f"/run/outputs/{task_name}/predictions.parquet",
    }
