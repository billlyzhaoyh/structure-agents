from __future__ import annotations

from structagent_api.contracts.export import SCHEMA_DIR, check_schemas, render_schemas


def test_schema_export_has_stable_expected_inventory() -> None:
    assert set(render_schemas()) == {
        "batch-evaluation-result.schema.json",
        "dataset-descriptor.schema.json",
        "daytona-materialization-request.schema.json",
        "daytona-materialization-response.schema.json",
        "default-task-catalog.schema.json",
        "evaluation-result.schema.json",
        "live-task-draft-outcome.schema.json",
        "materialization-result.schema.json",
        "modal-inference-request.schema.json",
        "modal-inference-response.schema.json",
        "prediction-package.schema.json",
        "rtj-inference-request.schema.json",
        "run-record.schema.json",
        "simulated-inference-request.schema.json",
        "simulated-inference-response.schema.json",
        "task-clarification-request.schema.json",
        "task-draft-outcome.schema.json",
        "task-draft-request.schema.json",
        "task-sql-artifact.schema.json",
    }


def test_committed_schema_snapshots_match_models() -> None:
    assert SCHEMA_DIR.is_dir()
    assert check_schemas() == []
