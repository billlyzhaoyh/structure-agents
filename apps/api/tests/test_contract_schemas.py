from __future__ import annotations

from structagent_api.contracts.export import SCHEMA_DIR, check_schemas, render_schemas


def test_schema_export_has_stable_expected_inventory() -> None:
    assert set(render_schemas()) == {
        "dataset-descriptor.schema.json",
        "default-task-catalog.schema.json",
        "evaluation-result.schema.json",
        "run-record.schema.json",
        "task-draft-outcome.schema.json",
        "task-draft-request.schema.json",
    }


def test_committed_schema_snapshots_match_models() -> None:
    assert SCHEMA_DIR.is_dir()
    assert check_schemas() == []
