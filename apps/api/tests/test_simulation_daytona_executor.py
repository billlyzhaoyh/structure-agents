from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from daytona import CreateSandboxFromImageParams
from structagent_api.contracts.simulation import (
    SimulationPlanRequest,
    canonical_contract_json,
    contract_digest,
)
from structagent_api.simulation.daytona_executor import (
    REMOTE_PLAN,
    REMOTE_REQUEST,
    RUNTIME_CANARY_MARKER,
    SimulationDaytonaError,
    execute_daytona_simulation_plan,
)
from structagent_api.simulation.design import generate_run_plan
from structagent_api.simulation_catalog import hm_promo_conjoint_v1


class FakeResponse:
    def __init__(self, *, exit_code: int = 0, result: str = "") -> None:
        self.exit_code = exit_code
        self.result = result


class FakeFileSystem:
    def __init__(self, downloads: dict[str, bytes]) -> None:
        self.downloads = downloads
        self.folders: list[tuple[str, str]] = []
        self.uploads: list[tuple[str | bytes, str]] = []

    def create_folder(self, path: str, mode: str) -> None:
        self.folders.append((path, mode))

    def upload_file(self, src: str | bytes, dst: str, timeout: int = 1800) -> None:
        self.uploads.append((src, dst))

    def download_file(self, *args: str) -> bytes | None:
        return self.downloads.get(args[0])


class FakeProcess:
    def __init__(
        self,
        response: FakeResponse,
        *,
        execution_error: BaseException | None = None,
    ) -> None:
        self.response = response
        self.execution_error = execution_error
        self.calls: list[tuple[str, str | None, dict[str, str] | None, int | None]] = []

    def exec(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int | None = None,
    ) -> FakeResponse:
        self.calls.append((command, cwd, env, timeout))
        if RUNTIME_CANARY_MARKER in command:
            return FakeResponse(
                result=json.dumps({"marker": RUNTIME_CANARY_MARKER, "pydantic": "2.13.5"})
            )
        if self.execution_error is not None:
            raise self.execution_error
        return self.response


class FakeSandbox:
    def __init__(
        self,
        downloads: dict[str, bytes],
        process: FakeProcess,
        *,
        network_block_all: bool | None = True,
        public: bool = False,
    ) -> None:
        self.id = "sandbox-simulation-test"
        self.network_block_all = network_block_all
        self.public = public
        self.fs = FakeFileSystem(downloads)
        self.process = process
        self.refreshed = False

    def refresh_data(self, request_timeout: float | None = None) -> None:
        self.refreshed = True


class FakeClient:
    def __init__(self, sandbox: FakeSandbox, delete_error: Exception | None = None) -> None:
        self.sandbox = sandbox
        self.delete_error = delete_error
        self.created_params: CreateSandboxFromImageParams | None = None
        self.deleted = False

    def create(
        self,
        params: CreateSandboxFromImageParams,
        *,
        timeout: float = 60,
        on_snapshot_create_logs: Callable[[str], None] | None = None,
    ) -> FakeSandbox:
        self.created_params = params
        return self.sandbox

    def delete(self, sandbox: Any, timeout: float = 60, wait: bool = False) -> None:
        self.deleted = True
        if self.delete_error is not None:
            raise self.delete_error


def reviewed_request() -> SimulationPlanRequest:
    return SimulationPlanRequest(
        study=hm_promo_conjoint_v1(),
        agent_keys=tuple(f"synthetic-agent-{index:03d}" for index in range(400)),
    )


def successful_boundary() -> tuple[SimulationPlanRequest, FakeSandbox, FakeClient]:
    request = reviewed_request()
    plan = generate_run_plan(request)
    plan_bytes = (canonical_contract_json(plan) + "\n").encode("utf-8")
    response = FakeResponse(
        result=json.dumps(
            {
                "agent_count": 400,
                "implementation_status": "design_only",
                "plan_digest": contract_digest(plan),
                "status": "succeeded",
                "task_count": 4_000,
            }
        )
    )
    sandbox = FakeSandbox({REMOTE_PLAN: plan_bytes}, FakeProcess(response))
    return request, sandbox, FakeClient(sandbox)


def test_daytona_planner_uses_private_boundary_verifies_plan_and_cleans_up(
    tmp_path: Path,
) -> None:
    request, sandbox, client = successful_boundary()
    output_path = tmp_path / "plan.json"

    report = execute_daytona_simulation_plan(
        request,
        output_path,
        client_factory=lambda: client,
    )

    assert report.cleanup_confirmed is True
    assert report.network_block_all is True
    assert report.resources == {"cpu": 2, "disk": 5, "memory": 4}
    assert report.runtime_canary_confirmed is True
    assert report.plan.task_count == 4_000
    assert output_path.read_text(encoding="utf-8") == canonical_contract_json(report.plan) + "\n"
    assert client.deleted is True
    assert sandbox.refreshed is True
    assert client.created_params is not None
    assert client.created_params.public is False
    assert client.created_params.network_block_all is True
    assert client.created_params.resources is not None
    assert client.created_params.resources.gpu is None
    assert client.created_params.secrets is None
    assert client.created_params.env_vars is None
    request_upload = next(src for src, dst in sandbox.fs.uploads if dst == REMOTE_REQUEST)
    assert isinstance(request_upload, bytes)
    assert b"DAYTONA_API_KEY" not in request_upload
    assert b"OPENAI_API_KEY" not in request_upload
    uploaded_destinations = {dst for _, dst in sandbox.fs.uploads}
    assert any(
        destination.endswith("simulation/design.py") for destination in uploaded_destinations
    )
    assert any(
        destination.endswith("simulation/runner.py") for destination in uploaded_destinations
    )


def test_daytona_planner_rejects_tampered_plan_and_cleans_up(tmp_path: Path) -> None:
    request, sandbox, client = successful_boundary()
    plan_payload = json.loads(sandbox.fs.downloads[REMOTE_PLAN])
    plan_payload["random_seed"] = 999
    sandbox.fs.downloads[REMOTE_PLAN] = (
        json.dumps(plan_payload, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")

    with pytest.raises(SimulationDaytonaError) as raised:
        execute_daytona_simulation_plan(
            request,
            tmp_path / "plan.json",
            client_factory=lambda: client,
        )

    assert raised.value.code == "artifact_integrity"
    assert client.deleted is True
    assert not (tmp_path / "plan.json").exists()


def test_daytona_planner_fails_safely_on_provider_error_and_cleans_up(
    tmp_path: Path,
) -> None:
    request, sandbox, client = successful_boundary()
    sandbox.process.execution_error = TimeoutError("private provider detail")

    with pytest.raises(SimulationDaytonaError) as raised:
        execute_daytona_simulation_plan(
            request,
            tmp_path / "plan.json",
            client_factory=lambda: client,
        )

    assert raised.value.code == "provider_failure"
    assert "private provider detail" not in raised.value.detail
    assert client.deleted is True


def test_daytona_planner_rejects_unconfirmed_network_policy_and_cleans_up(
    tmp_path: Path,
) -> None:
    request, sandbox, _ = successful_boundary()
    sandbox.network_block_all = None
    client = FakeClient(sandbox)

    with pytest.raises(SimulationDaytonaError) as raised:
        execute_daytona_simulation_plan(
            request,
            tmp_path / "plan.json",
            client_factory=lambda: client,
        )

    assert raised.value.code == "sandbox_policy"
    assert client.deleted is True


def test_daytona_planner_reports_cleanup_failure(tmp_path: Path) -> None:
    request, sandbox, _ = successful_boundary()
    client = FakeClient(sandbox, delete_error=RuntimeError("private delete detail"))

    with pytest.raises(SimulationDaytonaError) as raised:
        execute_daytona_simulation_plan(
            request,
            tmp_path / "plan.json",
            client_factory=lambda: client,
        )

    assert raised.value.code == "sandbox_cleanup"
    assert "private delete detail" not in raised.value.detail
