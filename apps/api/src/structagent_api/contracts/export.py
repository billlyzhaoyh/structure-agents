"""Export or verify deterministic JSON Schema snapshots for V1 contracts."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from structagent_api.contracts.compiler import LiveTaskDraftOutcome, TaskClarificationRequest
from structagent_api.contracts.inference import (
    BatchEvaluationResult,
    ModalInferenceRequest,
    ModalInferenceResponse,
    PredictionPackage,
    RTJInferenceRequest,
    SimulatedInferenceRequest,
    SimulatedInferenceResponse,
)
from structagent_api.contracts.models import (
    DatasetDescriptor,
    DaytonaMaterializationRequest,
    DaytonaMaterializationResponse,
    DefaultTaskCatalog,
    EvaluationResult,
    MaterializationResult,
    RunRecord,
    TaskDraftOutcome,
    TaskDraftRequest,
    TaskSqlArtifact,
)

ROOT = Path(__file__).resolve().parents[5]
SCHEMA_DIR = ROOT / "contracts" / "v1" / "schemas"
SchemaFactory = Callable[[], dict[str, Any]]

SCHEMA_FACTORIES: dict[str, SchemaFactory] = {
    "dataset-descriptor.schema.json": DatasetDescriptor.model_json_schema,
    "daytona-materialization-request.schema.json": DaytonaMaterializationRequest.model_json_schema,
    "daytona-materialization-response.schema.json": (
        DaytonaMaterializationResponse.model_json_schema
    ),
    "default-task-catalog.schema.json": DefaultTaskCatalog.model_json_schema,
    "evaluation-result.schema.json": TypeAdapter(EvaluationResult).json_schema,
    "materialization-result.schema.json": MaterializationResult.model_json_schema,
    "live-task-draft-outcome.schema.json": TypeAdapter(LiveTaskDraftOutcome).json_schema,
    "modal-inference-request.schema.json": ModalInferenceRequest.model_json_schema,
    "modal-inference-response.schema.json": ModalInferenceResponse.model_json_schema,
    "prediction-package.schema.json": TypeAdapter(PredictionPackage).json_schema,
    "rtj-inference-request.schema.json": RTJInferenceRequest.model_json_schema,
    "simulated-inference-request.schema.json": SimulatedInferenceRequest.model_json_schema,
    "simulated-inference-response.schema.json": SimulatedInferenceResponse.model_json_schema,
    "run-record.schema.json": RunRecord.model_json_schema,
    "task-draft-outcome.schema.json": TypeAdapter(TaskDraftOutcome).json_schema,
    "task-draft-request.schema.json": TaskDraftRequest.model_json_schema,
    "task-clarification-request.schema.json": TaskClarificationRequest.model_json_schema,
    "task-sql-artifact.schema.json": TypeAdapter(TaskSqlArtifact).json_schema,
    "batch-evaluation-result.schema.json": TypeAdapter(BatchEvaluationResult).json_schema,
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
