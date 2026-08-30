"""Private, ephemeral Daytona boundary for custom task validation."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final, Protocol, cast

from daytona import CreateSandboxFromImageParams, Daytona, Image, Resources
from pydantic import TypeAdapter

from structagent_api.contracts import CustomTaskSqlArtifact, TaskValidationEvidence
from structagent_api.materialization.materializer import HMDatasetFiles

REMOTE_ROOT: Final = "/workspace/structagent-compiler"
REMOTE_SOURCE: Final = f"{REMOTE_ROOT}/src"
REMOTE_INPUT: Final = f"{REMOTE_ROOT}/input"
REMOTE_OUTPUT: Final = f"{REMOTE_ROOT}/output"
QUERY_TIMEOUT_SECONDS: Final = 120

_SOURCE_FILES: Final = (
    "structagent_api/__init__.py",
    "structagent_api/catalog.py",
    "structagent_api/contracts/__init__.py",
    "structagent_api/contracts/compiler.py",
    "structagent_api/contracts/inference.py",
    "structagent_api/contracts/models.py",
    "structagent_api/compiler/__init__.py",
    "structagent_api/compiler/daytona_runner.py",
    "structagent_api/compiler/service.py",
    "structagent_api/materialization/__init__.py",
    "structagent_api/materialization/materializer.py",
    "structagent_api/materialization/synthetic.py",
    "structagent_api/materialization/task_sql.py",
)


class EvidenceExecutionError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


class EvidenceExecutor(Protocol):
    async def validate(self, task: CustomTaskSqlArtifact) -> TaskValidationEvidence: ...

    async def close(self) -> None: ...


class Sandbox(Protocol):
    id: str
    public: bool
    network_block_all: bool | None
    fs: Any
    process: Any

    def refresh_data(self, request_timeout: float | None = None) -> None: ...


class DaytonaClient(Protocol):
    def create(self, params: CreateSandboxFromImageParams, **kwargs: Any) -> Sandbox: ...

    def delete(self, sandbox: Sandbox, **kwargs: Any) -> None: ...


def _sandbox_params() -> CreateSandboxFromImageParams:
    return CreateSandboxFromImageParams(
        image=Image.debian_slim("3.12").pip_install(
            "duckdb==1.5.5", "pydantic==2.13.5", "sqlglot==30.17.0"
        ),
        language="python",
        labels={"project": "structagent", "purpose": "hm-custom-sql-validation"},
        public=False,
        network_block_all=True,
        ephemeral=True,
        auto_stop_interval=5,
        auto_delete_interval=0,
        ttl_minutes=5,
        resources=Resources(cpu=4, memory=8, disk=10),
    )


class DaytonaEvidenceExecutor:
    """Reuse one sandbox for at most one compiler run and delete it synchronously."""

    def __init__(
        self,
        dataset: HMDatasetFiles,
        *,
        client_factory: Callable[[], Any] = Daytona,
    ) -> None:
        self._dataset = dataset
        self._client = cast(DaytonaClient, client_factory())
        self._sandbox: Sandbox | None = None
        self._closed = False

    async def validate(self, task: CustomTaskSqlArtifact) -> TaskValidationEvidence:
        if self._closed:
            raise EvidenceExecutionError("sandbox_closed", "SQL validation is unavailable.")
        return await asyncio.to_thread(self._validate_sync, task)

    def _ensure_sandbox(self) -> Sandbox:
        if self._sandbox is not None:
            return self._sandbox
        try:
            sandbox = self._client.create(_sandbox_params(), timeout=120)
            sandbox.refresh_data(request_timeout=30)
            if sandbox.public or sandbox.network_block_all is not True:
                raise EvidenceExecutionError(
                    "sandbox_policy", "Daytona did not confirm the private network policy."
                )
            for directory in (
                REMOTE_ROOT,
                REMOTE_SOURCE,
                f"{REMOTE_SOURCE}/structagent_api",
                f"{REMOTE_SOURCE}/structagent_api/contracts",
                f"{REMOTE_SOURCE}/structagent_api/compiler",
                f"{REMOTE_SOURCE}/structagent_api/materialization",
                REMOTE_INPUT,
                REMOTE_OUTPUT,
            ):
                sandbox.fs.create_folder(directory, "755")
            source_root = Path(__file__).resolve().parents[2]
            for relative in _SOURCE_FILES:
                sandbox.fs.upload_file(str(source_root / relative), f"{REMOTE_SOURCE}/{relative}")
            for table, path in self._dataset.validated_paths().items():
                destination = f"{REMOTE_INPUT}/{table}.parquet"
                sandbox.fs.upload_file(str(path), destination)
                sandbox.fs.set_file_permissions(destination, "444")
            self._sandbox = sandbox
            return sandbox
        except EvidenceExecutionError:
            raise
        except Exception as error:
            raise EvidenceExecutionError(
                "sandbox_create", "Daytona SQL validation could not start."
            ) from error

    def _validate_sync(self, task: CustomTaskSqlArtifact) -> TaskValidationEvidence:
        sandbox = self._ensure_sandbox()
        request_path = f"{REMOTE_ROOT}/request-{task.query_sha256}.json"
        output_path = f"{REMOTE_OUTPUT}/{task.query_sha256}"
        payload = json.dumps(
            {"dataset_revision": self._dataset.revision, "task": task.model_dump(mode="json")},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        try:
            sandbox.fs.upload_file(payload, request_path)
            response = sandbox.process.exec(
                "python -m structagent_api.compiler.daytona_runner "
                f"{request_path} {REMOTE_INPUT} {output_path}",
                cwd=REMOTE_ROOT,
                env={"PYTHONPATH": REMOTE_SOURCE},
                timeout=QUERY_TIMEOUT_SECONDS,
            )
            if response.exit_code != 0:
                raise EvidenceExecutionError(
                    "query_rejected", "The candidate query failed guarded validation."
                )
            lines = [line for line in response.result.splitlines() if line.strip()]
            return TypeAdapter(TaskValidationEvidence).validate_json(lines[-1])
        except EvidenceExecutionError:
            raise
        except (IndexError, ValueError) as error:
            raise EvidenceExecutionError(
                "invalid_evidence", "Daytona returned invalid aggregate evidence."
            ) from error
        except Exception as error:
            raise EvidenceExecutionError(
                "provider_failure", "Daytona SQL validation failed."
            ) from error

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._sandbox is None:
            return
        try:
            await asyncio.to_thread(self._client.delete, self._sandbox, timeout=60, wait=True)
        except Exception as error:
            raise EvidenceExecutionError(
                "sandbox_cleanup", "Daytona sandbox cleanup was not confirmed."
            ) from error
