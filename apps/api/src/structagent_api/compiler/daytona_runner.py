"""Fixed custom-task validation entrypoint uploaded to a Daytona sandbox."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb
from pydantic import BaseModel, ConfigDict

from structagent_api.contracts import CustomTaskSqlArtifact
from structagent_api.materialization.materializer import HMDatasetFiles, materialize_task
from structagent_api.materialization.task_sql import validate_task_sql


class ValidationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_revision: str
    task: CustomTaskSqlArtifact


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path)
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()

    request = ValidationRequest.model_validate_json(args.request.read_text(encoding="utf-8"))
    validated = validate_task_sql(
        request.task.sql,
        entity_column=request.task.entity_column,
        target_column=request.task.target_column,
        horizon_days=request.task.horizon_days,
    )
    if (
        validated.normalized != request.task.normalized_sql
        or validated.sha256 != request.task.query_sha256
    ):
        raise RuntimeError("task SQL digest does not match sandbox validation")
    dataset = HMDatasetFiles.from_directory(
        args.input_dir,
        revision=request.dataset_revision,
    )
    result = materialize_task(request.task, dataset, args.output_dir)
    truth_path = args.output_dir / result.evaluator_truth.test_truth.path
    target = request.task.target_column.replace('"', '""')
    connection = duckdb.connect(database=":memory:")
    try:
        row = connection.execute(
            f'SELECT COUNT(*), AVG(CAST("{target}" AS DOUBLE)), '
            f'MIN(CAST("{target}" AS DOUBLE)), MAX(CAST("{target}" AS DOUBLE)) '
            "FROM read_parquet(?)",
            [str(truth_path)],
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        raise RuntimeError("aggregate evidence was not produced")

    evidence: dict[str, object] = {
        "task_type": request.task.task_type,
        "query_sha256": request.task.query_sha256,
        "columns": ["timestamp", request.task.entity_column, "target"],
        "row_count": int(row[0]),
        "null_rate": 0.0,
    }
    if request.task.task_type == "binary_classification":
        evidence["positive_rate"] = float(row[1])
    else:
        evidence["target_min"] = float(row[2])
        evidence["target_max"] = float(row[3])
    print(json.dumps(evidence, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
