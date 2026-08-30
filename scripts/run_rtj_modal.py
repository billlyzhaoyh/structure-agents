"""Run a bounded private RT-J smoke cohort on real RelBench H&M data."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from structagent_api.inference.live import run_user_churn_modal
from structagent_api.inference.modal_runner import APPROVED_MODAL_GPUS


def _write_private_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", required=True, type=Path)
    parser.add_argument("--materialization-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--sample-size", default=32, type=int)
    parser.add_argument("--gpu", choices=APPROVED_MODAL_GPUS, default="L4")
    args = parser.parse_args()

    if os.environ.get("STRUCTAGENT_ALLOW_REAL_HM") != "1":
        parser.error("STRUCTAGENT_ALLOW_REAL_HM=1 is required for private H&M data")
    if os.environ.get("STRUCTAGENT_ALLOW_RTJ_MODAL") != "1":
        parser.error("STRUCTAGENT_ALLOW_RTJ_MODAL=1 is required for paid private RT-J execution")
    if args.output_root.exists():
        parser.error("output root already exists")

    outcome = run_user_churn_modal(
        dataset_root=args.dataset_root,
        materialization_root=args.materialization_root,
        output_root=args.output_root,
        sample_size=args.sample_size,
        gpu=args.gpu,
    )
    _write_private_json(
        args.output_root / "evaluation.json",
        outcome.evaluation.model_dump(mode="json"),
    )
    summary = {
        "cleanup_confirmed": outcome.cleanup_confirmed,
        "dataset_revision": outcome.evaluation.dataset_revision,
        "metrics": outcome.evaluation.metrics.model_dump(mode="json"),
        "model_input_sha256": outcome.evaluation.model_input_sha256,
        "projected_cost_usd": str(outcome.projected_cost_usd),
        "projected_duration_seconds": str(outcome.projected_duration_seconds),
        "result_status": outcome.evaluation.result_status,
        "sample_count": outcome.evaluation.sample_count,
        "task_id": outcome.evaluation.task_id,
    }
    _write_private_json(args.output_root / "run.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
