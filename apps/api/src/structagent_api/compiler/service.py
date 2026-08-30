"""Provider-neutral task compiler service boundary."""

from __future__ import annotations

import hashlib
import json
from typing import Protocol

from structagent_api.contracts import (
    LiveTaskDraftOutcome,
    TaskClarificationRequest,
    TaskDraftRequest,
)


class TaskCompilerError(RuntimeError):
    """Sanitized compiler error with its public HTTP status."""

    def __init__(self, status_code: int, code: str, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.detail = detail


class TaskCompiler(Protocol):
    async def compile(self, request: TaskDraftRequest) -> LiveTaskDraftOutcome: ...

    async def clarify(
        self,
        draft_id: str,
        request: TaskClarificationRequest,
    ) -> LiveTaskDraftOutcome: ...


def draft_id_for(dataset_id: str, original_prompt: str) -> str:
    """Derive a stable identifier without retaining or exposing prompt text."""
    payload = json.dumps(
        {"dataset_id": dataset_id, "original_prompt": original_prompt},
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"draft_{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


class UnavailableTaskCompiler:
    """Fail closed when live compiler credentials or assets are not configured."""

    async def compile(self, request: TaskDraftRequest) -> LiveTaskDraftOutcome:
        del request
        raise TaskCompilerError(503, "compiler_unavailable", "Task compilation is unavailable.")

    async def clarify(
        self,
        draft_id: str,
        request: TaskClarificationRequest,
    ) -> LiveTaskDraftOutcome:
        del draft_id, request
        raise TaskCompilerError(503, "compiler_unavailable", "Task compilation is unavailable.")
