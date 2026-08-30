from __future__ import annotations

import pytest
from pydantic import ValidationError
from structagent_api.simulation.batch import (
    SimulationBatchCheckpoint,
    SimulationChoiceResponse,
)


def test_checkpoint_rejects_duplicate_task_repeat_pairs() -> None:
    response = SimulationChoiceResponse(
        task_id="task-1",
        agent_key="agent-1",
        repeat=1,
        selected="alternative_1",
    )

    with pytest.raises(ValidationError, match="checkpoint responses must be unique"):
        SimulationBatchCheckpoint(
            request_digest="sha256:" + "a" * 64,
            responses=(response, response),
        )


def test_checkpoint_accepts_distinct_repeats_for_a_sentinel() -> None:
    checkpoint = SimulationBatchCheckpoint(
        request_digest="sha256:" + "a" * 64,
        responses=(
            SimulationChoiceResponse(
                task_id="task-1",
                agent_key="agent-1",
                repeat=1,
                selected="alternative_1",
            ),
            SimulationChoiceResponse(
                task_id="task-1",
                agent_key="agent-1",
                repeat=2,
                selected="alternative_2",
            ),
        ),
    )

    assert len(checkpoint.responses) == 2
