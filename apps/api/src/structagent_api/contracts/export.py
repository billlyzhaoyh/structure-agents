"""Export or verify deterministic JSON Schema snapshots for V1 contracts."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from structagent_api.contracts.models import (
    DatasetDescriptor,
    DefaultTaskCatalog,
    EvaluationResult,
    RunRecord,
    TaskDraftOutcome,
    TaskDraftRequest,
)

ROOT = Path(__file__).resolve().parents[5]
SCHEMA_DIR = ROOT / "contracts" / "v1" / "schemas"
SchemaFactory = Callable[[], dict[str, Any]]

SCHEMA_FACTORIES: dict[str, SchemaFactory] = {
    "dataset-descriptor.schema.json": DatasetDescriptor.model_json_schema,
    "default-task-catalog.schema.json": DefaultTaskCatalog.model_json_schema,
    "evaluation-result.schema.json": TypeAdapter(EvaluationResult).json_schema,
    "run-record.schema.json": RunRecord.model_json_schema,
    "task-draft-outcome.schema.json": TypeAdapter(TaskDraftOutcome).json_schema,
    "task-draft-request.schema.json": TaskDraftRequest.model_json_schema,
}


def render_schemas() -> dict[str, str]:
    """Render every public schema in stable filename and key order."""

    return {
        name: json.dumps(factory(), indent=2, sort_keys=True) + "\n"
        for name, factory in sorted(SCHEMA_FACTORIES.items())
    }


def export_schemas() -> None:
    """Write schema snapshots to the committed contract directory."""

    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    for name, contents in render_schemas().items():
        (SCHEMA_DIR / name).write_text(contents, encoding="utf-8")


def check_schemas() -> list[str]:
    """Return filenames whose committed contents differ from current models."""

    mismatches: list[str] = []
    for name, expected in render_schemas().items():
        path = SCHEMA_DIR / name
        if not path.is_file() or path.read_text(encoding="utf-8") != expected:
            mismatches.append(name)
    return mismatches


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when committed schemas do not match the Pydantic models",
    )
    args = parser.parse_args()

    if args.check:
        mismatches = check_schemas()
        if mismatches:
            parser.error("contract schema drift: " + ", ".join(mismatches))
        return 0

    export_schemas()
    return 0
