"""Deterministic pseudo-random results for the explicitly simulated UI path."""

from __future__ import annotations

import hashlib
import random

from structagent_api.contracts import (
    ClassificationEvaluationResult,
    RegressionEvaluationResult,
    RunRecord,
    SimulatedInferenceRequest,
    SimulatedInferenceResponse,
)


def simulate_inference(request: SimulatedInferenceRequest) -> SimulatedInferenceResponse:
    """Return stable demo metrics without invoking a model or compute provider."""

    digest = hashlib.sha256(request.task_id.encode()).hexdigest()
    generator = random.Random(int(digest[:16], 16))
    run_id = f"sim-{digest[:16]}"
    common = {
        "contract_version": "v1",
        "fixture": True,
        "implementation_status": "placeholder",
        "run_id": run_id,
        "dataset_id": "rel-hm",
        "sample_count": generator.randint(650, 950),
        "coverage": round(generator.uniform(0.9, 0.99), 2),
        "provenance": {
            "dataset_revision": "synthetic",
            "model_id": "seeded-random-demo",
            "model_revision": "simulated",
            "context_length": 256,
            "duration_seconds": 0.0,
        },
        "integrity_checks": [
            {
                "name": "simulation_only",
                "status": "not_run",
                "detail": "Demo output only; no model prediction or truth evaluation occurred.",
            }
        ],
    }

    evaluation: ClassificationEvaluationResult | RegressionEvaluationResult
    if request.task_type == "binary_classification":
        prevalence = round(generator.uniform(0.2, 0.45), 2)
        evaluation = ClassificationEvaluationResult.model_validate(
            {
                **common,
                "task_type": "binary_classification",
                "prevalence": prevalence,
                "metrics": {
                    "auroc": round(generator.uniform(0.66, 0.84), 2),
                    "average_precision": round(generator.uniform(prevalence + 0.08, 0.72), 2),
                    "log_loss": round(generator.uniform(0.38, 0.62), 2),
                    "brier_score": round(generator.uniform(0.13, 0.23), 2),
                    "accuracy": round(generator.uniform(0.67, 0.84), 2),
                    "f1": round(generator.uniform(0.52, 0.76), 2),
                },
            },
        )
    else:
        mae = round(generator.uniform(8.0, 16.0), 1)
        evaluation = RegressionEvaluationResult.model_validate(
            {
                **common,
                "task_type": "regression",
                "target_unit": "dataset currency units",
                "metrics": {
                    "mae": mae,
                    "rmse": round(mae + generator.uniform(4.0, 9.0), 1),
                    "r2": round(generator.uniform(0.28, 0.56), 2),
                },
            },
        )

    return SimulatedInferenceResponse(
        contract_version="v1",
        fixture=True,
        implementation_status="simulated",
        run=RunRecord(
            contract_version="v1",
            fixture=True,
            implementation_status="placeholder",
            run_id=run_id,
            draft_id=request.task_id,
            status="succeeded",
            progress_percent=100,
            message="Seeded pseudo-random demo result; no model inference occurred.",
        ),
        evaluation=evaluation,
    )
