"""Private ephemeral Daytona adapter for CPU-only H&M SQL materialization."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Final, Protocol, cast

from daytona import CreateSandboxFromImageParams, Daytona, Image, Resources
from pydantic import BaseModel, ConfigDict

from structagent_api.contracts import MaterializationResult
from structagent_api.materialization.materializer import HMDatasetFiles
from structagent_api.materialization.task_sql import TaskId, build_default_task_sql

REMOTE_ROOT: Final = "/workspace/structagent"
REMOTE_SOURCE: Final = f"{REMOTE_ROOT}/src"
REMOTE_INPUT: Final = f"{REMOTE_ROOT}/input"
REMOTE_OUTPUT: Final = f"{REMOTE_ROOT}/output"
SANDBOX_TTL_MINUTES: Final = 15
PROCESS_TIMEOUT_SECONDS: Final = 600
SQL_CANARY_MARKER: Final = "structagent-sql-canary"

_OUTPUT_FILES: Final = (
    "manifest.json",
    "test-truth.parquet",
    "test.parquet",
    "train.parquet",
    "validation.parquet",
)
_SOURCE_FILES: Final = (
    "structagent_api/__init__.py",
    "structagent_api/catalog.py",
    "structagent_api/contracts/__init__.py",
    "structagent_api/contracts/compiler.py",
    "structagent_api/contracts/inference.py",
    "structagent_api/contracts/models.py",
    "structagent_api/materialization/__init__.py",
    "structagent_api/materialization/daytona_runner.py",
    "structagent_api/materialization/materializer.py",
    "structagent_api/materialization/synthetic.py",
    "structagent_api/materialization/task_sql.py",
)


class DaytonaExecutionError(RuntimeError):
    """Sanitized provider, policy, or artifact failure."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


class ProcessResponse(Protocol):
    exit_code: int
    result: str


class SandboxProcess(Protocol):
    def exec(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int | None = None,
    ) -> ProcessResponse: ...


class SandboxFileSystem(Protocol):
    def create_folder(self, path: str, mode: str) -> None: ...

    def upload_file(self, src: str | bytes, dst: str, timeout: int = 1800) -> None: ...

    def download_file(self, *args: str) -> bytes | None: ...

    def set_file_permissions(self, path: str, mode: str | None = None) -> None: ...


class Sandbox(Protocol):
    id: str
    network_block_all: bool | None
    public: bool
    fs: SandboxFileSystem
    process: SandboxProcess

    def refresh_data(self, request_timeout: float | None = None) -> None: ...


class DaytonaClient(Protocol):
    def create(
        self,
        params: CreateSandboxFromImageParams,
        *,
        timeout: float = 60,
        on_snapshot_create_logs: Callable[[str], None] | None = None,
    ) -> Sandbox: ...

    def delete(self, sandbox: Sandbox, timeout: float = 60, wait: bool = False) -> None: ...


class DaytonaExecutionReport(BaseModel):
    """Sanitized evidence returned only after synchronous sandbox deletion."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cleanup_confirmed: bool
    network_block_all: bool
    resources: dict[str, int]
    results: dict[str, MaterializationResult]
    sql_canary_confirmed: bool


def _runtime_image() -> Image:
    return Image.debian_slim("3.12").pip_install(
        "duckdb==1.5.5",
        "pydantic==2.13.5",
        "sqlglot==30.17.0",
    )


def _sandbox_params() -> CreateSandboxFromImageParams:
    return CreateSandboxFromImageParams(
        image=_runtime_image(),
        language="python",
        labels={"project": "structagent", "purpose": "hm-sql-materialization"},
        public=False,
        auto_stop_interval=5,
        auto_delete_interval=0,
        ttl_minutes=SANDBOX_TTL_MINUTES,
        network_block_all=True,
        ephemeral=True,
        resources=Resources(cpu=4, memory=8, disk=10),
    )


def _source_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _create_remote_directories(sandbox: Sandbox) -> None:
    for directory in (
        REMOTE_ROOT,
        REMOTE_SOURCE,
        f"{REMOTE_SOURCE}/structagent_api",
        f"{REMOTE_SOURCE}/structagent_api/contracts",
        f"{REMOTE_SOURCE}/structagent_api/materialization",
        REMOTE_INPUT,
        REMOTE_OUTPUT,
    ):
        sandbox.fs.create_folder(directory, "755")


def _run_sql_canary(sandbox: Sandbox) -> None:
    response = sandbox.process.exec(
        'python -c "import duckdb,json; '
        f"print(json.dumps({{'marker':'{SQL_CANARY_MARKER}',"
        "'value':duckdb.sql('SELECT 1').fetchone()[0]}))\"",
        cwd=REMOTE_ROOT,
        timeout=30,
    )
    if response.exit_code != 0:
        raise DaytonaExecutionError("sandbox_canary", "Daytona SQL canary exited unsuccessfully")
    lines = [line for line in response.result.splitlines() if line.strip()]
    try:
        evidence = json.loads(lines[-1])
    except (IndexError, json.JSONDecodeError) as error:
        raise DaytonaExecutionError(
            "sandbox_canary", "Daytona SQL canary evidence is invalid"
        ) from error
    if evidence != {"marker": SQL_CANARY_MARKER, "value": 1}:
        raise DaytonaExecutionError("sandbox_canary", "Daytona SQL canary evidence is invalid")


def _upload_sources(sandbox: Sandbox) -> None:
    source_root = _source_root()
    for relative_path in _SOURCE_FILES:
        source = source_root / relative_path
        if not source.is_file():
            raise DaytonaExecutionError("runner_source", "a fixed sandbox source file is missing")
        sandbox.fs.upload_file(str(source), f"{REMOTE_SOURCE}/{relative_path}")


def _upload_dataset(sandbox: Sandbox, dataset: HMDatasetFiles) -> None:
    for table, path in dataset.validated_paths().items():
        destination = f"{REMOTE_INPUT}/{table}.parquet"
        sandbox.fs.upload_file(str(path), destination)
        sandbox.fs.set_file_permissions(destination, "444")


def _write_download(path: Path, contents: bytes | None) -> None:
    if contents is None:
        raise DaytonaExecutionError("artifact_download", "Daytona returned no artifact bytes")
    path.write_bytes(contents)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_result_files(result: MaterializationResult, output_dir: Path) -> None:
    references = (
        result.model_input.train_labels,
        result.model_input.validation_labels,
        result.model_input.test_rows,
        result.evaluator_truth.test_truth,
    )
    for reference in references:
        path = output_dir / reference.path
        if not path.is_file() or path.stat().st_size != reference.byte_count:
            raise DaytonaExecutionError("artifact_integrity", "downloaded artifact size is invalid")
        if _sha256(path) != reference.sha256:
            raise DaytonaExecutionError(
                "artifact_integrity", "downloaded artifact digest is invalid"
            )


def _download_results(
    sandbox: Sandbox,
    task_ids: Sequence[TaskId],
    output_root: Path,
) -> dict[str, MaterializationResult]:
    results: dict[str, MaterializationResult] = {}
    for task_id in task_ids:
        slug = task_id.rsplit("/", maxsplit=1)[1]
        output_dir = output_root / slug
        if output_dir.exists():
            raise DaytonaExecutionError("output_exists", "local Daytona output already exists")
        output_dir.mkdir(parents=True)
        for filename in _OUTPUT_FILES:
            remote = f"{REMOTE_OUTPUT}/{slug}/{filename}"
            _write_download(output_dir / filename, sandbox.fs.download_file(remote))

        try:
            result = MaterializationResult.model_validate_json(
                (output_dir / "manifest.json").read_text(encoding="utf-8")
            )
        except ValueError as error:
            raise DaytonaExecutionError(
                "artifact_manifest", "Daytona returned an invalid materialization manifest"
            ) from error
        if result.model_input.task.task_id != task_id:
            raise DaytonaExecutionError("artifact_manifest", "manifest task ID is misaligned")
        _verify_result_files(result, output_dir)
        results[task_id] = result
    return results


def execute_daytona_materialization(
    task_ids: Sequence[TaskId],
    dataset: HMDatasetFiles,
    output_root: Path,
    *,
    client_factory: Callable[[], Any] | None = None,
) -> DaytonaExecutionReport:
    """Run reviewed SQL in one bounded CPU sandbox and delete it synchronously."""
    if not task_ids or len(task_ids) != len(set(task_ids)):
        raise DaytonaExecutionError("task_ids", "one or two unique task IDs are required")
    for task_id in task_ids:
        build_default_task_sql(task_id)
        if (output_root / task_id.rsplit("/", maxsplit=1)[1]).exists():
            raise DaytonaExecutionError("output_exists", "local Daytona output already exists")
    dataset.validated_paths()

    factory = client_factory or Daytona
    client = cast(DaytonaClient, factory())
    try:
        sandbox = client.create(_sandbox_params(), timeout=180)
    except Exception as error:
        raise DaytonaExecutionError(
            "sandbox_create", "Daytona could not create the SQL sandbox"
        ) from error

    try:
        sandbox.refresh_data(request_timeout=30)
        if sandbox.public or sandbox.network_block_all is not True:
            raise DaytonaExecutionError(
                "sandbox_policy",
                "Daytona did not confirm a private sandbox with outbound networking blocked",
            )
        _create_remote_directories(sandbox)
        _run_sql_canary(sandbox)
        _upload_sources(sandbox)
        _upload_dataset(sandbox, dataset)
        request = json.dumps(
            {"dataset_revision": dataset.revision, "task_ids": list(task_ids)},
            sort_keys=True,
        ).encode("utf-8")
        sandbox.fs.upload_file(request, f"{REMOTE_ROOT}/request.json")
        response = sandbox.process.exec(
            "python -m structagent_api.materialization.daytona_runner "
            f"{REMOTE_ROOT}/request.json {REMOTE_INPUT} {REMOTE_OUTPUT}",
            cwd=REMOTE_ROOT,
            env={"PYTHONPATH": REMOTE_SOURCE},
            timeout=PROCESS_TIMEOUT_SECONDS,
        )
        if response.exit_code != 0:
            raise DaytonaExecutionError(
                "sandbox_execution", "Daytona task materialization exited unsuccessfully"
            )
        lines = [line for line in response.result.splitlines() if line.strip()]
        if not lines:
            raise DaytonaExecutionError("sandbox_execution", "Daytona returned no run evidence")
        try:
            evidence = json.loads(lines[-1])
        except json.JSONDecodeError as error:
            raise DaytonaExecutionError(
                "sandbox_execution", "Daytona returned malformed run evidence"
            ) from error
        if not isinstance(evidence, dict) or not isinstance(evidence.get("packages"), dict):
            raise DaytonaExecutionError("sandbox_execution", "Daytona run evidence is invalid")
        if evidence.get("status") != "succeeded" or set(evidence["packages"]) != set(task_ids):
            raise DaytonaExecutionError("sandbox_execution", "Daytona run evidence is incomplete")

        results = _download_results(sandbox, task_ids, output_root)
        for result_task_id, result in results.items():
            if evidence["packages"][result_task_id] != result.package_sha256:
                raise DaytonaExecutionError(
                    "artifact_manifest", "run evidence and package digest do not match"
                )
        report = DaytonaExecutionReport(
            cleanup_confirmed=True,
            network_block_all=True,
            resources={"cpu": 4, "disk": 10, "memory": 8},
            results=results,
            sql_canary_confirmed=True,
        )
    except DaytonaExecutionError:
        raise
    except Exception as error:
        raise DaytonaExecutionError("provider_failure", "Daytona SQL execution failed") from error
    finally:
        try:
            client.delete(sandbox, timeout=60, wait=True)
        except Exception as error:
            raise DaytonaExecutionError(
                "sandbox_cleanup", "Daytona could not confirm sandbox deletion"
            ) from error
    return report
