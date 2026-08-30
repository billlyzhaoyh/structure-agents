from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError
from structagent_api.contracts.simulation import ChoiceTask, SimulationPlanRequest, TraitName
from structagent_api.simulation import edsl_runner
from structagent_api.simulation.design import generate_run_plan
from structagent_api.simulation.edsl import (
    AgentTrait,
    EdslChoiceRecord,
    EdslSmokeRequest,
    EdslSmokeResult,
    compile_edsl_interview,
    reviewed_edsl_smoke_request,
)
from structagent_api.simulation.edsl_runner import main as runner_main
from structagent_api.simulation_catalog import hm_promo_conjoint_v1


def first_reviewed_task() -> ChoiceTask:
    study = hm_promo_conjoint_v1()
    request = SimulationPlanRequest(
        study=study,
        agent_keys=tuple(f"synthetic-agent-{index:03d}" for index in range(400)),
    )
    return generate_run_plan(request).tasks[0]


def test_reviewed_task_compiles_to_strict_edsl_multiple_choice() -> None:
    request = reviewed_edsl_smoke_request(first_reviewed_task())

    spec = compile_edsl_interview(request)

    assert request.repeats == 3
    assert request.agent_source == "synthetic_placeholder"
    assert request.respondent_model_id == "gpt-5.6-luna"
    assert request.respondent_model_service == "openai"
    assert {trait.name for trait in request.traits} == set(TraitName)
    assert spec.question_options == ("{{ option_1 }}", "{{ option_2 }}", "No purchase")
    assert spec.scenario["task_id"] == "task-0001-01"
    assert "Member Exclusive Price" in spec.scenario["option_1"]
    assert "Discount Form: None" in spec.scenario["option_2"]
    rendered_templates = spec.question_text + " ".join(spec.question_options)
    assert all(f"{{{{ {field} }}}}" in rendered_templates for field in spec.scenario)
    assert "synthetic-agent" not in spec.agent_traits


def test_smoke_request_rejects_missing_traits_and_misaligned_agent() -> None:
    task = first_reviewed_task()

    with pytest.raises(ValidationError, match="every approved aggregate trait"):
        EdslSmokeRequest(
            agent_key=task.agent_key,
            traits=(AgentTrait(name=TraitName.AGE_BAND, value="unknown"),),
            task=task,
        )

    with pytest.raises(ValidationError, match="agent key does not match"):
        EdslSmokeRequest(
            agent_key="different-agent",
            traits=tuple(AgentTrait(name=name, value="unknown") for name in TraitName),
            task=task,
        )


def test_smoke_result_requires_three_ordered_repeats() -> None:
    choices = (
        EdslChoiceRecord(repeat=1, selected="alternative_1"),
        EdslChoiceRecord(repeat=2, selected="no_choice"),
        EdslChoiceRecord(repeat=3, selected="alternative_2"),
    )

    result = EdslSmokeResult(task_id="task-0001-01", choices=choices)

    assert [choice.selected for choice in result.choices] == [
        "alternative_1",
        "no_choice",
        "alternative_2",
    ]

    with pytest.raises(ValidationError, match="three ordered repeats"):
        EdslSmokeResult(
            task_id="task-0001-01",
            choices=(choices[1], choices[0], choices[2]),
        )


def test_runner_sanitizes_provider_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "result.json"
    request = reviewed_edsl_smoke_request(first_reviewed_task())
    request_path.write_text(request.model_dump_json(), encoding="utf-8")

    def fail_without_leaking(request: EdslSmokeRequest) -> EdslSmokeResult:
        raise RuntimeError("signed URL and private provider trace")

    monkeypatch.setattr(edsl_runner, "run_edsl_smoke", fail_without_leaking)
    monkeypatch.setattr(sys, "argv", ["edsl-runner", str(request_path), str(output_path)])

    assert runner_main() == 1

    evidence = capsys.readouterr().out
    assert json.loads(evidence) == {"code": "edsl_execution", "status": "failed"}
    assert "signed URL" not in evidence
    assert "private provider trace" not in evidence
    assert not output_path.exists()
