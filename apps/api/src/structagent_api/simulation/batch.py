"""Full reviewed-plan execution through EDSL's remote inference boundary."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Any, Final, Literal

from pydantic import Field, model_validator

from structagent_api.contracts.models import StrictModel
from structagent_api.contracts.simulation import SimulationRunPlan
from structagent_api.simulation.edsl import (
    EDSL_VERSION,
    RESPONDENT_MODEL_ID,
    RESPONDENT_MODEL_SERVICE,
    AgentTrait,
)

PROMPT_TEMPLATE_VERSION: Final = "promotion-choice-v1"
QUESTION_TEXT: Final = (
    "For this hypothetical fashion purchase, compare the offers below and choose exactly "
    "one option."
)
AGENT_INSTRUCTION: Final = (
    "You are a synthetic survey respondent conditioned only on the supplied aggregate retail "
    "traits. Choose one option without explanation."
)


def prompt_template_digest() -> str:
    payload = f"{PROMPT_TEMPLATE_VERSION}\n{QUESTION_TEXT}\n{AGENT_INSTRUCTION}".encode()
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


class BatchPersona(StrictModel):
    agent_key: str = Field(min_length=1)
    traits: tuple[AgentTrait, ...]


class SimulationBatchRequest(StrictModel):
    schema_version: Literal["1"] = "1"
    plan: SimulationRunPlan
    personas: tuple[BatchPersona, ...]
    sentinel_task_ids: tuple[str, ...]

    @model_validator(mode="after")
    def inputs_align(self) -> SimulationBatchRequest:
        if tuple(persona.agent_key for persona in self.personas) != tuple(
            dict.fromkeys(task.agent_key for task in self.plan.tasks)
        ):
            raise ValueError("persona order does not align with the run plan")
        task_ids = {task.task_id for task in self.plan.tasks}
        if not self.sentinel_task_ids or not set(self.sentinel_task_ids).issubset(task_ids):
            raise ValueError("sentinel tasks must be a non-empty subset of the plan")
        return self


class SimulationChoiceResponse(StrictModel):
    task_id: str = Field(min_length=1)
    agent_key: str = Field(min_length=1)
    repeat: int = Field(ge=1, le=2)
    selected: Literal["alternative_1", "alternative_2", "no_choice"]


class SimulationResponseBatch(StrictModel):
    schema_version: Literal["1"] = "1"
    evidence_kind: Literal["simulated"] = "simulated"
    respondent_model_id: Literal["gpt-5.6-luna"] = RESPONDENT_MODEL_ID
    respondent_model_service: Literal["openai"] = RESPONDENT_MODEL_SERVICE
    edsl_version: Literal["1.0.8"] = EDSL_VERSION
    base_response_count: int = Field(gt=0)
    sentinel_response_count: int = Field(gt=0)
    responses: tuple[SimulationChoiceResponse, ...] = Field(min_length=1)


class SimulationBatchCheckpoint(StrictModel):
    schema_version: Literal["1"] = "1"
    request_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    responses: tuple[SimulationChoiceResponse, ...] = ()

    @model_validator(mode="after")
    def responses_are_unique(self) -> SimulationBatchCheckpoint:
        keys = {(response.task_id, response.repeat) for response in self.responses}
        if len(keys) != len(self.responses):
            raise ValueError("checkpoint responses must be unique")
        return self


def _render_profile(task: Any, position: int) -> str:
    alternative = task.alternatives[position - 1]
    return "; ".join(
        f"{item.attribute.replace('_', ' ').title()}: "
        f"{item.level.replace('_percent', '%').replace('_', ' ').title()}"
        for item in alternative.profile
    )


def run_edsl_batch(
    request: SimulationBatchRequest,
    *,
    checkpoint: SimulationBatchCheckpoint | None = None,
    save_checkpoint: Callable[[SimulationBatchCheckpoint], None] | None = None,
) -> SimulationResponseBatch:
    """Execute every planned task once and repeat the deterministic sentinel subset."""

    import os

    import edsl  # type: ignore[import-untyped]
    from edsl import Agent, Model, QuestionMultipleChoice, Scenario, Survey
    from edsl.jobs.data_structures import (  # type: ignore[import-untyped]
        RunConfig,
        RunEnvironment,
        RunParameters,
    )

    if edsl.__version__ != EDSL_VERSION:
        raise ValueError("the EDSL runtime version is not pinned")
    from structagent_api.contracts.simulation import contract_digest

    request_digest = contract_digest(request)
    if checkpoint is not None and checkpoint.request_digest != request_digest:
        raise ValueError("the EDSL checkpoint belongs to another batch request")
    completed = {
        (response.task_id, response.repeat): response
        for response in (() if checkpoint is None else checkpoint.responses)
    }
    valid_keys = {(task.task_id, 1) for task in request.plan.tasks} | {
        (task_id, 2) for task_id in request.sentinel_task_ids
    }
    if not set(completed).issubset(valid_keys):
        raise ValueError("the EDSL checkpoint contains responses outside the run plan")
    agents_by_key = {
        persona.agent_key: Agent(
            traits={trait.name.value: trait.value for trait in persona.traits},
            instruction=AGENT_INSTRUCTION,
        )
        for persona in request.personas
    }
    model = Model(
        RESPONDENT_MODEL_ID,
        service_name=RESPONDENT_MODEL_SERVICE,
        temperature=0.5,
        max_tokens=16,
    )

    def execute_chunk(task_groups: list[list[Any]], repeat: int) -> list[SimulationChoiceResponse]:
        question_count = len(task_groups[0])
        if any(len(group) != question_count for group in task_groups):
            raise ValueError("every EDSL interview must contain the same number of tasks")
        questions = [
            QuestionMultipleChoice(
                question_name=f"promotion_choice_{index:02d}",
                question_text=QUESTION_TEXT,
                question_options=[
                    f"{{{{ option_1_{index:02d} }}}}",
                    f"{{{{ option_2_{index:02d} }}}}",
                    "No purchase",
                ],
                include_comment=False,
                use_code=True,
            )
            for index in range(1, question_count + 1)
        ]
        scenarios = []
        chunk_agents = []
        for position, group in enumerate(task_groups):
            agent_key = group[0].agent_key
            if any(task.agent_key != agent_key for task in group):
                raise ValueError("every EDSL interview must belong to one agent")
            chunk_agents.append(agents_by_key[agent_key])
            scenario: dict[str, object] = {
                "agent_key": agent_key,
                "agent_position": position,
            }
            for index, task in enumerate(group, start=1):
                scenario[f"task_id_{index:02d}"] = task.task_id
                scenario[f"option_1_{index:02d}"] = _render_profile(task, 1)
                scenario[f"option_2_{index:02d}"] = _render_profile(task, 2)
            scenarios.append(Scenario(scenario))
        job = Survey(questions).by(chunk_agents).by(scenarios).by(model)
        job.include_when("{{ scenario.agent_position == agent._index }}")
        config = RunConfig(
            environment=RunEnvironment(),
            parameters=RunParameters(
                n=1,
                progress_bar=False,
                stop_on_exception=True,
                check_api_keys=True,
                verbose=False,
                print_exceptions=False,
                remote_inference_description=(
                    "StructAgent simulation "
                    f"{request_digest.removeprefix('sha256:')[:12]} repeat {repeat} "
                    f"choices {len(task_groups) * question_count}"
                ),
                remote_inference_results_visibility="private",
                disable_remote_cache=True,
                disable_remote_inference=False,
                offload_execution=True,
                fresh=True,
                expected_parrot_api_key=os.environ["EXPECTED_PARROT_API_KEY"],
            ),
        )
        results = job.run(config=config)
        if results is None:
            raise ValueError("EDSL returned no results")
        task_columns = [f"scenario.task_id_{index:02d}" for index in range(1, question_count + 1)]
        answer_columns = [
            f"answer.promotion_choice_{index:02d}" for index in range(1, question_count + 1)
        ]
        rows = results.select(
            "scenario.agent_key",
            *task_columns,
            *answer_columns,
            "model.model",
            "model.inference_service",
        ).to_list()
        selections: tuple[
            Literal["alternative_1"],
            Literal["alternative_2"],
            Literal["no_choice"],
        ] = ("alternative_1", "alternative_2", "no_choice")
        output: list[SimulationChoiceResponse] = []
        for row in rows:
            agent_key = row[0]
            task_ids = row[1 : 1 + question_count]
            answers = row[1 + question_count : 1 + question_count * 2]
            model_id, service = row[-2:]
            if model_id != RESPONDENT_MODEL_ID or service != RESPONDENT_MODEL_SERVICE:
                raise ValueError("EDSL returned an unexpected respondent model")
            for task_id, answer in zip(task_ids, answers, strict=True):
                if (
                    not isinstance(answer, int)
                    or isinstance(answer, bool)
                    or answer not in (0, 1, 2)
                ):
                    raise ValueError("EDSL returned an invalid coded choice")
                output.append(
                    SimulationChoiceResponse(
                        task_id=task_id,
                        agent_key=agent_key,
                        repeat=repeat,
                        selected=selections[answer],
                    )
                )
        expected = len(task_groups) * question_count
        if len(output) != expected:
            raise ValueError("EDSL did not return every requested response")
        return output

    def persist() -> None:
        if save_checkpoint is not None:
            save_checkpoint(
                SimulationBatchCheckpoint(
                    request_digest=request_digest,
                    responses=tuple(completed.values()),
                )
            )

    def execute(task_groups: list[list[Any]], repeat: int) -> list[SimulationChoiceResponse]:
        task_groups = [
            group
            for group in task_groups
            if not all((task.task_id, repeat) in completed for task in group)
        ]
        if not task_groups:
            return []
        groups_per_job = 1
        output: list[SimulationChoiceResponse] = []
        for start in range(0, len(task_groups), groups_per_job):
            chunk = execute_chunk(task_groups[start : start + groups_per_job], repeat)
            output.extend(chunk)
            completed.update({(response.task_id, response.repeat): response for response in chunk})
            persist()
        return output

    by_agent: dict[str, list[Any]] = {persona.agent_key: [] for persona in request.personas}
    for task in request.plan.tasks:
        by_agent[task.agent_key].append(task)
    execute(list(by_agent.values()), 1)
    sentinel_ids = set(request.sentinel_task_ids)
    sentinel_groups = [
        [next(task for task in tasks if task.task_id in sentinel_ids)]
        for tasks in by_agent.values()
        if any(task.task_id in sentinel_ids for task in tasks)
    ]
    execute(sentinel_groups, 2)
    base = [completed[(task.task_id, 1)] for task in request.plan.tasks]
    sentinel = [completed[(task_id, 2)] for task_id in request.sentinel_task_ids]
    return SimulationResponseBatch(
        base_response_count=len(base),
        sentinel_response_count=len(sentinel),
        responses=tuple(base + sentinel),
    )
