from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from daytona import CreateSandboxFromImageParams
from structagent_api.materialization import (
    SYNTHETIC_CUTOFFS,
    create_synthetic_hm,
    materialize_default_task,
)
from structagent_api.materialization.daytona_executor import (
    REMOTE_INPUT,
    REMOTE_OUTPUT,
    SQL_CANARY_MARKER,
    DaytonaExecutionError,
    execute_daytona_materialization,
)
from structagent_api.materialization.task_sql import TaskId


class FakeResponse:
    def __init__(self, *, exit_code: int = 0, result: str = "") -> None:
        self.exit_code = exit_code
        self.result = result


class FakeFileSystem:
    def __init__(self, downloads: dict[str, bytes]) -> None:
        self.downloads = downloads
        self.folders: list[tuple[str, str]] = []
        self.permissions: list[tuple[str, str | None]] = []
        self.uploads: list[tuple[str | bytes, str]] = []

    def create_folder(self, path: str, mode: str) -> None:
        self.folders.append((path, mode))

    def upload_file(self, src: str | bytes, dst: str, timeout: int = 1800) -> None:
        self.uploads.append((src, dst))

    def download_file(self, *args: str) -> bytes | None:
        return self.downloads.get(args[0])

    def set_file_permissions(self, path: str, mode: str | None = None) -> None:
        self.permissions.append((path, mode))


class FakeProcess:
    def __init__(
        self,
        response: FakeResponse | None = None,
        error: BaseException | None = None,
    ) -> None:
        self.response = response or FakeResponse()
        self.error = error
        self.calls: list[tuple[str, str | None, dict[str, str] | None, int | None]] = []

    def exec(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int | None = None,
    ) -> FakeResponse:
        self.calls.append((command, cwd, env, timeout))
        if self.error is not None:
            raise self.error
        if SQL_CANARY_MARKER in command:
            if self.response.exit_code != 0:
                return self.response
            return FakeResponse(result=json.dumps({"marker": SQL_CANARY_MARKER, "value": 1}))
        return self.response


class FakeSandbox:
    def __init__(
        self,
        *,
        downloads: dict[str, bytes] | None = None,
        network_block_all: bool | None = True,
        process: FakeProcess | None = None,
        public: bool = False,
    ) -> None:
        self.id = "sandbox-test"
        self.network_block_all = network_block_all
        self.public = public
        self.fs = FakeFileSystem(downloads or {})
        self.process = process or FakeProcess()
        self.refreshed = False

    def refresh_data(self, request_timeout: float | None = None) -> None:
        self.refreshed = True


class FakeClient:
    def __init__(self, sandbox: FakeSandbox, *, delete_error: Exception | None = None) -> None:
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


def expected_downloads(
    tmp_path: Path,
    task_ids: tuple[TaskId, ...],
) -> tuple[dict[str, bytes], dict[str, str]]:
    dataset = create_synthetic_hm(tmp_path / "expected-dataset")
    downloads: dict[str, bytes] = {}
    packages: dict[str, str] = {}
    for task_id in task_ids:
        slug = task_id.rsplit("/", maxsplit=1)[1]
        output = tmp_path / "expected-output" / slug
        result = materialize_default_task(
            task_id,
            dataset,
            output,
            cutoffs=SYNTHETIC_CUTOFFS,
        )
        packages[task_id] = result.package_sha256
        for path in output.iterdir():
            downloads[f"{REMOTE_OUTPUT}/{slug}/{path.name}"] = path.read_bytes()
    return downloads, packages


def test_daytona_executor_uses_private_cpu_boundary_and_cleans_up(tmp_path: Path) -> None:
    task_ids: tuple[TaskId, ...] = ("rel-hm/user-churn", "rel-hm/item-sales")
    downloads, packages = expected_downloads(tmp_path, task_ids)
    process = FakeProcess(
        FakeResponse(result=json.dumps({"status": "succeeded", "packages": packages}))
    )
    sandbox = FakeSandbox(downloads=downloads, process=process)
    client = FakeClient(sandbox)
    dataset = create_synthetic_hm(tmp_path / "input-dataset")

    report = execute_daytona_materialization(
        task_ids,
        dataset,
        tmp_path / "downloaded",
        client_factory=lambda: client,
    )

    assert report.cleanup_confirmed is True
    assert report.network_block_all is True
    assert report.resources == {"cpu": 4, "disk": 10, "memory": 8}
    assert report.sql_canary_confirmed is True
    assert client.deleted is True
    assert sandbox.refreshed is True
    assert client.created_params is not None
    assert client.created_params.public is False
    assert client.created_params.network_block_all is True
    assert client.created_params.resources is not None
    assert client.created_params.resources.gpu is None
    assert client.created_params.secrets is None
    assert client.created_params.env_vars is None
    assert sandbox.fs.permissions == [
        (f"{REMOTE_INPUT}/article.parquet", "444"),
        (f"{REMOTE_INPUT}/customer.parquet", "444"),
        (f"{REMOTE_INPUT}/transactions.parquet", "444"),
    ]
    uploaded_destinations = {destination for _, destination in sandbox.fs.uploads}
    assert any(
        destination.endswith("contracts/compiler.py") for destination in uploaded_destinations
    )
    assert any(
        destination.endswith("contracts/inference.py") for destination in uploaded_destinations
    )
    request_upload = next(src for src, dst in sandbox.fs.uploads if dst.endswith("request.json"))
    assert isinstance(request_upload, bytes)
    assert b"OPENAI_API_KEY" not in request_upload
    assert b"MODAL_TOKEN" not in request_upload


@pytest.mark.parametrize(
    ("sandbox", "expected_code"),
    [
        (FakeSandbox(network_block_all=None), "sandbox_policy"),
        (
            FakeSandbox(process=FakeProcess(FakeResponse(exit_code=17, result="private detail"))),
            "sandbox_canary",
        ),
        (
            FakeSandbox(process=FakeProcess(error=TimeoutError("provider secret detail"))),
            "provider_failure",
        ),
    ],
)
def test_daytona_executor_fails_safely_and_deletes_sandbox(
    tmp_path: Path,
    sandbox: FakeSandbox,
    expected_code: str,
) -> None:
    client = FakeClient(sandbox)
    dataset = create_synthetic_hm(tmp_path / "input-dataset")

    with pytest.raises(DaytonaExecutionError) as raised:
        execute_daytona_materialization(
            ("rel-hm/user-churn",),
            dataset,
            tmp_path / "downloaded",
            client_factory=lambda: client,
        )

    assert raised.value.code == expected_code
    assert "private detail" not in raised.value.detail
    assert "provider secret detail" not in raised.value.detail
    assert client.deleted is True


def test_daytona_executor_deletes_sandbox_on_cancellation(tmp_path: Path) -> None:
    sandbox = FakeSandbox(process=FakeProcess(error=KeyboardInterrupt()))
    client = FakeClient(sandbox)
    dataset = create_synthetic_hm(tmp_path / "input-dataset")

    with pytest.raises(KeyboardInterrupt):
        execute_daytona_materialization(
            ("rel-hm/user-churn",),
            dataset,
            tmp_path / "downloaded",
            client_factory=lambda: client,
        )

    assert client.deleted is True


def test_daytona_executor_reports_cleanup_failure(tmp_path: Path) -> None:
    task_ids: tuple[TaskId, ...] = ("rel-hm/user-churn",)
    downloads, packages = expected_downloads(tmp_path, task_ids)
    sandbox = FakeSandbox(
        downloads=downloads,
        process=FakeProcess(
            FakeResponse(result=json.dumps({"status": "succeeded", "packages": packages}))
        ),
    )
    client = FakeClient(sandbox, delete_error=RuntimeError("private delete detail"))
    dataset = create_synthetic_hm(tmp_path / "input-dataset")

    with pytest.raises(DaytonaExecutionError) as raised:
        execute_daytona_materialization(
            task_ids,
            dataset,
            tmp_path / "downloaded",
            client_factory=lambda: client,
        )

    assert raised.value.code == "sandbox_cleanup"
    assert "private delete detail" not in raised.value.detail
