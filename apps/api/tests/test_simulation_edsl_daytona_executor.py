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
from structagent_api.simulation.design import generate_run_plan
from structagent_api.simulation.edsl import (
    EdslChoiceRecord,
    EdslSmokeRequest,
    EdslSmokeResult,
    reviewed_edsl_smoke_request,
)
from structagent_api.simulation.edsl_daytona_executor import (
    DOMAIN_ALLOW_LIST,
    REMOTE_REQUEST,
    REMOTE_RESULT,
    RUNTIME_CANARY_MARKER,
    EdslDaytonaError,
    execute_daytona_edsl_smoke,
)
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
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
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
                result=json.dumps(
                    {
                        "marker": RUNTIME_CANARY_MARKER,
                        "edsl": "1.0.8",
                        "pydantic": "2.13.5",
                    }
                )
            )
        return self.response


class FakeSandbox:
    def __init__(
        self,
        downloads: dict[str, bytes],
        process: FakeProcess,
        *,
        domain_allow_list: str | None = DOMAIN_ALLOW_LIST,
        public: bool = False,
    ) -> None:
        self.id = "sandbox-edsl-test"
        self.domain_allow_list = domain_allow_list
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


def smoke_request() -> EdslSmokeRequest:
    study = hm_promo_conjoint_v1()
    plan_request = SimulationPlanRequest(
        study=study,
        agent_keys=tuple(f"synthetic-agent-{index:03d}" for index in range(400)),
    )
    plan = generate_run_plan(plan_request)
    return reviewed_edsl_smoke_request(plan.tasks[0])


def smoke_result() -> EdslSmokeResult:
    return EdslSmokeResult(
        task_id="task-0001-01",
        choices=(
            EdslChoiceRecord(repeat=1, selected="alternative_1"),
            EdslChoiceRecord(repeat=2, selected="alternative_1"),
            EdslChoiceRecord(repeat=3, selected="no_choice"),
        ),
    )


def successful_boundary() -> tuple[FakeSandbox, FakeClient]:
    result = smoke_result()
    result_bytes = (canonical_contract_json(result) + "\n").encode("utf-8")
    response = FakeResponse(
        result=json.dumps(
            {
                "choice_count": 3,
                "result_digest": contract_digest(result),
                "status": "succeeded",
            }
        )
    )
    sandbox = FakeSandbox({REMOTE_RESULT: result_bytes}, FakeProcess(response))
    return sandbox, FakeClient(sandbox)


def test_edsl_executor_mounts_opaque_secret_verifies_result_and_cleans_up(
    tmp_path: Path,
) -> None:
    request = smoke_request()
    sandbox, client = successful_boundary()
    output_path = tmp_path / "result.json"

    report = execute_daytona_edsl_smoke(
        request,
        output_path,
        "expected-parrot-test-secret",
        client_factory=lambda: client,
    )

    assert report.cleanup_confirmed is True
    assert report.domain_allow_list == ("api.expectedparrot.com", "storage.googleapis.com")
    assert report.secret_transport == "daytona_opaque_placeholder"
    assert report.result.choices[2].selected == "no_choice"
    assert output_path.read_text(encoding="utf-8") == canonical_contract_json(report.result) + "\n"
    assert client.deleted is True
    assert sandbox.refreshed is True
    assert client.created_params is not None
    assert client.created_params.public is False
    assert client.created_params.domain_allow_list == DOMAIN_ALLOW_LIST
    assert client.created_params.network_block_all is None
    assert client.created_params.secrets == {
        "EXPECTED_PARROT_API_KEY": "expected-parrot-test-secret"
    }
    assert client.created_params.env_vars is None
    request_upload = next(src for src, dst in sandbox.fs.uploads if dst == REMOTE_REQUEST)
    assert isinstance(request_upload, bytes)
    assert b"EXPECTED_PARROT_API_KEY" not in request_upload
    assert b"expected-parrot-test-secret" not in request_upload
    assert any(dst.endswith("simulation/edsl_runner.py") for _, dst in sandbox.fs.uploads)


def test_edsl_executor_rejects_provider_trace_and_cleans_up(tmp_path: Path) -> None:
    request = smoke_request()
    sandbox = FakeSandbox(
        {},
        FakeProcess(FakeResponse(exit_code=17, result="signed URL and private provider trace")),
    )
    client = FakeClient(sandbox)

    with pytest.raises(EdslDaytonaError) as raised:
        execute_daytona_edsl_smoke(
            request,
            tmp_path / "result.json",
            "expected-parrot-test-secret",
            client_factory=lambda: client,
        )

    assert raised.value.code == "sandbox_execution"
    assert "signed URL" not in raised.value.detail
    assert "private provider trace" not in raised.value.detail
    assert client.deleted is True


def test_edsl_executor_rejects_unconfirmed_domain_policy_and_cleans_up(
    tmp_path: Path,
) -> None:
    request = smoke_request()
    sandbox, _ = successful_boundary()
    sandbox.domain_allow_list = "api.expectedparrot.com"
    client = FakeClient(sandbox)

    with pytest.raises(EdslDaytonaError) as raised:
        execute_daytona_edsl_smoke(
            request,
            tmp_path / "result.json",
            "expected-parrot-test-secret",
            client_factory=lambda: client,
        )

    assert raised.value.code == "sandbox_policy"
    assert client.deleted is True


def test_edsl_executor_rejects_tampered_result_and_cleans_up(tmp_path: Path) -> None:
    request = smoke_request()
    sandbox, client = successful_boundary()
    payload = json.loads(sandbox.fs.downloads[REMOTE_RESULT])
    payload["task_id"] = "tampered-task"
    sandbox.fs.downloads[REMOTE_RESULT] = (
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")

    with pytest.raises(EdslDaytonaError) as raised:
        execute_daytona_edsl_smoke(
            request,
            tmp_path / "result.json",
            "expected-parrot-test-secret",
            client_factory=lambda: client,
        )

    assert raised.value.code == "artifact_integrity"
    assert client.deleted is True
    assert not (tmp_path / "result.json").exists()
