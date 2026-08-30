"""Shared orchestration for one bounded, private H&M RT-J run."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Literal, cast

from structagent_api.contracts import BatchEvaluationResult
from structagent_api.inference.adapter import build_inference_request
from structagent_api.inference.evaluator import evaluate_predictions
from structagent_api.inference.modal_provider import EphemeralModalProvider
from structagent_api.inference.modal_runner import (
    ModalExecutionPolicy,
    ProjectionLedger,
    RTWorker,
    run_modal_inference,
)
from structagent_api.inference.smoke import create_user_churn_smoke_materialization


@dataclass(frozen=True)
class LiveModalOutcome:
    """Sanitized metadata; private artifacts remain below the caller-owned root."""

    evaluation: BatchEvaluationResult
    cleanup_confirmed: bool
    projected_cost_usd: Decimal
    projected_duration_seconds: Decimal


def run_user_churn_modal(
    *,
    dataset_root: Path,
    materialization_root: Path,
    output_root: Path,
    sample_size: int = 32,
    gpu: Literal["L4", "L40S"] = "L4",
) -> LiveModalOutcome:
    """Run and evaluate one deterministic real-data cohort through ephemeral Modal."""

    if output_root.exists():
        raise ValueError("output root already exists")
    task_root = output_root / "task"
    materialization = create_user_churn_smoke_materialization(
        materialization_root,
        task_root,
        sample_size=sample_size,
    )
    request = build_inference_request(materialization, gpu=gpu)
    prediction_root = output_root / "prediction"
    provider = EphemeralModalProvider(
        task_name="user-churn",
        checkpoint_variant="classification",
        prediction_root=prediction_root,
    )
    runtime_module = importlib.import_module("workers.rtj.runtime")
    worker = cast(RTWorker, runtime_module.run_task_inference)
    modal_result = run_modal_inference(
        request,
        (dataset_root, task_root),
        provider,
        worker,
        ProjectionLedger(),
        policy=ModalExecutionPolicy(gpu=gpu),
    )
    evaluation = evaluate_predictions(
        modal_result.prediction,
        prediction_root,
        materialization,
        task_root,
    )
    return LiveModalOutcome(
        evaluation=evaluation,
        cleanup_confirmed=modal_result.cleanup_confirmed,
        projected_cost_usd=modal_result.projection.estimated_cost_usd,
        projected_duration_seconds=modal_result.projection.duration_seconds,
    )
