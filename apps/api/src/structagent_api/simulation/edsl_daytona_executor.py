"""Secure Daytona boundary for a genuine EDSL respondent-model integration smoke."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final, Protocol, cast

from daytona import CreateSandboxFromImageParams, Daytona, Image, Resources
from pydantic import BaseModel, ConfigDict

from structagent_api.contracts.simulation import canonical_contract_json, contract_digest
from structagent_api.simulation.batch import (
    SimulationBatchCheckpoint,
    SimulationBatchRequest,
    SimulationResponseBatch,
)
from structagent_api.simulation.edsl import (
    EDSL_VERSION,
    EdslSmokeRequest,
    EdslSmokeResult,
)

REMOTE_ROOT: Final = "/workspace/structagent"
REMOTE_SOURCE: Final = f"{REMOTE_ROOT}/src"
REMOTE_REQUEST: Final = f"{REMOTE_ROOT}/request.json"
REMOTE_RESULT: Final = f"{REMOTE_ROOT}/result.json"
REMOTE_CHECKPOINT: Final = f"{REMOTE_ROOT}/checkpoint.json"
EXPECTED_PARROT_DOMAIN: Final = "api.expectedparrot.com"
SIGNED_ARTIFACT_DOMAIN: Final = "storage.googleapis.com"
DOMAIN_ALLOW_LIST: Final = f"{EXPECTED_PARROT_DOMAIN},{SIGNED_ARTIFACT_DOMAIN}"
SANDBOX_TTL_MINUTES: Final = 15
PROCESS_TIMEOUT_SECONDS: Final = 600
BATCH_PROCESS_TIMEOUT_SECONDS: Final = 3600
RUNTIME_CANARY_MARKER: Final = "structagent-edsl-canary"

_SOURCE_FILES: Final = (
    "structagent_api/__init__.py",
    "structagent_api/contracts/__init__.py",
    "structagent_api/contracts/models.py",
    "structagent_api/contracts/simulation.py",
    "structagent_api/simulation/__init__.py",
    "structagent_api/simulation/design.py",
    "structagent_api/simulation/edsl.py",
    "structagent_api/simulation/edsl_runner.py",
    "structagent_api/simulation/batch.py",
    "structagent_api/simulation/batch_runner.py",
)


class EdslDaytonaError(RuntimeError):
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


class Sandbox(Protocol):
    id: str
    domain_allow_list: str | None
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


class EdslDaytonaReport(BaseModel):
    """Sanitized evidence returned only after synchronous sandbox deletion."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cleanup_confirmed: bool
    domain_allow_list: tuple[str, str]
    resources: dict[str, int]
    result: EdslSmokeResult
    result_digest: str
    runtime_canary_confirmed: bool
    secret_transport: str


class EdslBatchDaytonaReport(BaseModel):
    """Sanitized evidence for a complete EDSL response batch."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    batch: SimulationResponseBatch
    cleanup_confirmed: bool
    result_digest: str
    runtime_canary_confirmed: bool
    secret_transport: str


def _runtime_image() -> Image:
    return Image.debian_slim("3.12").pip_install(
        f"edsl=={EDSL_VERSION}",
        "pydantic==2.13.5",
    )


def _sandbox_params(secret_name: str) -> CreateSandboxFromImageParams:
    return CreateSandboxFromImageParams(
        image=_runtime_image(),
        language="python",
        labels={"project": "structagent", "purpose": "edsl-inference-smoke"},
        public=False,
        auto_stop_interval=5,
        auto_delete_interval=0,
        ttl_minutes=SANDBOX_TTL_MINUTES,
        domain_allow_list=DOMAIN_ALLOW_LIST,
        secrets={"EXPECTED_PARROT_API_KEY": secret_name},
        ephemeral=True,
        resources=Resources(cpu=2, memory=4, disk=5),
    )


def _source_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _create_remote_directories(sandbox: Sandbox) -> None:
    for directory in (
        REMOTE_ROOT,
        REMOTE_SOURCE,
        f"{REMOTE_SOURCE}/structagent_api",
        f"{REMOTE_SOURCE}/structagent_api/contracts",
        f"{REMOTE_SOURCE}/structagent_api/simulation",
    ):
        sandbox.fs.create_folder(directory, "755")


def _run_runtime_canary(sandbox: Sandbox) -> None:
    response = sandbox.process.exec(
        'python -c "import edsl,json,pydantic; '
        f"print(json.dumps({{'marker':'{RUNTIME_CANARY_MARKER}',"
        "'edsl':edsl.__version__,'pydantic':pydantic.__version__}))\"",
        cwd=REMOTE_ROOT,
        timeout=30,
    )
    if response.exit_code != 0:
        raise EdslDaytonaError("sandbox_canary", "Daytona EDSL canary exited unsuccessfully")
    lines = [line for line in response.result.splitlines() if line.strip()]
    try:
        evidence = json.loads(lines[-1])
    except (IndexError, json.JSONDecodeError) as error:
        raise EdslDaytonaError(
            "sandbox_canary", "Daytona EDSL canary evidence is invalid"
        ) from error
    if evidence != {
        "marker": RUNTIME_CANARY_MARKER,
        "edsl": EDSL_VERSION,
        "pydantic": "2.13.5",
    }:
        raise EdslDaytonaError("sandbox_canary", "Daytona EDSL canary evidence is invalid")


def _upload_sources(sandbox: Sandbox) -> None:
    source_root = _source_root()
    for relative_path in _SOURCE_FILES:
        source = source_root / relative_path
        if not source.is_file():
            raise EdslDaytonaError("runner_source", "a fixed EDSL sandbox source file is missing")
        sandbox.fs.upload_file(str(source), f"{REMOTE_SOURCE}/{relative_path}")


def _parse_run_evidence(result: str) -> dict[str, object]:
    lines = [line for line in result.splitlines() if line.strip()]
    try:
        evidence = json.loads(lines[-1])
    except (IndexError, json.JSONDecodeError) as error:
        raise EdslDaytonaError(
            "sandbox_execution", "Daytona returned malformed EDSL evidence"
        ) from error
    if not isinstance(evidence, dict) or evidence.get("status") != "succeeded":
        raise EdslDaytonaError("sandbox_execution", "Daytona EDSL execution failed")
    return evidence


def _verify_result(
    contents: bytes | None,
    request: EdslSmokeRequest,
    evidence: dict[str, object],
) -> tuple[EdslSmokeResult, bytes]:
    if contents is None:
        raise EdslDaytonaError("artifact_download", "Daytona returned no EDSL result bytes")
    try:
        result = EdslSmokeResult.model_validate_json(contents)
    except ValueError as error:
        raise EdslDaytonaError(
            "artifact_manifest", "Daytona returned an invalid EDSL result"
        ) from error
    canonical = (canonical_contract_json(result) + "\n").encode("utf-8")
    if contents != canonical:
        raise EdslDaytonaError("artifact_integrity", "downloaded EDSL result is not canonical")
    digest = contract_digest(result)
    if evidence.get("result_digest") != digest or evidence.get("choice_count") != request.repeats:
        raise EdslDaytonaError("artifact_integrity", "EDSL evidence and result do not match")
    if result.task_id != request.task.task_id:
        raise EdslDaytonaError("artifact_integrity", "EDSL result task is misaligned")
    return result, canonical


def execute_daytona_edsl_smoke(
    request: EdslSmokeRequest,
    output_path: Path,
    secret_name: str,
    *,
    client_factory: Callable[[], Any] | None = None,
) -> EdslDaytonaReport:
    """Run three genuine responses through EDSL and delete the sandbox synchronously."""

    if output_path.exists():
        raise EdslDaytonaError("output_exists", "local EDSL result already exists")
    if not output_path.parent.is_dir():
        raise EdslDaytonaError("output_parent", "EDSL result parent directory is missing")
    if not secret_name:
        raise EdslDaytonaError("secret_name", "a Daytona Expected Parrot secret is required")

    factory = client_factory or Daytona
    client = cast(DaytonaClient, factory())
    try:
        sandbox = client.create(_sandbox_params(secret_name), timeout=180)
    except Exception as error:
        raise EdslDaytonaError(
            "sandbox_create", "Daytona could not create the EDSL sandbox"
        ) from error

    try:
        sandbox.refresh_data(request_timeout=30)
        allowed = {item.strip() for item in (sandbox.domain_allow_list or "").split(",") if item}
        if sandbox.public or allowed != {EXPECTED_PARROT_DOMAIN, SIGNED_ARTIFACT_DOMAIN}:
            raise EdslDaytonaError(
                "sandbox_policy", "Daytona did not confirm the private EDSL domain allowlist"
            )
        _create_remote_directories(sandbox)
        _run_runtime_canary(sandbox)
        _upload_sources(sandbox)
        sandbox.fs.upload_file(
            (canonical_contract_json(request) + "\n").encode("utf-8"), REMOTE_REQUEST
        )
        response = sandbox.process.exec(
            f"python -m structagent_api.simulation.edsl_runner {REMOTE_REQUEST} {REMOTE_RESULT}",
            cwd=REMOTE_ROOT,
            env={"PYTHONPATH": REMOTE_SOURCE},
            timeout=PROCESS_TIMEOUT_SECONDS,
        )
        if response.exit_code != 0:
            raise EdslDaytonaError("sandbox_execution", "Daytona EDSL execution failed")
        evidence = _parse_run_evidence(response.result)
        result, canonical = _verify_result(
            sandbox.fs.download_file(REMOTE_RESULT), request, evidence
        )
        output_path.write_bytes(canonical)
        report = EdslDaytonaReport(
            cleanup_confirmed=True,
            domain_allow_list=(EXPECTED_PARROT_DOMAIN, SIGNED_ARTIFACT_DOMAIN),
            resources={"cpu": 2, "disk": 5, "memory": 4},
            result=result,
            result_digest=contract_digest(result),
            runtime_canary_confirmed=True,
            secret_transport="daytona_opaque_placeholder",
        )
    except EdslDaytonaError:
        raise
    except Exception as error:
        raise EdslDaytonaError("provider_failure", "Daytona EDSL execution failed") from error
    finally:
        try:
            client.delete(sandbox, timeout=60, wait=True)
        except Exception as error:
            raise EdslDaytonaError(
                "sandbox_cleanup", "Daytona could not confirm EDSL cleanup"
            ) from error
    return report


def execute_daytona_edsl_batch(
    request: SimulationBatchRequest,
    output_path: Path,
    secret_name: str,
    *,
    checkpoint_path: Path | None = None,
    client_factory: Callable[[], Any] | None = None,
) -> EdslBatchDaytonaReport:
    """Execute a complete reviewed response batch and verify cleanup and artifact integrity."""

    if output_path.exists() or not output_path.parent.is_dir() or not secret_name:
        raise EdslDaytonaError(
            "batch_input", "EDSL batch output or secret configuration is invalid"
        )
    client = cast(DaytonaClient, (client_factory or Daytona)())
    try:
        sandbox = client.create(_sandbox_params(secret_name), timeout=180)
    except Exception as error:
        raise EdslDaytonaError(
            "sandbox_create", "Daytona could not create the EDSL sandbox"
        ) from error
    try:
        sandbox.refresh_data(request_timeout=30)
        allowed = {item.strip() for item in (sandbox.domain_allow_list or "").split(",") if item}
        if sandbox.public or allowed != {EXPECTED_PARROT_DOMAIN, SIGNED_ARTIFACT_DOMAIN}:
            raise EdslDaytonaError(
                "sandbox_policy", "Daytona did not confirm the private EDSL domain allowlist"
            )
        _create_remote_directories(sandbox)
        _run_runtime_canary(sandbox)
        _upload_sources(sandbox)
        sandbox.fs.upload_file((canonical_contract_json(request) + "\n").encode(), REMOTE_REQUEST)
        if checkpoint_path is not None and checkpoint_path.exists():
            sandbox.fs.upload_file(str(checkpoint_path), REMOTE_CHECKPOINT)
        response = sandbox.process.exec(
            "python -m structagent_api.simulation.batch_runner "
            f"{REMOTE_REQUEST} {REMOTE_RESULT} {REMOTE_CHECKPOINT}",
            cwd=REMOTE_ROOT,
            env={"PYTHONPATH": REMOTE_SOURCE},
            timeout=BATCH_PROCESS_TIMEOUT_SECONDS,
        )
        try:
            remote_checkpoint = sandbox.fs.download_file(REMOTE_CHECKPOINT)
        except Exception:
            remote_checkpoint = None
        if checkpoint_path is not None and remote_checkpoint is not None:
            try:
                checkpoint = SimulationBatchCheckpoint.model_validate_json(remote_checkpoint)
            except ValueError as error:
                raise EdslDaytonaError(
                    "artifact_manifest", "Daytona returned an invalid EDSL checkpoint"
                ) from error
            canonical_checkpoint = (canonical_contract_json(checkpoint) + "\n").encode()
            if (
                remote_checkpoint != canonical_checkpoint
                or checkpoint.request_digest != contract_digest(request)
            ):
                raise EdslDaytonaError(
                    "artifact_integrity", "Daytona EDSL checkpoint is not canonical or aligned"
                )
            checkpoint_path.write_bytes(canonical_checkpoint)
        if response.exit_code != 0:
            lines = [line for line in response.result.splitlines() if line.strip()]
            try:
                failed_evidence = json.loads(lines[-1])
            except (IndexError, json.JSONDecodeError):
                failed_evidence = {}
            error_type = failed_evidence.get("error_type", "unknown")
            if not isinstance(error_type, str) or not error_type.isidentifier():
                error_type = "unknown"
            raise EdslDaytonaError(
                "batch_execution",
                f"Daytona EDSL batch execution failed ({error_type})",
            )
        evidence = _parse_run_evidence(response.result)
        contents = sandbox.fs.download_file(REMOTE_RESULT)
        if contents is None:
            raise EdslDaytonaError("artifact_download", "Daytona returned no EDSL batch bytes")
        try:
            batch = SimulationResponseBatch.model_validate_json(contents)
        except ValueError as error:
            raise EdslDaytonaError(
                "artifact_manifest", "Daytona returned an invalid EDSL batch"
            ) from error
        canonical = (canonical_contract_json(batch) + "\n").encode()
        digest = contract_digest(batch)
        if contents != canonical or evidence.get("result_digest") != digest:
            raise EdslDaytonaError(
                "artifact_integrity", "EDSL batch evidence and artifact do not match"
            )
        if (
            batch.base_response_count != request.plan.task_count
            or batch.sentinel_response_count != len(request.sentinel_task_ids)
        ):
            raise EdslDaytonaError(
                "artifact_integrity", "EDSL batch response counts are incomplete"
            )
        output_path.write_bytes(canonical)
        report = EdslBatchDaytonaReport(
            batch=batch,
            cleanup_confirmed=True,
            result_digest=digest,
            runtime_canary_confirmed=True,
            secret_transport="daytona_opaque_placeholder",
        )
    except EdslDaytonaError:
        raise
    except Exception as error:
        raise EdslDaytonaError("provider_failure", "Daytona EDSL batch execution failed") from error
    finally:
        try:
            client.delete(sandbox, timeout=60, wait=True)
        except Exception as error:
            raise EdslDaytonaError(
                "sandbox_cleanup", "Daytona could not confirm EDSL cleanup"
            ) from error
    return report
