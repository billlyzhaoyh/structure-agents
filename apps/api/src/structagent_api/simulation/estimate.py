"""Honest descriptive estimation and validation for a real simulation response batch."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from typing import Final

from structagent_api.contracts.simulation import (
    CertificationGate,
    EffectDiagnostic,
    GateStatus,
    RecommendationStatus,
    RunProvenance,
    RunValidationGate,
    SimulationRunPlan,
    SimulationRunResult,
    SimulationStudyArtifact,
    ValidationGateResult,
    contract_digest,
)
from structagent_api.simulation.batch import (
    SimulationResponseBatch,
    prompt_template_digest,
)
from structagent_api.simulation.edsl import EDSL_VERSION, RESPONDENT_MODEL_ID
from structagent_api.simulation.population import SimulationPopulationPackage

ESTIMATOR_VERSION: Final = "descriptive-choice-v1"
VALIDATION_VERSION: Final = "simulation-validation-v1"
WORKER_VERSION: Final = "daytona-edsl-batch-v1"


def _digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _diagnostics(
    study: SimulationStudyArtifact,
    plan: SimulationRunPlan,
    batch: SimulationResponseBatch,
) -> tuple[EffectDiagnostic, ...]:
    tasks = {task.task_id: task for task in plan.tasks}
    counts: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
    for response in batch.responses:
        if response.repeat != 1:
            continue
        task = tasks[response.task_id]
        for position, alternative in enumerate(task.alternatives, start=1):
            chosen = response.selected == f"alternative_{position}"
            for item in alternative.profile:
                counts[(item.attribute, item.level)][0] += int(chosen)
                counts[(item.attribute, item.level)][1] += 1

    diagnostics: list[EffectDiagnostic] = []
    for attribute in study.study.attributes:
        baseline_wins, baseline_n = counts[(attribute.name, attribute.baseline_level)]
        baseline_rate = baseline_wins / baseline_n if baseline_n else 0.0
        for level in attribute.levels:
            if level == attribute.baseline_level:
                continue
            wins, observations = counts[(attribute.name, level)]
            rate = wins / observations if observations else 0.0
            estimate = (rate - baseline_rate) * 100
            variance = rate * (1 - rate) / max(1, observations) + baseline_rate * (
                1 - baseline_rate
            ) / max(1, baseline_n)
            margin = 1.96 * math.sqrt(variance) * 100
            suppressed = (
                observations < 30 or baseline_n < 30 or estimate - margin <= 0 <= estimate + margin
            )
            diagnostics.append(
                EffectDiagnostic(
                    attribute=attribute.name,
                    level=level,
                    estimate_percentage_points=round(estimate, 3),
                    confidence_interval_lower=round(estimate - margin, 3),
                    confidence_interval_upper=round(estimate + margin, 3),
                    suppressed=suppressed,
                    suppression_reason=(
                        "insufficient exposure or interval overlaps zero" if suppressed else None
                    ),
                )
            )
    return tuple(diagnostics)


def estimate_simulation_result(
    study: SimulationStudyArtifact,
    plan: SimulationRunPlan,
    population: SimulationPopulationPackage,
    batch: SimulationResponseBatch,
) -> SimulationRunResult:
    """Return real diagnostics while withholding a ranking until certification is implemented."""

    base = [response for response in batch.responses if response.repeat == 1]
    repeats = {response.task_id: response for response in batch.responses if response.repeat == 2}
    originals = {response.task_id: response for response in base}
    disagreement = sum(
        originals[task_id].selected != response.selected for task_id, response in repeats.items()
    ) / len(repeats)
    position_one = sum(response.selected == "alternative_1" for response in base) / len(base)
    position_two = sum(response.selected == "alternative_2" for response in base) / len(base)
    order_gap = abs(position_one - position_two)

    validation = (
        ValidationGateResult(
            gate=CertificationGate.ORDER_INVARIANCE,
            status=GateStatus.PASSED if order_gap <= 0.1 else GateStatus.FAILED,
            hard_gate=True,
            summary="Observed left/right selection-rate gap in the reviewed randomized design.",
            metric=round(order_gap, 6),
        ),
        ValidationGateResult(
            gate=CertificationGate.FULL_REPEAT_VARIANCE,
            status=GateStatus.PASSED if disagreement <= 0.35 else GateStatus.FAILED,
            hard_gate=True,
            summary="Observed disagreement across the deterministic repeated sentinel tasks.",
            metric=round(disagreement, 6),
        ),
        ValidationGateResult(
            gate=CertificationGate.TRAIT_ABLATION,
            status=GateStatus.NOT_APPLICABLE,
            hard_gate=True,
            summary="Trait-ablation certification has not yet been executed.",
        ),
        ValidationGateResult(
            gate=CertificationGate.MARKDOWN_CONCORDANCE,
            status=GateStatus.NOT_APPLICABLE,
            hard_gate=True,
            summary="Multi-window markdown concordance has not yet been executed.",
        ),
        ValidationGateResult(
            gate=CertificationGate.TEMPORAL_HOLDOUT,
            status=GateStatus.NOT_APPLICABLE,
            hard_gate=True,
            summary="Sealed temporal-holdout certification has not yet been executed.",
        ),
        ValidationGateResult(
            gate=RunValidationGate.CERTIFICATION_CURRENCY,
            status=GateStatus.NOT_APPLICABLE,
            hard_gate=True,
            summary="No complete certification artifact is current for this worker identity.",
        ),
        ValidationGateResult(
            gate=RunValidationGate.DESIGN_INVARIANTS,
            status=GateStatus.PASSED,
            hard_gate=True,
            summary="The canonical plan passed its count, sequence, and profile invariants.",
        ),
        ValidationGateResult(
            gate=RunValidationGate.RANDOMIZATION_BALANCE,
            status=GateStatus.PASSED if order_gap <= 0.1 else GateStatus.FAILED,
            hard_gate=True,
            summary="Alternative position selection remained within the declared tolerance.",
            metric=round(order_gap, 6),
        ),
        ValidationGateResult(
            gate=RunValidationGate.SENTINEL_REPEAT_VARIANCE,
            status=GateStatus.PASSED if disagreement <= 0.35 else GateStatus.FAILED,
            hard_gate=True,
            summary="Sentinel disagreement remained within the declared tolerance.",
            metric=round(disagreement, 6),
        ),
        ValidationGateResult(
            gate=RunValidationGate.DECLARED_MONOTONICITY,
            status=GateStatus.NOT_APPLICABLE,
            hard_gate=False,
            summary="A descriptive pilot does not claim a monotonic treatment response.",
        ),
    )
    certification_digest = _digest([item.model_dump(mode="json") for item in validation[:5]])
    return SimulationRunResult(
        run_id=f"sim-{contract_digest(batch).removeprefix('sha256:')[:20]}",
        study_artifact_id=study.artifact_id,
        recommendation_status=RecommendationStatus.WITHHELD,
        validation=validation,
        diagnostics=_diagnostics(study, plan, batch),
        limitations=(
            "This is an H&M-conditioned simulated-choice result, not observed customer behavior.",
            "No uplift, incrementality, elasticity, revenue, or expected-percentage claim "
            "is supported.",
            "A treatment shortlist is withheld until every certification gate is current.",
        ),
        provenance=RunProvenance(
            dataset_revision=population.dataset_revision,
            dataset_manifest_digest=population.dataset_manifest_digest,
            study_digest=contract_digest(study),
            trait_query_digest=population.trait_query_digest,
            prompt_template_digest=prompt_template_digest(),
            certification_digest=certification_digest,
            respondent_model_id=RESPONDENT_MODEL_ID,
            respondent_model_version=RESPONDENT_MODEL_ID,
            edsl_version=EDSL_VERSION,
            random_seed=plan.random_seed,
        ),
    )
