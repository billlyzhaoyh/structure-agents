from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from structagent_api.contracts.simulation import (
    ChoiceAlternative,
    SimulationPlanRequest,
    SimulationRunPlan,
    canonical_contract_json,
)
from structagent_api.simulation.design import generate_run_plan
from structagent_api.simulation.runner import main
from structagent_api.simulation_catalog import hm_promo_conjoint_v1


def reviewed_request() -> SimulationPlanRequest:
    return SimulationPlanRequest(
        study=hm_promo_conjoint_v1(),
        agent_keys=tuple(f"agent-{index:03d}" for index in range(400)),
    )


def profile_levels(alternative: ChoiceAlternative) -> dict[str, str]:
    return {item.attribute: item.level for item in alternative.profile}


def test_design_is_reproducible_and_has_an_exact_inventory() -> None:
    request = reviewed_request()

    first = generate_run_plan(request)
    second = generate_run_plan(request)

    assert first == second
    assert first.implementation_status == "design_only"
    assert first.agent_count == 400
    assert first.tasks_per_agent == 10
    assert first.task_count == 4_000
    assert first.tasks[0].task_id == "task-0001-01"
    assert first.tasks[-1].task_id == "task-0400-10"
    assert profile_levels(first.tasks[0].alternatives[0]) == {
        "discount_form": "member_exclusive_price",
        "depth": "30_percent",
        "threshold": "none",
        "urgency": "weekend_only",
        "framing": "member_perk",
    }
    assert first.tasks[0].alternatives[1].is_control is True
    assert canonical_contract_json(first) == canonical_contract_json(second)


def test_each_agent_gets_control_and_every_task_has_valid_choice_options() -> None:
    plan = generate_run_plan(reviewed_request())
    first_tasks = [task for task in plan.tasks if task.sequence == 1]

    assert len(first_tasks) == 400
    assert {alternative.position for task in plan.tasks for alternative in task.alternatives} == {
        1,
        2,
    }
    assert all(task.include_no_choice for task in plan.tasks)
    assert all(task.alternatives[0].profile != task.alternatives[1].profile for task in plan.tasks)
    assert all(
        sum(alternative.is_control for alternative in task.alternatives) == 1
        for task in first_tasks
    )
    assert {
        next(alt.position for alt in task.alternatives if alt.is_control) for task in first_tasks
    } == {
        1,
        2,
    }


def test_generated_profiles_apply_dependent_attribute_baselines() -> None:
    plan = generate_run_plan(reviewed_request())

    for task in plan.tasks:
        for alternative in task.alternatives:
            levels = profile_levels(alternative)
            if levels["discount_form"] not in {"percent_off", "member_exclusive_price"}:
                assert levels["depth"] == "0_percent"
            if levels["discount_form"] != "bogo":
                assert levels["threshold"] == "none"


def test_worker_writes_canonical_plan_and_sanitized_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "plan.json"
    request_path.write_text(canonical_contract_json(reviewed_request()), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["simulation-runner", str(request_path), str(output_path)])

    assert main() == 0

    plan = SimulationRunPlan.model_validate_json(output_path.read_text(encoding="utf-8"))
    evidence = json.loads(capsys.readouterr().out)
    assert output_path.read_text(encoding="utf-8") == canonical_contract_json(plan) + "\n"
    assert evidence == {
        "agent_count": 400,
        "implementation_status": "design_only",
        "plan_digest": evidence["plan_digest"],
        "status": "succeeded",
        "task_count": 4_000,
    }
    assert evidence["plan_digest"].startswith("sha256:")
