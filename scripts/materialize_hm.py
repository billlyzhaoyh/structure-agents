"""Run local or Daytona H&M task materialization without exposing row data."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from structagent_api.contracts import MaterializationResult
from structagent_api.materialization import (
    SYNTHETIC_CUTOFFS,
    MaterializationError,
    create_synthetic_hm,
    materialize_default_task,
)
from structagent_api.materialization.daytona_executor import (
    DaytonaExecutionError,
    execute_daytona_materialization,
)
from structagent_api.materialization.hm_assets import (
    AssetStagingError,
    verify_hm_assets,
)
from structagent_api.materialization.parity import ParityError, verify_materialization_parity
from structagent_api.materialization.task_sql import TaskId

TASK_IDS: tuple[TaskId, ...] = ("rel-hm/user-churn", "rel-hm/item-sales")


def _run_root(parent: Path, mode: str) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    root = parent / f"{timestamp}-{mode}"
    root.mkdir(parents=True, exist_ok=False)
    return root


def _task_summary(results: Mapping[Any, MaterializationResult]) -> dict[str, object]:
    return {
        str(task_id): {
            "package_sha256": result.package_sha256,
            "test_rows": result.model_input.test_rows.row_count,
            "validation_status": result.validation_report.status,
        }
        for task_id, result in results.items()
    }


def _run_local(runs_root: Path) -> dict[str, Any]:
    root = _run_root(runs_root, "local-synthetic")
    dataset = create_synthetic_hm(root / "dataset")
    results = {
        task_id: materialize_default_task(
            task_id,
            dataset,
            root / "tasks" / task_id.rsplit("/", maxsplit=1)[1],
            cutoffs=SYNTHETIC_CUTOFFS,
        )
        for task_id in TASK_IDS
    }
    return {"mode": "local-synthetic", "run_root": str(root), "tasks": _task_summary(results)}


def _require_daytona_key() -> None:
    if not os.environ.get("DAYTONA_API_KEY"):
        raise DaytonaExecutionError(
            "missing_credential", "DAYTONA_API_KEY is required in the ignored environment"
        )


def _run_daytona_synthetic(runs_root: Path) -> dict[str, Any]:
    _require_daytona_key()
    root = _run_root(runs_root, "daytona-synthetic")
    dataset = create_synthetic_hm(root / "dataset")
    report = execute_daytona_materialization(TASK_IDS, dataset, root / "tasks")
    return {
        "cleanup_confirmed": report.cleanup_confirmed,
        "mode": "daytona-synthetic",
        "network_block_all": report.network_block_all,
        "resources": report.resources,
        "run_root": str(root),
        "sql_canary_confirmed": report.sql_canary_confirmed,
        "tasks": _task_summary(report.results),
    }


def _run_daytona_live(runs_root: Path, cache_root: Path) -> dict[str, Any]:
    _require_daytona_key()
    if os.environ.get("STRUCTAGENT_ALLOW_REAL_HM") != "1":
        raise DaytonaExecutionError(
            "approval_required",
            "set STRUCTAGENT_ALLOW_REAL_HM=1 to acknowledge private H&M data transfer and cost",
        )
    staged = verify_hm_assets(cache_root)
    root = _run_root(runs_root, "daytona-rel-hm")
    report = execute_daytona_materialization(TASK_IDS, staged.dataset, root / "tasks")
    parity = {
        task_id: verify_materialization_parity(
            task_id,
            root / "tasks" / task_id.rsplit("/", maxsplit=1)[1],
            staged.expected_labels(task_id),
        )
        for task_id in TASK_IDS
    }
    (root / "parity.json").write_text(
        json.dumps(
            {task_id: result.model_dump(mode="json") for task_id, result in parity.items()},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "cleanup_confirmed": report.cleanup_confirmed,
        "mode": "daytona-rel-hm",
        "network_block_all": report.network_block_all,
        "parity": {task_id: result.status for task_id, result in parity.items()},
        "resources": report.resources,
        "run_root": str(root),
        "sql_canary_confirmed": report.sql_canary_confirmed,
        "tasks": _task_summary(report.results),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("local", "daytona-synthetic", "daytona-live"))
    parser.add_argument("--runs-root", type=Path, default=Path(".artifacts/runs"))
    parser.add_argument("--cache-root", type=Path, default=Path(".artifacts/rel-hm"))
    args = parser.parse_args()

    try:
        if args.mode == "local":
            report = _run_local(args.runs_root)
        elif args.mode == "daytona-synthetic":
            report = _run_daytona_synthetic(args.runs_root)
        else:
            report = _run_daytona_live(args.runs_root, args.cache_root)
    except (AssetStagingError, DaytonaExecutionError, MaterializationError, ParityError) as error:
        parser.error(f"{error.code}: {error.detail}")

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
