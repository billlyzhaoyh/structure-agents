"""Guarded task-table materialization for the reviewed H&M defaults."""

from structagent_api.materialization.materializer import (
    HMDatasetFiles,
    MaterializationError,
    TemporalCutoffs,
    materialize_default_task,
    materialize_task,
)
from structagent_api.materialization.synthetic import SYNTHETIC_CUTOFFS, create_synthetic_hm
from structagent_api.materialization.task_sql import SqlPolicyError, build_default_task_sql

__all__ = [
    "HMDatasetFiles",
    "MaterializationError",
    "SqlPolicyError",
    "SYNTHETIC_CUTOFFS",
    "TemporalCutoffs",
    "build_default_task_sql",
    "create_synthetic_hm",
    "materialize_default_task",
    "materialize_task",
]
