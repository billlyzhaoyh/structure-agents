"""One bounded OpenAI Agents SDK compiler for H&M prediction tasks."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, Literal, Protocol, cast

from pydantic import BaseModel, ConfigDict, Field

from structagent_api.catalog import REL_HM_DATASET
from structagent_api.compiler.daytona import (
    DaytonaEvidenceExecutor,
    EvidenceExecutionError,
    EvidenceExecutor,
)
from structagent_api.compiler.service import (
    TaskCompiler,
    TaskCompilerError,
    UnavailableTaskCompiler,
    draft_id_for,
)
from structagent_api.compiler.sql import CandidateCache, CandidateLimitError, CandidateSpec
from structagent_api.contracts import (
    LiveDraftReady,
    LiveNeedsClarification,
    LiveTaskDraftOutcome,
    TaskClarificationRequest,
    TaskDraftRequest,
    TaskValidationEvidence,
    UnsupportedTaskDraft,
)
from structagent_api.contracts.models import (
    BinaryTaskContract,
    ClarificationQuestion,
    EntitySpec,
    HorizonSpec,
    PredictionTimeSpec,
    QueryArtifact,
    RegressionTaskContract,
    TargetSpec,
    TaskContract,
)
from structagent_api.materialization.hm_assets import verify_hm_assets
from structagent_api.materialization.task_sql import SqlPolicyError

MODEL = "gpt-5.6-terra"
OVERALL_TIMEOUT_SECONDS = 300
SQL_EXECUTION_TOOL_TIMEOUT_SECONDS = 180
INSTRUCTIONS = """You compile one natural-language request into a RelBench H&M task.
V1 supports only customer or article entities, binary classification or regression, and a
one-to-seven-day horizon. Ask concise clarification questions when entity, eligibility,
target semantics, aggregation/condition, type, or horizon is ambiguous. Return unsupported
for recommendation, multiclass, causal, intervention, policy-learning, or longer-horizon
requests. A ready task must call all four tools in order: inspect_reviewed_schema,
static_validate_sql, execute_validated_sql, read_aggregate_evidence. SQL must return exactly
timestamp, the reviewed entity key, and target. The SQL candidate budget limits repair attempts,
not rows or entities; never ask to narrow a population because that budget is exhausted. Never
return draft_ready unless aggregate evidence was returned for that exact digest during the
current run. Never request or infer raw rows. Human review is always required after compilation."""


def _reviewed_schema_json() -> str:
    """Describe source tables plus the framework-provided prediction cutoffs."""
    dataset = REL_HM_DATASET.model_dump(
        mode="json",
        exclude={"description", "display_name", "fixture", "implementation_status"},
    )
    return json.dumps(
        {
            "dataset": dataset,
            "framework_relations": [
                {
                    "name": "timestamps",
                    "purpose": "Scheduled prediction cutoffs supplied by the evaluation framework.",
                    "columns": [{"name": "timestamp", "data_type": "timestamp"}],
                }
            ],
            "sql_policy": {
                "dialect": "duckdb",
                "allowed_tables": ["article", "customer", "timestamps", "transactions"],
                "allowed_functions": ["AND", "CAST", "COALESCE", "EXISTS", "SUM"],
                "interval_rule": "Every interval must equal the declared horizon in days.",
                "output_columns": ["timestamp", "reviewed_entity_key", "target"],
                "candidate_budget": "At most three distinct SQL repair attempts per run.",
            },
        },
        sort_keys=True,
        separators=(",", ":"),
    )


class DecisionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ClarificationDecision(DecisionModel):
    outcome: Literal["needs_clarification"]
    questions: list[ClarificationQuestion] = Field(min_length=1)


class UnsupportedDecision(DecisionModel):
    outcome: Literal["unsupported"]
    reason_code: Literal[
        "unsupported_dataset",
        "unsupported_entity",
        "unsupported_target",
        "unsupported_horizon",
        "unsafe_request",
    ]
    explanation: str = Field(min_length=1)


class ReadyDecision(DecisionModel):
    outcome: Literal["draft_ready"]
    query_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    entity_table: Literal["customer", "article"]
    entity_column: Literal["customer_id", "article_id"]
    task_type: Literal["binary_classification", "regression"]
    horizon_days: int = Field(ge=1, le=7)
    target_description: str = Field(min_length=1)
    positive_class: str | None = None
    target_unit: str | None = None
    eligibility_definition: str = Field(min_length=1)
    label_definition: str = Field(min_length=1)


AgentDecision = Annotated[
    ClarificationDecision | UnsupportedDecision | ReadyDecision,
    Field(discriminator="outcome"),
]


class AgentOutput(DecisionModel):
    decision: AgentDecision


@dataclass
class CompilationContext:
    cache: CandidateCache
    executor: EvidenceExecutor
    evidence: dict[str, TaskValidationEvidence] = field(default_factory=dict)


class AgentRunner(Protocol):
    async def run(self, prompt: str, context: CompilationContext) -> AgentOutput: ...


class OpenAIAgentRunner:
    """Lazily import and run the pinned SDK so ordinary API imports remain keyless."""

    async def run(self, prompt: str, context: CompilationContext) -> AgentOutput:
        from agents import Agent, ModelSettings, RunConfig, RunContextWrapper, Runner, function_tool

        # The SDK resolves deferred tool annotations against module globals.
        globals()["RunContextWrapper"] = RunContextWrapper

        @function_tool
        async def inspect_reviewed_schema() -> str:
            """Return reviewed H&M tables, relationships, and framework inputs."""
            return _reviewed_schema_json()

        @function_tool
        async def static_validate_sql(
            wrapper: RunContextWrapper[CompilationContext],
            sql: str,
            entity_table: Literal["customer", "article"],
            entity_column: Literal["customer_id", "article_id"],
            task_type: Literal["binary_classification", "regression"],
            horizon_days: int,
        ) -> str:
            """Validate and cache one candidate; returns only a digest or sanitized error."""
            try:
                artifact = wrapper.context.cache.validate(
                    CandidateSpec(
                        sql=sql,
                        entity_table=entity_table,
                        entity_column=entity_column,
                        task_type=task_type,
                        horizon_days=horizon_days,
                    )
                )
                return json.dumps({"status": "passed", "query_sha256": artifact.query_sha256})
            except (SqlPolicyError, CandidateLimitError) as error:
                code = getattr(error, "code", "candidate_limit")
                return json.dumps({"status": "rejected", "code": code})

        @function_tool(timeout=SQL_EXECUTION_TOOL_TIMEOUT_SECONDS)
        async def execute_validated_sql(
            wrapper: RunContextWrapper[CompilationContext],
            query_sha256: str,
        ) -> str:
            """Execute a cached digest in private Daytona; never returns rows."""
            artifact = wrapper.context.cache.get(query_sha256)
            if artifact is None:
                return json.dumps({"status": "rejected", "code": "unknown_digest"})
            try:
                evidence = await wrapper.context.executor.validate(artifact)
                wrapper.context.evidence[query_sha256] = evidence
                return json.dumps({"status": "passed", "query_sha256": query_sha256})
            except EvidenceExecutionError as error:
                return json.dumps({"status": "rejected", "code": error.code})

        @function_tool
        async def read_aggregate_evidence(
            wrapper: RunContextWrapper[CompilationContext],
            query_sha256: str,
        ) -> str:
            """Return sanitized counts/balance/range for a successfully tested digest."""
            evidence = wrapper.context.evidence.get(query_sha256)
            if evidence is None:
                return json.dumps({"status": "rejected", "code": "evidence_unavailable"})
            return evidence.model_dump_json()

        agent = Agent[CompilationContext](
            name="StructAgent H&M task compiler",
            instructions=INSTRUCTIONS,
            model=MODEL,
            model_settings=ModelSettings(
                reasoning={"effort": "medium"},
                parallel_tool_calls=False,
                store=False,
                timeout=60,
            ),
            tools=[
                inspect_reviewed_schema,
                static_validate_sql,
                execute_validated_sql,
                read_aggregate_evidence,
            ],
            output_type=AgentOutput,
        )
        result = await Runner.run(
            agent,
            prompt,
            context=context,
            max_turns=12,
            run_config=RunConfig(
                tracing_disabled=True,
                trace_include_sensitive_data=False,
                workflow_name="StructAgent task compilation",
            ),
        )
        return cast(AgentOutput, result.final_output)


ExecutorFactory = Callable[[], EvidenceExecutor]


class NaturalLanguageTaskCompiler(TaskCompiler):
    def __init__(self, runner: AgentRunner, executor_factory: ExecutorFactory) -> None:
        self._runner = runner
        self._executor_factory = executor_factory

    async def compile(self, request: TaskDraftRequest) -> LiveTaskDraftOutcome:
        return await self._run(request.dataset_id, request.prompt, None)

    async def clarify(
        self,
        draft_id: str,
        request: TaskClarificationRequest,
    ) -> LiveTaskDraftOutcome:
        expected = draft_id_for(request.dataset_id, request.original_prompt)
        if draft_id != expected:
            raise TaskCompilerError(422, "draft_mismatch", "Clarification draft is invalid.")
        continuation = json.dumps(
            {
                "original_prompt": request.original_prompt,
                "questions": [
                    question.model_dump(mode="json") for question in request.prior_questions
                ],
                "answers": [answer.model_dump(mode="json") for answer in request.answers],
            },
            sort_keys=True,
        )
        return await self._run(request.dataset_id, request.original_prompt, continuation)

    async def _run(
        self,
        dataset_id: str,
        original_prompt: str,
        continuation: str | None,
    ) -> LiveTaskDraftOutcome:
        continuation_too_large = continuation is not None and len(continuation) > 20_000
        if len(original_prompt) > 4_000 or continuation_too_large:
            raise TaskCompilerError(422, "request_too_large", "Task request exceeds V1 limits.")
        if dataset_id != "rel-hm":
            return UnsupportedTaskDraft(
                contract_version="v1",
                outcome="unsupported",
                draft_id=draft_id_for(dataset_id, original_prompt),
                reason_code="unsupported_dataset",
                explanation="V1 supports only RelBench H&M.",
            )
        draft_id = draft_id_for(dataset_id, original_prompt)
        prompt_sha = hashlib.sha256(original_prompt.encode("utf-8")).hexdigest()
        schema_payload = _reviewed_schema_json()
        context = CompilationContext(
            cache=CandidateCache(
                draft_id=draft_id,
                model=MODEL,
                prompt_sha256=prompt_sha,
                schema_sha256=hashlib.sha256(schema_payload.encode("utf-8")).hexdigest(),
                instructions_sha256=hashlib.sha256(INSTRUCTIONS.encode("utf-8")).hexdigest(),
            ),
            executor=self._executor_factory(),
        )
        input_text = continuation or json.dumps({"original_prompt": original_prompt})
        run_error: BaseException | None = None
        try:
            async with asyncio.timeout(OVERALL_TIMEOUT_SECONDS):
                output = await self._runner.run(input_text, context)
            return self._assemble(draft_id, output.decision, context)
        except TimeoutError as error:
            run_error = error
            raise TaskCompilerError(
                504, "compiler_timeout", "Task compilation timed out."
            ) from error
        except TaskCompilerError as error:
            run_error = error
            raise
        except Exception as error:
            run_error = error
            name = type(error).__name__
            if name in {"ModelTimeoutError", "ToolTimeoutError"}:
                raise TaskCompilerError(
                    504, "compiler_timeout", "Task compilation timed out."
                ) from error
            if name in {"MaxTurnsExceeded", "ModelBehaviorError", "ModelRefusalError"}:
                raise TaskCompilerError(
                    422, "compilation_failed", "The request could not be compiled safely."
                ) from error
            raise TaskCompilerError(
                502, "provider_failure", "The task compiler provider failed."
            ) from error
        finally:
            try:
                await context.executor.close()
            except EvidenceExecutionError as error:
                if run_error is None:
                    raise TaskCompilerError(
                        502, "sandbox_cleanup", "SQL sandbox cleanup was not confirmed."
                    ) from error

    @staticmethod
    def _assemble(
        draft_id: str,
        decision: AgentDecision,
        context: CompilationContext,
    ) -> LiveTaskDraftOutcome:
        if isinstance(decision, ClarificationDecision):
            return LiveNeedsClarification(
                contract_version="v1",
                outcome="needs_clarification",
                draft_id=draft_id,
                questions=decision.questions,
            )
        if isinstance(decision, UnsupportedDecision):
            return UnsupportedTaskDraft(
                contract_version="v1",
                outcome="unsupported",
                draft_id=draft_id,
                reason_code=decision.reason_code,
                explanation=decision.explanation,
            )

        artifact = context.cache.get(decision.query_sha256)
        evidence = context.evidence.get(decision.query_sha256)
        if artifact is None or evidence is None:
            raise TaskCompilerError(
                422, "unvalidated_candidate", "The task did not complete guarded SQL validation."
            )
        evidence_values = evidence.model_dump(mode="python").values()
        if any(isinstance(value, float) and not math.isfinite(value) for value in evidence_values):
            raise TaskCompilerError(
                422, "invalid_evidence", "SQL validation returned non-finite aggregate evidence."
            )
        if (
            decision.entity_table != artifact.entity_table
            or decision.entity_column != artifact.entity_column
            or decision.task_type != artifact.task_type
            or decision.horizon_days != artifact.horizon_days
        ):
            raise TaskCompilerError(
                422, "candidate_mismatch", "The task semantics do not match the validated SQL."
            )
        query_artifacts = [
            QueryArtifact(
                purpose="eligibility",
                status="generated",
                dialect="duckdb",
                sql=artifact.normalized_sql,
            ),
            QueryArtifact(
                purpose="label",
                status="generated",
                dialect="duckdb",
                sql=artifact.normalized_sql,
            ),
        ]
        common: dict[str, Any] = {
            "source": "custom",
            "draft_id": draft_id,
            "dataset_id": "rel-hm",
            "entity": EntitySpec(table=artifact.entity_table, key_column=artifact.entity_column),
            "prediction_time": PredictionTimeSpec(table="timestamps", column="timestamp"),
            "horizon": HorizonSpec(value=artifact.horizon_days, unit="days"),
            "target": TargetSpec(
                name="target",
                description=decision.target_description,
                positive_class=decision.positive_class,
                unit=decision.target_unit,
            ),
            "eligibility_definition": decision.eligibility_definition,
            "label_definition": decision.label_definition,
            "query_artifacts": query_artifacts,
        }
        if artifact.task_type == "binary_classification":
            contract: TaskContract = BinaryTaskContract(
                **common,
                task_type="binary_classification",
                recommended_metrics=["auroc", "average_precision", "log_loss"],
            )
        else:
            contract = RegressionTaskContract(
                **common,
                task_type="regression",
                recommended_metrics=["mae", "rmse", "r2"],
            )
        return LiveDraftReady(
            contract_version="v1",
            outcome="draft_ready",
            draft_id=draft_id,
            contract=contract,
            sql_artifact=artifact,
            validation_evidence=evidence,
            review_required=True,
        )


def compiler_from_environment() -> TaskCompiler:
    """Build the live compiler only when both provider boundaries are configured."""
    if not os.environ.get("OPENAI_API_KEY") or not os.environ.get("DAYTONA_API_KEY"):
        return UnavailableTaskCompiler()
    cache_root = Path(os.environ.get("STRUCTAGENT_HM_CACHE_ROOT", ".artifacts/rel-hm"))

    def executor_factory() -> EvidenceExecutor:
        assets = verify_hm_assets(cache_root)
        return DaytonaEvidenceExecutor(assets.dataset)

    return NaturalLanguageTaskCompiler(OpenAIAgentRunner(), executor_factory)
