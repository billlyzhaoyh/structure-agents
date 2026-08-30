"""Provider-neutral construction of reviewed default RT-J requests."""

from __future__ import annotations

import hashlib
import json
from typing import Final, Literal

from structagent_api.contracts import (
    MaterializationResult,
    RTJCheckpointReference,
    RTJInferenceConfig,
    RTJInferenceRequest,
)

RT_SOURCE_REVISION: Final[Literal["455df27c1458e093eac00133d5bbf41a8263a2e3"]] = (
    "455df27c1458e093eac00133d5bbf41a8263a2e3"
)
RTJ_CHECKPOINT_REVISION: Final[Literal["a2c204c79d493ed0056661140e6fd24db3118381"]] = (
    "a2c204c79d493ed0056661140e6fd24db3118381"
)
MINILM_REVISION: Final[Literal["a50ef00143b4d5391434df20ae11632588ac25be"]] = (
    "a50ef00143b4d5391434df20ae11632588ac25be"
)
RELBENCH_EVALUATOR_REVISION: Final[Literal["9a223758cea1fd486a8d20f9e2f7ac4f42c88d0f"]] = (
    "9a223758cea1fd486a8d20f9e2f7ac4f42c88d0f"
)
REVIEWED_TASK_IDS = frozenset({"rel-hm/user-churn", "rel-hm/item-sales"})


def checkpoint_for_task(task_type: str) -> RTJCheckpointReference:
    variant = {
        "binary_classification": "classification",
        "regression": "regression",
    }.get(task_type)
    if variant is None:
        raise ValueError("RT-J supports only reviewed classification and regression tasks")
    if variant == "classification":
        return RTJCheckpointReference(
            repository_url="https://huggingface.co/stanford-star/rt-j",
            revision=RTJ_CHECKPOINT_REVISION,
            variant="classification",
            config_path="classification/config.json",
            weights_path="classification/model.safetensors",
            license="CC-BY-NC-SA-4.0",
        )
    return RTJCheckpointReference(
        repository_url="https://huggingface.co/stanford-star/rt-j",
        revision=RTJ_CHECKPOINT_REVISION,
        variant="regression",
        config_path="regression/config.json",
        weights_path="regression/model.safetensors",
        license="CC-BY-NC-SA-4.0",
    )


def build_inference_request(result: MaterializationResult) -> RTJInferenceRequest:
    """Build a fixed-protocol request from the model-visible package only."""
    if result.model_input.task.task_id not in REVIEWED_TASK_IDS:
        raise ValueError("live RT-J inference is limited to the two reviewed default tasks")
    model_input_payload = result.model_input.model_dump(mode="json")
    model_input_sha256 = hashlib.sha256(
        json.dumps(model_input_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if model_input_sha256 != result.model_input_sha256:
        raise ValueError("model-visible package digest is invalid")
    return RTJInferenceRequest(
        contract_version="v1",
        materialization_package_sha256=result.package_sha256,
        model_input_sha256=result.model_input_sha256,
        model_input=result.model_input,
        source_revision=RT_SOURCE_REVISION,
        checkpoint=checkpoint_for_task(result.model_input.task.task_type),
        config=RTJInferenceConfig(),
    )
