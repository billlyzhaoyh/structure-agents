"""Generate a canonical design-only simulation run plan from a reviewed request."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pydantic import ValidationError

from structagent_api.contracts.simulation import (
    SimulationPlanRequest,
    canonical_contract_json,
    contract_digest,
)
from structagent_api.simulation.design import DesignGenerationError, generate_run_plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path, help="reviewed simulation plan request JSON")
    parser.add_argument("output", type=Path, help="new canonical run-plan JSON file")
    args = parser.parse_args()

    if args.output.exists():
        parser.error("output path already exists")

    try:
        request = SimulationPlanRequest.model_validate_json(
            args.request.read_text(encoding="utf-8")
        )
        plan = generate_run_plan(request)
        args.output.write_text(canonical_contract_json(plan) + "\n", encoding="utf-8")
    except (OSError, ValidationError):
        parser.error("unable to read a valid simulation plan request")
    except DesignGenerationError as error:
        parser.error(str(error))

    print(
        json.dumps(
            {
                "agent_count": plan.agent_count,
                "implementation_status": plan.implementation_status,
                "plan_digest": contract_digest(plan),
                "status": "succeeded",
                "task_count": plan.task_count,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
