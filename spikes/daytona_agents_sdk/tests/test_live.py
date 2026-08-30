from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest
from agents.exceptions import UserError
from agents.testing import ScriptedModel, assistant_message, function_call
from openai_codex import ApprovalMode, CodexConfig, Sandbox

from spikes.daytona_agents_sdk import live
from spikes.daytona_agents_sdk.smoke import CANARY_MARKER, CANARY_TOOL_NAME, SandboxEvidence


def sandbox_evidence() -> SandboxEvidence:
    return SandboxEvidence(
        marker=CANARY_MARKER,
        python_version="3.12.13",
        cleanup_confirmed=True,
        network_block_all_requested=True,
        ttl_minutes=10,
    )


def test_openai_api_agent_calls_daytona_once_with_structured_conclusion() -> None:
    calls = 0

    def executor() -> SandboxEvidence:
        nonlocal calls
        calls += 1
        return sandbox_evidence()

    model = ScriptedModel(
        [
            [function_call(CANARY_TOOL_NAME, {}, call_id="live-daytona-call")],
            [assistant_message('{"completed":true}')],
        ]
    )

    report = live.run_openai_api_smoke(executor, model=model)

    model.assert_complete()
    assert calls == 1
    assert report.provider == "openai-api"
    assert report.model == "ScriptedModel"
    assert report.openai_api_used is True
    assert report.conclusion.completed is True
    assert report.sandbox.cleanup_confirmed is True


def test_openai_api_agent_propagates_daytona_failure() -> None:
    def executor() -> SandboxEvidence:
        raise RuntimeError("daytona unavailable")

    model = ScriptedModel([[function_call(CANARY_TOOL_NAME, {}, call_id="failed-daytona-call")]])

    with pytest.raises(UserError, match="daytona unavailable"):
        live.run_openai_api_smoke(executor, model=model)


def test_codex_sdk_uses_read_only_empty_workspace_without_provider_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeTurnResult:
        final_response = '{"action":"run_daytona_canary"}'

    class FakeThread:
        def run(self, prompt: str, **kwargs: object) -> FakeTurnResult:
            captured["prompt"] = prompt
            captured["run_kwargs"] = kwargs
            return FakeTurnResult()

    class FakeCodex:
        def __init__(self, config: CodexConfig) -> None:
            captured["config"] = config

        def __enter__(self) -> FakeCodex:
            return self

        def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
            return None

        def account(self) -> SimpleNamespace:
            return SimpleNamespace(account=SimpleNamespace(root=SimpleNamespace(type="chatgpt")))

        def thread_start(self, **kwargs: object) -> FakeThread:
            captured["thread_kwargs"] = kwargs
            return FakeThread()

    monkeypatch.setenv("OPENAI_API_KEY", "openai-secret-value")
    monkeypatch.setenv("DAYTONA_API_KEY", "daytona-secret-value")
    monkeypatch.setenv("CODEX_ACCESS_TOKEN", "codex-secret-value")
    monkeypatch.setattr(live, "Codex", FakeCodex)

    directive = live.request_codex_directive("test-codex-model")

    config = cast(CodexConfig, captured["config"])
    assert config.env is not None
    assert "OPENAI_API_KEY" not in config.env
    assert "DAYTONA_API_KEY" not in config.env
    assert "CODEX_ACCESS_TOKEN" not in config.env

    thread_kwargs = cast(dict[str, Any], captured["thread_kwargs"])
    assert thread_kwargs["approval_mode"] is ApprovalMode.deny_all
    assert thread_kwargs["ephemeral"] is True
    assert thread_kwargs["model"] == "test-codex-model"
    assert thread_kwargs["sandbox"] is Sandbox.read_only
    assert directive.action == "run_daytona_canary"

    run_kwargs = cast(dict[str, Any], captured["run_kwargs"])
    assert run_kwargs["output_schema"] == live._CODEX_DIRECTIVE_SCHEMA


def test_codex_sdk_rejects_cached_api_key_authentication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCodex:
        def __init__(self, config: CodexConfig) -> None:
            self.config = config

        def __enter__(self) -> FakeCodex:
            return self

        def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
            return None

        def account(self) -> SimpleNamespace:
            return SimpleNamespace(account=SimpleNamespace(root=SimpleNamespace(type="apiKey")))

    monkeypatch.setattr(live, "Codex", FakeCodex)

    with pytest.raises(RuntimeError, match="requires an existing ChatGPT-authenticated"):
        live.request_codex_directive("test-codex-model")


def test_codex_sdk_runs_daytona_only_after_a_valid_directive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def executor() -> SandboxEvidence:
        nonlocal calls
        calls += 1
        return sandbox_evidence()

    monkeypatch.setattr(
        live,
        "request_codex_directive",
        lambda model=None: live.CodexDirective(action="run_daytona_canary"),
    )

    report = live.run_codex_sdk_smoke(executor, model="test-codex-model")

    assert calls == 1
    assert report.provider == "codex-sdk"
    assert report.model == "test-codex-model"
    assert report.authentication == "chatgpt"
    assert report.openai_api_key_exposed_to_codex is False
    assert report.daytona_api_key_exposed_to_codex is False
    assert report.directive.action == "run_daytona_canary"
