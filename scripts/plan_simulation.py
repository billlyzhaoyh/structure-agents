"""Generate the reviewed default simulation design locally or in Daytona."""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from structagent_api.contracts.simulation import (
    SimulationPlanRequest,
    canonical_contract_json,
    contract_digest,
)
from structagent_api.simulation.daytona_executor import (
    SimulationDaytonaError,
    execute_daytona_simulation_plan,
)
from structagent_api.simulation.design import generate_run_plan
from structagent_api.simulation_catalog import hm_promo_conjoint_v1


def _request() -> SimulationPlanRequest:
    study = hm_promo_conjoint_v1()
    target = study.population.sampling.target_agents
    return SimulationPlanRequest(
        study=study,
        agent_keys=tuple(f"synthetic-agent-{index:03d}" for index in range(target)),
    )


def _run_root(parent: Path, mode: str) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    root = parent / f"{timestamp}-{mode}"
    root.mkdir(parents=True, exist_ok=False)
    return root


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("local", "daytona"))
    parser.add_argument("--runs-root", type=Path, default=Path(".artifacts/runs"))
    args = parser.parse_args()

    request = _request()
    root = _run_root(args.runs_root, f"{args.mode}-simulation-design")
    output_path = root / "plan.json"
    try:
        if args.mode == "local":
            plan = generate_run_plan(request)
            output_path.write_text(canonical_contract_json(plan) + "\n", encoding="utf-8")
            cleanup_confirmed = None
            network_block_all = None
            runtime_canary_confirmed = None
        else:
            if not os.environ.get("DAYTONA_API_KEY"):
                raise SimulationDaytonaError(
                    "missing_credential", "DAYTONA_API_KEY is required in the ignored environment"
                )
            report = execute_daytona_simulation_plan(request, output_path)
            plan = report.plan
            cleanup_confirmed = report.cleanup_confirmed
            network_block_all = report.network_block_all
            runtime_canary_confirmed = report.runtime_canary_confirmed
    except SimulationDaytonaError as error:
        parser.error(f"{error.code}: {error.detail}")

    print(
        json.dumps(
            {
                "agent_count": plan.agent_count,
                "agent_source": "synthetic_placeholder",
                "cleanup_confirmed": cleanup_confirmed,
                "dataset_status": request.study.dataset.status,
                "implementation_status": plan.implementation_status,
                "mode": args.mode,
                "network_block_all": network_block_all,
                "plan_digest": contract_digest(plan),
                "run_root": str(root),
                "runtime_canary_confirmed": runtime_canary_confirmed,
                "task_count": plan.task_count,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
