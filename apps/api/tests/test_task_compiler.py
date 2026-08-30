from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from structagent_api.api import create_app
from structagent_api.compiler.agent import (
    AgentOutput,
    ClarificationDecision,
    CompilationContext,
    NaturalLanguageTaskCompiler,
    OpenAIAgentRunner,
    ReadyDecision,
    UnsupportedDecision,
    _reviewed_schema_json,
)
from structagent_api.compiler.service import TaskCompilerError, draft_id_for
from structagent_api.compiler.sql import CandidateCache, CandidateSpec
from structagent_api.contracts import (
    TaskDraftRequest,
)
from structagent_api.contracts.compiler import BinaryValidationEvidence
from structagent_api.contracts.models import ClarificationQuestion
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

    import asyncio

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
    import asyncio
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
