"""Private ephemeral Daytona adapter for deterministic simulation design planning."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final, Protocol, cast

from daytona import CreateSandboxFromImageParams, Daytona, Image, Resources
from pydantic import BaseModel, ConfigDict

from structagent_api.contracts.simulation import (
    SimulationPlanRequest,
    SimulationRunPlan,
    canonical_contract_json,
    contract_digest,
)
from structagent_api.simulation.design import generate_run_plan

REMOTE_ROOT: Final = "/workspace/structagent"
REMOTE_SOURCE: Final = f"{REMOTE_ROOT}/src"
REMOTE_REQUEST: Final = f"{REMOTE_ROOT}/request.json"
REMOTE_PLAN: Final = f"{REMOTE_ROOT}/plan.json"
SANDBOX_TTL_MINUTES: Final = 15
PROCESS_TIMEOUT_SECONDS: Final = 600
RUNTIME_CANARY_MARKER: Final = "structagent-simulation-design-canary"

_SOURCE_FILES: Final = (
    "structagent_api/__init__.py",
    "structagent_api/contracts/__init__.py",
    "structagent_api/contracts/models.py",
    "structagent_api/contracts/simulation.py",
    "structagent_api/simulation/__init__.py",
    "structagent_api/simulation/design.py",
    "structagent_api/simulation/runner.py",
)


class SimulationDaytonaError(RuntimeError):
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


class SimulationDaytonaReport(BaseModel):
    """Sanitized evidence returned only after synchronous sandbox deletion."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cleanup_confirmed: bool
    network_block_all: bool
    plan: SimulationRunPlan
    plan_digest: str
    resources: dict[str, int]
    runtime_canary_confirmed: bool


def _runtime_image() -> Image:
    return Image.debian_slim("3.12").pip_install("pydantic==2.13.5")


def _sandbox_params() -> CreateSandboxFromImageParams:
    return CreateSandboxFromImageParams(
        image=_runtime_image(),
        language="python",
        labels={"project": "structagent", "purpose": "simulation-design-planning"},
        public=False,
        auto_stop_interval=5,
        auto_delete_interval=0,
        ttl_minutes=SANDBOX_TTL_MINUTES,
        network_block_all=True,
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
        'python -c "import json,pydantic; '
        f"print(json.dumps({{'marker':'{RUNTIME_CANARY_MARKER}',"
        "'pydantic':pydantic.__version__}))\"",
        cwd=REMOTE_ROOT,
        timeout=30,
    )
    if response.exit_code != 0:
        raise SimulationDaytonaError(
            "sandbox_canary", "Daytona simulation runtime canary exited unsuccessfully"
        )
    lines = [line for line in response.result.splitlines() if line.strip()]
    try:
        evidence = json.loads(lines[-1])
    except (IndexError, json.JSONDecodeError) as error:
        raise SimulationDaytonaError(
            "sandbox_canary", "Daytona simulation runtime canary evidence is invalid"
        ) from error
    if evidence != {"marker": RUNTIME_CANARY_MARKER, "pydantic": "2.13.5"}:
        raise SimulationDaytonaError(
            "sandbox_canary", "Daytona simulation runtime canary evidence is invalid"
        )


def _upload_sources(sandbox: Sandbox) -> None:
    source_root = _source_root()
    for relative_path in _SOURCE_FILES:
        source = source_root / relative_path
        if not source.is_file():
            raise SimulationDaytonaError("runner_source", "a fixed sandbox source file is missing")
        sandbox.fs.upload_file(str(source), f"{REMOTE_SOURCE}/{relative_path}")


def _parse_run_evidence(result: str) -> dict[str, object]:
    lines = [line for line in result.splitlines() if line.strip()]
    try:
        evidence = json.loads(lines[-1])
    except (IndexError, json.JSONDecodeError) as error:
        raise SimulationDaytonaError(
            "sandbox_execution", "Daytona returned malformed simulation run evidence"
        ) from error
    if not isinstance(evidence, dict) or evidence.get("status") != "succeeded":
        raise SimulationDaytonaError(
            "sandbox_execution", "Daytona simulation run evidence is incomplete"
        )
    return evidence


def _verify_downloaded_plan(
    contents: bytes,
    request: SimulationPlanRequest,
    evidence: dict[str, object],
) -> SimulationRunPlan:
    try:
        plan = SimulationRunPlan.model_validate_json(contents)
    except ValueError as error:
        raise SimulationDaytonaError(
            "artifact_manifest", "Daytona returned an invalid simulation run plan"
        ) from error
    canonical = (canonical_contract_json(plan) + "\n").encode("utf-8")
    if contents != canonical:
        raise SimulationDaytonaError(
            "artifact_integrity", "downloaded simulation run plan is not canonical"
        )
    digest = contract_digest(plan)
    if evidence.get("plan_digest") != digest:
        raise SimulationDaytonaError(
            "artifact_integrity", "run evidence and simulation plan digest do not match"
        )
    expected_evidence = {
        "agent_count": plan.agent_count,
        "implementation_status": plan.implementation_status,
        "task_count": plan.task_count,
    }
    if any(evidence.get(key) != value for key, value in expected_evidence.items()):
        raise SimulationDaytonaError(
            "artifact_integrity", "run evidence and simulation plan counts do not match"
        )
    if plan != generate_run_plan(request):
        raise SimulationDaytonaError(
            "artifact_integrity", "downloaded simulation plan does not match the request"
        )
    return plan


def execute_daytona_simulation_plan(
    request: SimulationPlanRequest,
    output_path: Path,
    *,
    client_factory: Callable[[], Any] | None = None,
) -> SimulationDaytonaReport:
    """Generate one reviewed design in Daytona, verify it locally, and delete the sandbox."""

    if output_path.exists():
        raise SimulationDaytonaError("output_exists", "local simulation plan already exists")
    if not output_path.parent.is_dir():
        raise SimulationDaytonaError("output_parent", "simulation plan parent directory is missing")

    factory = client_factory or Daytona
    client = cast(DaytonaClient, factory())
    try:
        sandbox = client.create(_sandbox_params(), timeout=180)
    except Exception as error:
        raise SimulationDaytonaError(
            "sandbox_create", "Daytona could not create the simulation sandbox"
        ) from error

    try:
        sandbox.refresh_data(request_timeout=30)
        if sandbox.public or sandbox.network_block_all is not True:
            raise SimulationDaytonaError(
                "sandbox_policy",
                "Daytona did not confirm a private sandbox with outbound networking blocked",
            )
        _create_remote_directories(sandbox)
        _run_runtime_canary(sandbox)
        _upload_sources(sandbox)
        sandbox.fs.upload_file(
            (canonical_contract_json(request) + "\n").encode("utf-8"), REMOTE_REQUEST
        )
        response = sandbox.process.exec(
            f"python -m structagent_api.simulation.runner {REMOTE_REQUEST} {REMOTE_PLAN}",
            cwd=REMOTE_ROOT,
            env={"PYTHONPATH": REMOTE_SOURCE},
            timeout=PROCESS_TIMEOUT_SECONDS,
        )
        if response.exit_code != 0:
            raise SimulationDaytonaError(
                "sandbox_execution", "Daytona simulation design exited unsuccessfully"
            )
        evidence = _parse_run_evidence(response.result)
        plan_bytes = sandbox.fs.download_file(REMOTE_PLAN)
        if plan_bytes is None:
            raise SimulationDaytonaError("artifact_download", "Daytona returned no run-plan bytes")
        plan = _verify_downloaded_plan(plan_bytes, request, evidence)
        output_path.write_bytes(plan_bytes)
        report = SimulationDaytonaReport(
            cleanup_confirmed=True,
            network_block_all=True,
            plan=plan,
            plan_digest=contract_digest(plan),
            resources={"cpu": 2, "disk": 5, "memory": 4},
            runtime_canary_confirmed=True,
        )
    except SimulationDaytonaError:
        raise
    except Exception as error:
        raise SimulationDaytonaError(
            "provider_failure", "Daytona simulation design execution failed"
        ) from error
    finally:
        try:
            client.delete(sandbox, timeout=60, wait=True)
        except Exception as error:
            raise SimulationDaytonaError(
                "sandbox_cleanup", "Daytona could not confirm simulation sandbox deletion"
            ) from error
    return report
