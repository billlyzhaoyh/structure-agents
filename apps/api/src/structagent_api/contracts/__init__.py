"""Versioned domain contracts shared with StructAgent clients."""

from structagent_api.contracts.models import (
    ClassificationEvaluationResult,
    DatasetDescriptor,
    DraftReady,
    EvaluationResult,
    NeedsClarification,
    RegressionEvaluationResult,
    RunRecord,
    TaskDraftOutcome,
    TaskDraftRequest,
)

__all__ = [
    "ClassificationEvaluationResult",
    "DatasetDescriptor",
    "DraftReady",
    "EvaluationResult",
    "NeedsClarification",
    "RegressionEvaluationResult",
    "RunRecord",
    "TaskDraftOutcome",
    "TaskDraftRequest",
]
