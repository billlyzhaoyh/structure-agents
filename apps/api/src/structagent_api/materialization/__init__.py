"""Guarded task-table materialization for the reviewed H&M defaults."""

from structagent_api.materialization.materializer import (
    HMDatasetFiles,
    MaterializationError,
    TemporalCutoffs,
    materialize_default_task,
    materialize_task,
)
from structagent_api.materialization.task_sql import SqlPolicyError, build_default_task_sql

__all__ = [
    "HMDatasetFiles",
    "MaterializationError",
    "SqlPolicyError",
    "TemporalCutoffs",
    "build_default_task_sql",
    "materialize_default_task",
    "materialize_task",
]
