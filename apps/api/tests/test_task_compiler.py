from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from structagent_api.api import create_app
from structagent_api.compiler.agent import (
    OVERALL_TIMEOUT_SECONDS,
    AgentOutput,
    ClarificationDecision,
    CompilationContext,
    NaturalLanguageTaskCompiler,
    OpenAIAgentRunner,
    ReadyDecision,
    UnsupportedDecision,
    _reviewed_schema_json,
)
from structagent_api.compiler.daytona import (
    _SOURCE_FILES,
    SANDBOX_TTL_MINUTES,
    DaytonaEvidenceExecutor,
    EvidenceExecutionError,
    _sandbox_params,
)
from structagent_api.compiler.service import TaskCompilerError, draft_id_for
from structagent_api.compiler.sql import CandidateCache, CandidateSpec
from structagent_api.contracts import (
    TaskDraftRequest,
)
from structagent_api.contracts.compiler import BinaryValidationEvidence
from structagent_api.contracts.models import ClarificationQuestion
from structagent_api.materialization.materializer import HMDatasetFiles
from structagent_api.materialization.synthetic import create_synthetic_hm
from structagent_api.materialization.task_sql import build_default_task_sql
from structagent_api.settings import Settings


def candidate_sql() -> str:
    return build_default_task_sql("rel-hm/user-churn").sql.replace("AS churn", "AS target")


def test_reviewed_compiler_schema_includes_framework_prediction_cutoffs() -> None:
    import json

    payload = json.loads(_reviewed_schema_json())

    assert [relation["name"] for relation in payload["framework_relations"]] == ["timestamps"]
    assert payload["framework_relations"][0]["columns"] == [
        {"name": "timestamp", "data_type": "timestamp"}
    ]
    assert payload["sql_policy"]["allowed_tables"] == [
        "article",
        "customer",
        "timestamps",
        "transactions",
    ]
    assert payload["sql_policy"]["allowed_functions"] == [
        "AND",
        "CAST",
        "COALESCE",
        "EXISTS",
        "SUM",
    ]


def test_compiler_sandbox_packages_imported_service_module() -> None:
    assert "structagent_api/compiler/service.py" in _SOURCE_FILES


class FakeEvidenceExecutor:
    def __init__(self, *, close_error: bool = False) -> None:
        self.calls = 0
        self.closed = False
        self.close_error = close_error

    async def validate(self, task: Any) -> BinaryValidationEvidence:
        self.calls += 1
        return BinaryValidationEvidence(
            task_type="binary_classification",
            query_sha256=task.query_sha256,
            columns=["timestamp", "customer_id", "target"],
            row_count=10,
            null_rate=0,
            positive_rate=0.4,
        )

    async def close(self) -> None:
        self.closed = True
        if self.close_error:
            from structagent_api.compiler.daytona import EvidenceExecutionError

            raise EvidenceExecutionError("sandbox_cleanup", "private detail")


class FakeRunner:
    def __init__(self, decision: str) -> None:
        self.decision = decision

    async def run(self, prompt: str, context: CompilationContext) -> AgentOutput:
        assert prompt
        if self.decision == "clarification":
            return AgentOutput(
                decision=ClarificationDecision(
                    outcome="needs_clarification",
                    questions=[
                        ClarificationQuestion(
                            question_id="horizon",
                            prompt="Use one day or seven days?",
                            answer_kind="single_choice",
                            choices=["1 day", "7 days"],
                        )
                    ],
                )
            )
        if self.decision == "unsupported":
            return AgentOutput(
                decision=UnsupportedDecision(
                    outcome="unsupported",
                    reason_code="unsupported_target",
                    explanation="Recommendation is outside V1.",
                )
            )
        if self.decision == "timeout":

            class ModelTimeoutError(RuntimeError):
                pass

            raise ModelTimeoutError("provider secret")

        artifact = context.cache.validate(
            CandidateSpec(
                sql=candidate_sql(),
                entity_table="customer",
                entity_column="customer_id",
                task_type="binary_classification",
                horizon_days=7,
            )
        )
        context.evidence[artifact.query_sha256] = await context.executor.validate(artifact)
        return AgentOutput(
            decision=ReadyDecision(
                outcome="draft_ready",
                query_sha256=artifact.query_sha256,
                entity_table="customer",
                entity_column="customer_id",
                task_type="binary_classification",
                horizon_days=7,
                target_description="One when an active customer makes no future purchase.",
                positive_class="No purchase in the future window.",
                eligibility_definition="Customers active in the prior seven days.",
                label_definition="No transaction in the next seven days.",
            )
        )


def compiler(decision: str, executor: FakeEvidenceExecutor | None = None) -> tuple[Any, Any]:
    resolved = executor or FakeEvidenceExecutor()
    return NaturalLanguageTaskCompiler(FakeRunner(decision), lambda: resolved), resolved


def test_live_route_returns_clarification_as_http_200() -> None:
    task_compiler, executor = compiler("clarification")
    client = TestClient(create_app(Settings(environment="test"), task_compiler=task_compiler))

    response = client.post(
        "/v1/task-drafts",
        json={"contract_version": "v1", "dataset_id": "rel-hm", "prompt": "Predict churn"},
    )

    assert response.status_code == 200
    assert response.json()["outcome"] == "needs_clarification"
    assert executor.closed is True


def test_live_route_returns_typed_unsupported_as_http_200() -> None:
    task_compiler, _ = compiler("unsupported")
    response = TestClient(
        create_app(Settings(environment="test"), task_compiler=task_compiler)
    ).post(
        "/v1/task-drafts",
        json={
            "contract_version": "v1",
            "dataset_id": "rel-hm",
            "prompt": "Recommend one item per customer",
        },
    )

    assert response.status_code == 200
    assert response.json()["reason_code"] == "unsupported_target"


def test_ready_task_is_validated_and_requires_review() -> None:
    task_compiler, executor = compiler("ready")
    client = TestClient(create_app(Settings(environment="test"), task_compiler=task_compiler))
    response = client.post(
        "/v1/task-drafts",
        json={"contract_version": "v1", "dataset_id": "rel-hm", "prompt": "Predict churn"},
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["outcome"] == "draft_ready"
    assert payload["review_required"] is True
    assert payload["contract"]["horizon"] == {"value": 7, "unit": "days"}
    assert payload["sql_artifact"]["task_id"].endswith(payload["sql_artifact"]["query_sha256"])
    assert {artifact["status"] for artifact in payload["contract"]["query_artifacts"]} == {
        "generated"
    }
    assert executor.calls == 1
    assert executor.closed is True


def test_cumulative_clarification_verifies_original_draft() -> None:
    task_compiler, _ = compiler("clarification")
    original = "Predict churn"
    request = {
        "contract_version": "v1",
        "dataset_id": "rel-hm",
        "original_prompt": original,
        "prior_questions": [
            {
                "question_id": "horizon",
                "prompt": "Use one day or seven days?",
                "answer_kind": "single_choice",
                "choices": ["1 day", "7 days"],
            }
        ],
        "answers": [{"question_id": "horizon", "answer_kind": "single_choice", "value": "7 days"}],
    }
    client = TestClient(create_app(Settings(environment="test"), task_compiler=task_compiler))

    response = client.post(
        f"/v1/task-drafts/{draft_id_for('rel-hm', original)}/clarifications",
        json=request,
    )
    mismatch = client.post(f"/v1/task-drafts/{'draft_' + 'a' * 64}/clarifications", json=request)

    assert response.status_code == 200
    assert mismatch.status_code == 422
    assert mismatch.json()["detail"]["code"] == "draft_mismatch"


def test_provider_timeout_and_cleanup_failure_are_sanitized() -> None:
    timeout_compiler, _ = compiler("timeout")
    cleanup_compiler, _ = compiler("clarification", FakeEvidenceExecutor(close_error=True))
    request = TaskDraftRequest(contract_version="v1", dataset_id="rel-hm", prompt="Predict churn")

    with pytest.raises(TaskCompilerError) as timeout:
        asyncio.run(timeout_compiler.compile(request))
    with pytest.raises(TaskCompilerError) as cleanup:
        asyncio.run(cleanup_compiler.compile(request))

    assert (timeout.value.status_code, timeout.value.code) == (504, "compiler_timeout")
    assert "secret" not in timeout.value.detail
    assert (cleanup.value.status_code, cleanup.value.code) == (502, "sandbox_cleanup")


def test_openai_runner_uses_one_fixed_agent_four_tools_and_disabled_tracing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    import agents

    captured: dict[str, Any] = {}

    async def fake_sdk_run(agent: Any, prompt: str, **kwargs: Any) -> Any:
        captured.update(agent=agent, prompt=prompt, kwargs=kwargs)
        return SimpleNamespace(
            final_output=AgentOutput(
                decision=UnsupportedDecision(
                    outcome="unsupported",
                    reason_code="unsupported_target",
                    explanation="Outside V1.",
                )
            )
        )

    monkeypatch.setattr(agents.Runner, "run", staticmethod(fake_sdk_run))
    executor = FakeEvidenceExecutor()
    context = CompilationContext(
        cache=CandidateCache(
            draft_id=draft_id_for("rel-hm", "Recommend products"),
            model="gpt-5.6-terra",
            prompt_sha256="a" * 64,
            schema_sha256="b" * 64,
            instructions_sha256="c" * 64,
        ),
        executor=executor,
    )

    asyncio.run(OpenAIAgentRunner().run("Recommend products", context))

    agent = captured["agent"]
    assert agent.model == "gpt-5.6-terra"
    assert agent.model_settings.reasoning.effort == "medium"
    assert [tool.name for tool in agent.tools] == [
        "inspect_reviewed_schema",
        "static_validate_sql",
        "execute_validated_sql",
        "read_aggregate_evidence",
    ]
    assert captured["kwargs"]["run_config"].tracing_disabled is True
    assert captured["kwargs"]["run_config"].trace_include_sensitive_data is False


class _StagingFileSystem:
    """Fail the dataset upload the way a large parquet transfer can."""

    def __init__(self, *, fail_on: str | None = None) -> None:
        self.fail_on = fail_on
        self.uploads: list[str] = []

    def create_folder(self, path: str, mode: str) -> None:
        return None

    def upload_file(self, src: str | bytes, dst: str, timeout: int = 1800) -> None:
        if self.fail_on is not None and self.fail_on in dst:
            raise RuntimeError("upload interrupted")
        self.uploads.append(dst)

    def set_file_permissions(self, path: str, mode: str | None = None) -> None:
        return None


class _StagingSandbox:
    def __init__(
        self, *, fail_on: str | None = None, network_block_all: bool | None = True
    ) -> None:
        self.id = "sandbox-compiler-test"
        self.public = False
        self.network_block_all = network_block_all
        self.fs = _StagingFileSystem(fail_on=fail_on)
        self.process = None

    def refresh_data(self, request_timeout: float | None = None) -> None:
        return None


class _StagingClient:
    def __init__(self, sandbox: _StagingSandbox) -> None:
        self.sandbox = sandbox
        self.created_params: Any = None
        self.deleted: list[Any] = []

    def create(self, params: Any, **kwargs: Any) -> _StagingSandbox:
        self.created_params = params
        return self.sandbox

    def delete(self, sandbox: Any, **kwargs: Any) -> None:
        self.deleted.append(sandbox)


def _hm_dataset(tmp_path: Path) -> HMDatasetFiles:
    return create_synthetic_hm(tmp_path / "dataset")


@pytest.mark.parametrize(
    ("fail_on", "expected_code"),
    [("input/transactions.parquet", "sandbox_create"), (None, None)],
)
def test_close_deletes_sandbox_even_when_staging_fails(
    tmp_path: Path,
    fail_on: str | None,
    expected_code: str | None,
) -> None:
    sandbox = _StagingSandbox(fail_on=fail_on)
    client = _StagingClient(sandbox)
    executor = DaytonaEvidenceExecutor(_hm_dataset(tmp_path), client_factory=lambda: client)

    if expected_code is None:
        assert executor._ensure_sandbox() is sandbox
    else:
        with pytest.raises(EvidenceExecutionError) as failure:
            executor._ensure_sandbox()
        assert failure.value.code == expected_code

    asyncio.run(executor.close())
    assert client.deleted == [sandbox]


def test_failed_staging_is_not_reused_by_a_later_validate(tmp_path: Path) -> None:
    sandbox = _StagingSandbox(fail_on="input/transactions.parquet")
    client = _StagingClient(sandbox)
    executor = DaytonaEvidenceExecutor(_hm_dataset(tmp_path), client_factory=lambda: client)

    with pytest.raises(EvidenceExecutionError):
        executor._ensure_sandbox()
    with pytest.raises(EvidenceExecutionError) as retry:
        executor._ensure_sandbox()

    assert retry.value.code == "sandbox_create"
    assert client.created_params is not None
    asyncio.run(executor.close())
    assert client.deleted == [sandbox]


def test_rejected_sandbox_policy_still_deletes_the_sandbox(tmp_path: Path) -> None:
    sandbox = _StagingSandbox(network_block_all=False)
    client = _StagingClient(sandbox)
    executor = DaytonaEvidenceExecutor(_hm_dataset(tmp_path), client_factory=lambda: client)

    with pytest.raises(EvidenceExecutionError) as failure:
        executor._ensure_sandbox()

    assert failure.value.code == "sandbox_policy"
    asyncio.run(executor.close())
    assert client.deleted == [sandbox]


def test_compiler_sandbox_ttl_outlasts_the_overall_run_budget() -> None:
    params = _sandbox_params()

    assert SANDBOX_TTL_MINUTES * 60 > OVERALL_TIMEOUT_SECONDS
    assert params.ttl_minutes == SANDBOX_TTL_MINUTES
    assert params.auto_stop_interval == 5
    assert params.auto_delete_interval == 0
    assert params.ephemeral is True
