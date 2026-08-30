"""Provider-neutral contracts for sealed RT-J batch inference and evaluation."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from structagent_api.contracts.models import (
    ClassificationMetrics,
    ContractVersion,
    MaterializedFileReference,
    ModelTaskPackage,
    RegressionMetrics,
    StrictModel,
    TaskType,
)


class RTJCheckpointReference(StrictModel):
    repository_url: Literal["https://huggingface.co/stanford-star/rt-j"]
    revision: Literal["a2c204c79d493ed0056661140e6fd24db3118381"]
    variant: Literal["classification", "regression"]
    config_path: Literal["classification/config.json", "regression/config.json"]
    weights_path: Literal[
        "classification/model.safetensors",
        "regression/model.safetensors",
    ]
    license: Literal["CC-BY-NC-SA-4.0"]

    @model_validator(mode="after")
    def validate_variant_paths(self) -> RTJCheckpointReference:
        prefix = f"{self.variant}/"
        if not self.config_path.startswith(prefix) or not self.weights_path.startswith(prefix):
            raise ValueError("RT-J checkpoint paths do not match the selected variant")
        return self


class RTJInferenceConfig(StrictModel):
    context_length: Literal[256] = 256
    local_context_length: Literal[128] = 128
    bfs_width: Literal[32] = 32
    num_walks: Literal[10_000] = 10_000
    walk_length: Literal[20] = 20
    shuffle_seed: Literal[0] = 0
    context_seed: Literal[101] = 101
    gpu: Literal["L4"] = "L4"


class RTJInferenceRequest(StrictModel):
    contract_version: ContractVersion
    materialization_package_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_input: ModelTaskPackage
    source_revision: Literal["455df27c1458e093eac00133d5bbf41a8263a2e3"]
    checkpoint: RTJCheckpointReference
    config: RTJInferenceConfig

    @model_validator(mode="after")
    def validate_checkpoint_task(self) -> RTJInferenceRequest:
        expected_variant = {
            "binary_classification": "classification",
            "regression": "regression",
        }[self.model_input.task.task_type]
        if self.checkpoint.variant != expected_variant:
            raise ValueError("RT-J checkpoint does not match the task type")
        return self


class RTJRuntimeProvenance(StrictModel):
    provider: Literal["modal", "fake"]
    gpu: Literal["L4", "none"]
    duration_seconds: float = Field(ge=0)
    source_revision: str = Field(pattern=r"^[0-9a-f]{40}$|^synthetic$")
    checkpoint_revision: str = Field(pattern=r"^[0-9a-f]{40}$|^synthetic$")


class CompletedPredictionPackage(StrictModel):
    contract_version: ContractVersion
    status: Literal["observed", "synthetic"]
    dataset_id: Literal["rel-hm"]
    task_id: str = Field(min_length=1)
    task_type: TaskType
    dataset_revision: str = Field(pattern=r"^[0-9a-f]{40}$|^synthetic$")
    materialization_package_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    query_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prediction_file: MaterializedFileReference
    checkpoint: RTJCheckpointReference
    config: RTJInferenceConfig
    runtime: RTJRuntimeProvenance


class FailedPredictionPackage(StrictModel):
    contract_version: ContractVersion
    status: Literal["failed"]
    dataset_id: Literal["rel-hm"]
    task_id: str = Field(min_length=1)
    task_type: TaskType
    materialization_package_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    query_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    error_code: str = Field(min_length=1)
    runtime: RTJRuntimeProvenance


PredictionPackage = Annotated[
    CompletedPredictionPackage | FailedPredictionPackage,
    Field(discriminator="status"),
]


class BatchEvaluationBase(StrictModel):
    contract_version: ContractVersion
    result_status: Literal["observed", "synthetic"]
    dataset_id: Literal["rel-hm"]
    task_id: str = Field(min_length=1)
    sample_count: int = Field(gt=0)
    coverage: float = Field(ge=1, le=1)
    prediction_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    truth_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class BatchClassificationEvaluation(BatchEvaluationBase):
    task_type: Literal["binary_classification"]
    prevalence: float = Field(ge=0, le=1)
    metrics: ClassificationMetrics


class BatchRegressionMetrics(RegressionMetrics):
    nmae: float = Field(ge=0)


class BatchRegressionEvaluation(BatchEvaluationBase):
    task_type: Literal["regression"]
    metrics: BatchRegressionMetrics


BatchEvaluationResult = Annotated[
    BatchClassificationEvaluation | BatchRegressionEvaluation,
    Field(discriminator="task_type"),
]
