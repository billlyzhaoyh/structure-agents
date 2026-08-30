from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter
from structagent_api.contracts import (
    ClassificationEvaluationResult,
    DatasetDescriptor,
    DraftReady,
    EvaluationResult,
    NeedsClarification,
    RegressionEvaluationResult,
    RunRecord,
    TaskDraftOutcome,
    TaskDraftRequest,
)

EXAMPLE_ROOT = Path(__file__).resolve().parents[3] / "contracts" / "v1" / "examples"


def load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict), f"{path} must contain a JSON object"
    return payload


def fixture_paths(filename: str) -> list[Path]:
    return sorted(EXAMPLE_ROOT.glob(f"*/{filename}"))


@pytest.mark.parametrize("path", fixture_paths("dataset.json"), ids=lambda path: path.parent.name)
def test_dataset_fixtures_are_metadata_only(path: Path) -> None:
    descriptor = DatasetDescriptor.model_validate_json(path.read_text(encoding="utf-8"))

    assert descriptor.dataset_id == path.parent.name
    assert descriptor.fixture is True
    assert descriptor.implementation_status == "metadata_only"
    assert set(descriptor.supported_task_types) == {"binary_classification", "regression"}


@pytest.mark.parametrize(
    "path",
    fixture_paths("task-draft-request.json"),
    ids=lambda path: path.parent.name,
)
def test_task_request_fixtures_target_their_dataset(path: Path) -> None:
    request = TaskDraftRequest.model_validate_json(path.read_text(encoding="utf-8"))

    assert request.dataset_id == path.parent.name


@pytest.mark.parametrize(
    "path",
    fixture_paths("needs-clarification.json") + fixture_paths("task-contract.json"),
    ids=lambda path: f"{path.parent.name}-{path.stem}",
)
def test_task_outcome_fixtures_are_valid_placeholders(path: Path) -> None:
    outcome: NeedsClarification | DraftReady = TypeAdapter(TaskDraftOutcome).validate_json(
        path.read_text(encoding="utf-8")
    )

    assert outcome.fixture is True
    assert outcome.implementation_status == "placeholder"
    if outcome.outcome == "draft_ready":
        assert outcome.contract.dataset_id == path.parent.name
        assert {artifact.status for artifact in outcome.contract.query_artifacts} == {
            "not_generated"
        }
        assert all(artifact.sql is None for artifact in outcome.contract.query_artifacts)


@pytest.mark.parametrize(
    "path", fixture_paths("run-record.json"), ids=lambda path: path.parent.name
)
def test_run_fixtures_disclose_that_no_execution_occurred(path: Path) -> None:
    run = RunRecord.model_validate_json(path.read_text(encoding="utf-8"))

    assert run.fixture is True
    assert "no execution occurred" in run.message.lower()


@pytest.mark.parametrize(
    "path",
    fixture_paths("evaluation-result.json"),
    ids=lambda path: path.parent.name,
)
def test_result_fixtures_are_synthetic_and_unexecuted(path: Path) -> None:
    result: ClassificationEvaluationResult | RegressionEvaluationResult = TypeAdapter(
        EvaluationResult
    ).validate_json(path.read_text(encoding="utf-8"))

    assert result.fixture is True
    assert result.dataset_id == path.parent.name
    assert result.provenance.dataset_revision == "fixture-only"
    assert result.provenance.model_revision == "fixture-only"
    assert {check.status for check in result.integrity_checks} == {"not_run"}


def test_every_example_json_has_a_known_contract_role() -> None:
    expected_names = {
        "dataset.json",
        "evaluation-result.json",
        "needs-clarification.json",
        "run-record.json",
        "task-contract.json",
        "task-draft-request.json",
    }

    paths = sorted(EXAMPLE_ROOT.rglob("*.json"))
    assert {path.name for path in paths} == expected_names
    assert {path.parent.name for path in paths} == {"rel-amazon", "rel-hm"}
    assert all(load_object(path) for path in paths)
