"""Trusted HTTP-facing service for synthetic Daytona materialization."""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from structagent_api.contracts import (
    DaytonaMaterializationResponse,
    DaytonaResourceSummary,
    DaytonaTaskSummary,
)
from structagent_api.materialization.daytona_executor import (
    DaytonaExecutionError,
    execute_daytona_materialization,
)
from structagent_api.materialization.synthetic import create_synthetic_hm
from structagent_api.materialization.task_sql import TaskId


def materialize_synthetic_in_daytona(
    task_ids: Sequence[TaskId],
) -> DaytonaMaterializationResponse:
    """Execute reviewed tasks without exposing provider credentials or artifact paths."""
    if not os.environ.get("DAYTONA_API_KEY"):
        raise DaytonaExecutionError(
            "missing_credential",
            "DAYTONA_API_KEY is required in the ignored server environment",
        )

    execution_id = f"mat-{uuid4().hex[:16]}"
    with TemporaryDirectory(prefix=f"structagent-{execution_id}-") as temporary_root:
        root = Path(temporary_root)
        dataset = create_synthetic_hm(root / "dataset")
        report = execute_daytona_materialization(task_ids, dataset, root / "tasks")

        summaries = []
        for task_id in task_ids:
            result = report.results[task_id]
            summaries.append(
                DaytonaTaskSummary(
                    task_id=task_id,
                    package_sha256=result.package_sha256,
                    validation_status=result.validation_report.status,
                    train_rows=result.model_input.train_labels.row_count,
                    validation_rows=result.model_input.validation_labels.row_count,
                    test_rows=result.model_input.test_rows.row_count,
                )
            )

        if not (
            report.cleanup_confirmed and report.network_block_all and report.sql_canary_confirmed
        ):
            raise DaytonaExecutionError(
                "sandbox_evidence",
                "Daytona did not return complete sandbox safety evidence",
            )

    return DaytonaMaterializationResponse(
        contract_version="v1",
        fixture=True,
        implementation_status="synthetic_execution",
        execution_id=execution_id,
        dataset_id="rel-hm",
        mode="daytona-synthetic",
        status="succeeded",
        cleanup_confirmed=True,
        network_block_all=True,
        sql_canary_confirmed=True,
        resources=DaytonaResourceSummary(
            cpu_cores=report.resources["cpu"],
            memory_gib=report.resources["memory"],
            disk_gib=report.resources["disk"],
        ),
        tasks=summaries,
    )
