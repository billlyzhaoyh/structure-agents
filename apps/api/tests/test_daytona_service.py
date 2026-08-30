from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest
from structagent_api.contracts import MaterializationResult
from structagent_api.materialization import (
    SYNTHETIC_CUTOFFS,
    HMDatasetFiles,
    materialize_default_task,
)
from structagent_api.materialization.daytona_executor import (
    DaytonaExecutionError,
    DaytonaExecutionReport,
)
from structagent_api.materialization.daytona_service import (
    materialize_synthetic_in_daytona,
)
from structagent_api.materialization.task_sql import TaskId


def test_http_service_requires_a_server_side_daytona_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DAYTONA_API_KEY", raising=False)

    with pytest.raises(DaytonaExecutionError, match="server environment") as error:
        materialize_synthetic_in_daytona(["rel-hm/user-churn"])

    assert error.value.code == "missing_credential"


def test_http_service_returns_sanitized_summaries_for_both_reviewed_tasks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    temporary_roots: list[Path] = []

    def execute_locally(
        task_ids: Sequence[TaskId],
        dataset: HMDatasetFiles,
        output_root: Path,
    ) -> DaytonaExecutionReport:
        temporary_roots.append(output_root.parent)
        results: dict[str, MaterializationResult] = {
            task_id: materialize_default_task(
                task_id,
                dataset,
                output_root / task_id.rsplit("/", maxsplit=1)[1],
                cutoffs=SYNTHETIC_CUTOFFS,
            )
            for task_id in task_ids
        }
        return DaytonaExecutionReport(
            cleanup_confirmed=True,
            network_block_all=True,
            resources={"cpu": 4, "memory": 8, "disk": 10},
            results=results,
            sql_canary_confirmed=True,
        )

    monkeypatch.setenv("DAYTONA_API_KEY", "synthetic-test-placeholder")
    monkeypatch.setattr(
        "structagent_api.materialization.daytona_service.execute_daytona_materialization",
        execute_locally,
    )

    response = materialize_synthetic_in_daytona(["rel-hm/user-churn", "rel-hm/item-sales"])

    assert [task.task_id for task in response.tasks] == [
        "rel-hm/user-churn",
        "rel-hm/item-sales",
    ]
    assert all(task.validation_status == "passed" for task in response.tasks)
    assert all(task.package_sha256 for task in response.tasks)
    assert response.resources.model_dump() == {
        "cpu_cores": 4,
        "memory_gib": 8,
        "disk_gib": 10,
    }
    assert response.cleanup_confirmed is True
    assert temporary_roots and not temporary_roots[0].exists()
