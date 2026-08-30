"""Compile one reviewed choice task for genuine EDSL respondent-model execution."""

from __future__ import annotations

from typing import Any, Final, Literal, Self

from pydantic import Field, field_validator, model_validator

from structagent_api.contracts.models import StrictModel
from structagent_api.contracts.simulation import (
    ChoiceAlternative,
    ChoiceTask,
    TraitName,
)

EDSL_VERSION: Final[Literal["1.0.8"]] = "1.0.8"
RESPONDENT_MODEL_ID: Final[Literal["gpt-4.1-mini-2025-04-14"]] = "gpt-4.1-mini-2025-04-14"
RESPONDENT_MODEL_SERVICE: Final[Literal["openai"]] = "openai"
REPEAT_COUNT: Final[Literal[3]] = 3


class AgentTrait(StrictModel):
    """One approved aggregate trait supplied to a synthetic respondent."""

    name: TraitName
    value: str = Field(min_length=1, max_length=100)


class EdslSmokeRequest(StrictModel):
    """One reviewed task and placeholder persona used to prove the live boundary."""

    schema_version: Literal["1"] = "1"
    implementation_status: Literal["integration_smoke"] = "integration_smoke"
    agent_source: Literal["synthetic_placeholder"] = "synthetic_placeholder"
    agent_key: str = Field(min_length=1, max_length=200)
    traits: tuple[AgentTrait, ...]
    task: ChoiceTask
    respondent_model_id: Literal["gpt-4.1-mini-2025-04-14"] = RESPONDENT_MODEL_ID
    respondent_model_service: Literal["openai"] = RESPONDENT_MODEL_SERVICE
    edsl_version: Literal["1.0.8"] = EDSL_VERSION
    repeats: Literal[3] = REPEAT_COUNT

    @model_validator(mode="after")
    def persona_and_task_are_aligned(self) -> Self:
        names = [trait.name for trait in self.traits]
        if len(names) != len(set(names)):
            raise ValueError("respondent traits must be unique")
        if set(names) != set(TraitName):
            raise ValueError("integration smoke must supply every approved aggregate trait")
        if self.task.agent_key != self.agent_key:
            raise ValueError("respondent agent key does not match the choice task")
        return self


class EdslInterviewSpec(StrictModel):
    """Pure-data representation compiled into EDSL objects inside Daytona."""

    question_name: Literal["promotion_choice"] = "promotion_choice"
    question_text: str
    question_options: tuple[str, str, str]
    scenario: dict[str, str]
    agent_instruction: str
    agent_traits: dict[str, str]


class EdslChoiceRecord(StrictModel):
    """One coded response with raw prompts and provider output removed."""

    repeat: int = Field(ge=1, le=REPEAT_COUNT)
    selected: Literal["alternative_1", "alternative_2", "no_choice"]


class EdslSmokeResult(StrictModel):
    """Canonical evidence for a real but non-study EDSL integration smoke."""

    schema_version: Literal["1"] = "1"
    implementation_status: Literal["integration_smoke"] = "integration_smoke"
    evidence_kind: Literal["simulated"] = "simulated"
    agent_source: Literal["synthetic_placeholder"] = "synthetic_placeholder"
    task_id: str = Field(min_length=1)
    respondent_model_id: Literal["gpt-4.1-mini-2025-04-14"] = RESPONDENT_MODEL_ID
    respondent_model_service: Literal["openai"] = RESPONDENT_MODEL_SERVICE
    edsl_version: Literal["1.0.8"] = EDSL_VERSION
    choices: tuple[EdslChoiceRecord, EdslChoiceRecord, EdslChoiceRecord]

    @field_validator("choices")
    @classmethod
    def repeats_are_complete(
        cls,
        choices: tuple[EdslChoiceRecord, EdslChoiceRecord, EdslChoiceRecord],
    ) -> tuple[EdslChoiceRecord, EdslChoiceRecord, EdslChoiceRecord]:
        if tuple(choice.repeat for choice in choices) != (1, 2, 3):
            raise ValueError("EDSL smoke choices must contain three ordered repeats")
        return choices


def _render_alternative(alternative: ChoiceAlternative) -> str:
    return "; ".join(
        f"{item.attribute.replace('_', ' ').title()}: "
        f"{item.level.replace('_percent', '%').replace('_', ' ').title()}"
        for item in alternative.profile
    )


def compile_edsl_interview(request: EdslSmokeRequest) -> EdslInterviewSpec:
    """Compile only reviewed fields into one strict multiple-choice interview."""

    return EdslInterviewSpec(
        question_text=(
            "For synthetic integration task {{ task_id }}, compare the two fashion purchase "
            "offers below. Choose exactly one option."
        ),
        question_options=("{{ option_1 }}", "{{ option_2 }}", "No purchase"),
        scenario={
            "task_id": request.task.task_id,
            "option_1": _render_alternative(request.task.alternatives[0]),
            "option_2": _render_alternative(request.task.alternatives[1]),
        },
        agent_instruction=(
            "You are a synthetic survey respondent conditioned only on the aggregate retail "
            "traits supplied to you. This is a hypothetical fashion purchase. Choose exactly "
            "one offered option and do not add an explanation."
        ),
        agent_traits={trait.name.value: trait.value for trait in request.traits},
    )


def _choice_record(row: list[Any]) -> EdslChoiceRecord:
    if len(row) != 4:
        raise ValueError("EDSL returned an unexpected result row")
    answer, model_id, service, iteration = row
    if model_id != RESPONDENT_MODEL_ID or service != RESPONDENT_MODEL_SERVICE:
        raise ValueError("EDSL returned a response from an unexpected model")
    if not isinstance(answer, int) or isinstance(answer, bool) or answer not in (0, 1, 2):
        raise ValueError("EDSL returned an invalid coded choice")
    if not isinstance(iteration, int) or isinstance(iteration, bool):
        raise ValueError("EDSL returned an invalid repeat index")
    selections: tuple[Literal["alternative_1"], Literal["alternative_2"], Literal["no_choice"]] = (
        "alternative_1",
        "alternative_2",
        "no_choice",
    )
    selected = selections[answer]
    return EdslChoiceRecord(repeat=iteration + 1, selected=selected)


def run_edsl_smoke(request: EdslSmokeRequest) -> EdslSmokeResult:
    """Execute three real EDSL interviews; this function runs only inside Daytona."""

    import os

    import edsl  # type: ignore[import-untyped]
    from edsl import (
        Agent,
        Model,
        QuestionMultipleChoice,
        Scenario,
        Survey,
    )
    from edsl.jobs.data_structures import (  # type: ignore[import-untyped]
        RunConfig,
        RunEnvironment,
        RunParameters,
    )

    if edsl.__version__ != EDSL_VERSION:
        raise ValueError("the EDSL runtime version is not pinned")

    spec = compile_edsl_interview(request)
    question = QuestionMultipleChoice(
        question_name=spec.question_name,
        question_text=spec.question_text,
        question_options=list(spec.question_options),
        include_comment=False,
        use_code=True,
    )
    agent = Agent(traits=spec.agent_traits, instruction=spec.agent_instruction)
    scenario = Scenario(spec.scenario)
    model = Model(
        RESPONDENT_MODEL_ID,
        service_name=RESPONDENT_MODEL_SERVICE,
        temperature=0.5,
        max_tokens=16,
    )
    job = Survey([question]).by(agent).by(scenario).by(model)
    config = RunConfig(
        environment=RunEnvironment(),
        parameters=RunParameters(
            n=request.repeats,
            progress_bar=False,
            stop_on_exception=True,
            check_api_keys=True,
            verbose=False,
            print_exceptions=False,
            remote_cache_description="StructAgent synthetic EDSL integration smoke",
            remote_inference_description="StructAgent synthetic EDSL integration smoke",
            remote_inference_results_visibility="private",
            disable_remote_cache=False,
            disable_remote_inference=False,
            offload_execution=True,
            fresh=True,
            expected_parrot_api_key=os.environ["EXPECTED_PARROT_API_KEY"],
        ),
    )
    results = job.run(config=config)
    if results is None:
        raise ValueError("EDSL returned no results")
    rows = results.select(
        "answer.promotion_choice",
        "model.model",
        "model.inference_service",
        "iteration.iteration",
    ).to_list()
    choices = tuple(sorted((_choice_record(row) for row in rows), key=lambda item: item.repeat))
    if len(choices) != REPEAT_COUNT:
        raise ValueError("EDSL did not return every requested repeat")
    return EdslSmokeResult(
        task_id=request.task.task_id,
        choices=(choices[0], choices[1], choices[2]),
    )


def reviewed_edsl_smoke_request(task: ChoiceTask) -> EdslSmokeRequest:
    """Build an explicitly placeholder persona for integration testing only."""

    return EdslSmokeRequest(
        agent_key=task.agent_key,
        traits=tuple(AgentTrait(name=name, value="unknown") for name in TraitName),
        task=task,
    )
