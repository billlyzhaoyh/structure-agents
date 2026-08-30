from __future__ import annotations

from typing import Any

import pytest
from agents.exceptions import UserError

from spikes.daytona_agents_sdk import smoke


class FakeResponse:
    def __init__(self, *, exit_code: int, result: str) -> None:
        self.exit_code = exit_code
        self.result = result


class FakeProcess:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls: list[tuple[str, int | None]] = []

    def code_run(self, code: str, timeout: int | None = None) -> FakeResponse:
        self.calls.append((code, timeout))
        return self.response


class FakeSandbox:
    def __init__(self, response: FakeResponse) -> None:
        self.process = FakeProcess(response)


class FakeDaytona:
    def __init__(self, response: FakeResponse) -> None:
        self.sandbox = FakeSandbox(response)
        self.create_calls: list[tuple[Any, float]] = []
        self.delete_calls: list[tuple[FakeSandbox, float, bool]] = []

    def create(self, params: Any, *, timeout: float = 60) -> FakeSandbox:
        self.create_calls.append((params, timeout))
        return self.sandbox

    def delete(
        self,
        sandbox: FakeSandbox,
        timeout: float = 60,
        wait: bool = False,
    ) -> None:
        self.delete_calls.append((sandbox, timeout, wait))


def successful_response() -> FakeResponse:
    return FakeResponse(
        exit_code=0,
        result='{"marker":"structagent-daytona-canary","python_version":"3.12.13"}\n',
    )


def test_executor_applies_safety_limits_and_confirms_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeDaytona(successful_response())
    monkeypatch.setattr(smoke, "Daytona", lambda: client)

    evidence = smoke.execute_daytona_canary()

    assert evidence == smoke.SandboxEvidence(
        marker=smoke.CANARY_MARKER,
        python_version="3.12.13",
        cleanup_confirmed=True,
        network_block_all_requested=True,
        ttl_minutes=10,
    )
    assert len(client.create_calls) == 1
    params, create_timeout = client.create_calls[0]
    assert create_timeout == 60
    assert params.public is False
    assert params.ephemeral is True
    assert params.auto_stop_interval == 5
    assert params.auto_delete_interval == 0
    assert params.ttl_minutes == 10
    assert params.network_block_all is True
    assert params.env_vars is None
    assert params.secrets is None
    assert client.sandbox.process.calls == [(smoke._CANARY_CODE, 30)]
    assert client.delete_calls == [(client.sandbox, 60, True)]


def test_executor_deletes_sandbox_when_canary_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeDaytona(FakeResponse(exit_code=17, result="failed"))
    monkeypatch.setattr(smoke, "Daytona", lambda: client)

    with pytest.raises(RuntimeError, match="exited with status 17"):
        smoke.execute_daytona_canary()

    assert client.delete_calls == [(client.sandbox, 60, True)]


def test_agent_loop_is_keyless_and_calls_the_executor_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    calls = 0

    def executor() -> smoke.SandboxEvidence:
        nonlocal calls
        calls += 1
        return smoke.SandboxEvidence(
            marker=smoke.CANARY_MARKER,
            python_version="3.12.13",
            cleanup_confirmed=True,
            network_block_all_requested=True,
            ttl_minutes=10,
        )

    report = smoke.run_keyless_agent(executor)

    assert calls == 1
    assert report.mode == "scripted-keyless"
    assert report.openai_api_used is False
    assert report.model_calls == 2
    assert report.final_output == smoke.FINAL_OUTPUT
    assert report.sandbox.cleanup_confirmed is True


def test_agent_loop_propagates_the_executor_error() -> None:
    def executor() -> smoke.SandboxEvidence:
        raise RuntimeError("provider failed")

    with pytest.raises(UserError, match="provider failed"):
        smoke.run_keyless_agent(executor)


def test_error_redaction_removes_known_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DAYTONA_API_KEY", "daytona-secret-value")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-secret-value")

    message = smoke.redact_error_message(
        RuntimeError("daytona-secret-value and openai-secret-value must not be logged")
    )

    assert message == "[REDACTED] and [REDACTED] must not be logged"


def test_cli_requires_only_the_daytona_key(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("DAYTONA_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    exit_code = smoke.main()

    assert exit_code == 2
    assert capsys.readouterr().err == (
        "DAYTONA_API_KEY is required for the live smoke test; OPENAI_API_KEY is not.\n"
    )
