"""Run a bounded private RT-J smoke cohort on real RelBench H&M data."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any, cast

from structagent_api.inference import build_inference_request, evaluate_predictions
from structagent_api.inference.modal_provider import EphemeralModalProvider
from structagent_api.inference.modal_runner import (
    APPROVED_MODAL_GPUS,
    ModalExecutionPolicy,
    ProjectionLedger,
    RTWorker,
    run_modal_inference,
)
from structagent_api.inference.smoke import create_user_churn_smoke_materialization

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))


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

    task_root = args.output_root / "task"
    result = create_user_churn_smoke_materialization(
        args.materialization_root,
        task_root,
        sample_size=args.sample_size,
    )
    request = build_inference_request(result, gpu=args.gpu)
    prediction_root = args.output_root / "prediction"
    provider = EphemeralModalProvider(
        task_name="user-churn",
        checkpoint_variant="classification",
        prediction_root=prediction_root,
    )
    runtime_module = importlib.import_module("workers.rtj.runtime")
    worker = cast(RTWorker, runtime_module.run_task_inference)
    modal_result = run_modal_inference(
        request,
        (args.dataset_root, task_root),
        provider,
        worker,
        ProjectionLedger(),
        policy=ModalExecutionPolicy(gpu=args.gpu),
    )
    evaluation = evaluate_predictions(
        modal_result.prediction,
        prediction_root,
        result,
        task_root,
    )
    _write_private_json(
        args.output_root / "evaluation.json",
        evaluation.model_dump(mode="json"),
    )
    summary = {
        "cleanup_confirmed": modal_result.cleanup_confirmed,
        "dataset_revision": result.model_input.dataset_revision,
        "metrics": evaluation.metrics.model_dump(mode="json"),
        "model_input_sha256": result.model_input_sha256,
        "projected_cost_usd": str(modal_result.projection.estimated_cost_usd),
        "projected_duration_seconds": str(modal_result.projection.duration_seconds),
        "result_status": evaluation.result_status,
        "sample_count": evaluation.sample_count,
        "task_id": evaluation.task_id,
    }
    _write_private_json(args.output_root / "run.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
