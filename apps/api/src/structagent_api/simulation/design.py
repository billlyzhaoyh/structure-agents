"""Compile a reviewed discrete-choice study into a deterministic run plan."""

from __future__ import annotations

import random

from structagent_api.contracts.simulation import (
    ChoiceAlternative,
    ChoiceTask,
    DiscreteChoiceStudySpec,
    ProfileLevel,
    SimulationPlanRequest,
    SimulationRunPlan,
    contract_digest,
)

_MAX_DISTINCT_PROFILE_ATTEMPTS = 1_000
_ORDER_SEED_MASK = 0xA5A5A5A5


class DesignGenerationError(Exception):
    """A reviewed study cannot be compiled into a valid choice design."""


def _normalized_control(study: DiscreteChoiceStudySpec) -> tuple[ProfileLevel, ...] | None:
    if study.control_profile is None:
        return None
    levels_by_attribute = {item.attribute: item.level for item in study.control_profile}
    return tuple(
        ProfileLevel(attribute=attribute.name, level=levels_by_attribute[attribute.name])
        for attribute in study.attributes
    )


def _draw_profile(study: DiscreteChoiceStudySpec, rng: random.Random) -> tuple[ProfileLevel, ...]:
    selected_levels: dict[str, str] = {}
    profile: list[ProfileLevel] = []
    for attribute in study.attributes:
        applicability = attribute.applicability
        if applicability is not None and (
            selected_levels[applicability.controlling_attribute] not in applicability.allowed_levels
        ):
            level = attribute.baseline_level
        else:
            level = rng.choice(attribute.levels)
        selected_levels[attribute.name] = level
        profile.append(ProfileLevel(attribute=attribute.name, level=level))
    return tuple(profile)


def _draw_distinct_profile(
    study: DiscreteChoiceStudySpec,
    rng: random.Random,
    excluded: tuple[ProfileLevel, ...],
) -> tuple[ProfileLevel, ...]:
    for _ in range(_MAX_DISTINCT_PROFILE_ATTEMPTS):
        candidate = _draw_profile(study, rng)
        if candidate != excluded:
            return candidate
    raise DesignGenerationError("study does not yield two distinct applicable profiles")


def _ordered_alternatives(
    first: tuple[ProfileLevel, ...],
    second: tuple[ProfileLevel, ...],
    control: tuple[ProfileLevel, ...] | None,
    order_rng: random.Random,
) -> tuple[ChoiceAlternative, ChoiceAlternative]:
    profiles = [first, second]
    order_rng.shuffle(profiles)
    return (
        ChoiceAlternative(
            position=1,
            profile=profiles[0],
            is_control=control is not None and profiles[0] == control,
        ),
        ChoiceAlternative(
            position=2,
            profile=profiles[1],
            is_control=control is not None and profiles[1] == control,
        ),
    )


def generate_run_plan(request: SimulationPlanRequest) -> SimulationRunPlan:
    """Generate an exact, reproducible task inventory without executing a model."""

    study = request.study.study
    seed = request.study.population.sampling.seed
    profile_rng = random.Random(seed)
    order_rng = random.Random(seed ^ _ORDER_SEED_MASK)
    control = _normalized_control(study)
    tasks: list[ChoiceTask] = []

    for agent_index, agent_key in enumerate(request.agent_keys, start=1):
        for sequence in range(1, study.tasks_per_agent + 1):
            if sequence == 1 and control is not None:
                first = control
            else:
                first = _draw_profile(study, profile_rng)
            second = _draw_distinct_profile(study, profile_rng, first)
            alternatives = _ordered_alternatives(first, second, control, order_rng)
            tasks.append(
                ChoiceTask(
                    task_id=f"task-{agent_index:04d}-{sequence:02d}",
                    agent_key=agent_key,
                    sequence=sequence,
                    alternatives=alternatives,
                )
            )

    return SimulationRunPlan(
        study_artifact_id=request.study.artifact_id,
        study_digest=contract_digest(request.study),
        random_seed=seed,
        agent_count=len(request.agent_keys),
        tasks_per_agent=study.tasks_per_agent,
        task_count=len(tasks),
        tasks=tuple(tasks),
    )
