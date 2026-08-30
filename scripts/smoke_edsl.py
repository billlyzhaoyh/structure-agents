"""Run three genuine EDSL responses for one reviewed task in Daytona."""

from __future__ import annotations

import argparse
import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from daytona import CreateSecretParams, Daytona
from structagent_api.contracts.simulation import SimulationPlanRequest
from structagent_api.simulation.design import generate_run_plan
from structagent_api.simulation.edsl import reviewed_edsl_smoke_request
from structagent_api.simulation.edsl_daytona_executor import (
    EXPECTED_PARROT_DOMAIN,
    EdslDaytonaError,
    execute_daytona_edsl_smoke,
)
from structagent_api.simulation_catalog import hm_promo_conjoint_v1


def _run_root(parent: Path) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    root = parent / f"{timestamp}-daytona-edsl-smoke"
    root.mkdir(parents=True, exist_ok=False)
    return root


def _reviewed_request() -> SimulationPlanRequest:
    study = hm_promo_conjoint_v1()
    target = study.population.sampling.target_agents
    return SimulationPlanRequest(
        study=study,
        agent_keys=tuple(f"synthetic-agent-{index:03d}" for index in range(target)),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-root", type=Path, default=Path(".artifacts/runs"))
    args = parser.parse_args()

    if not os.environ.get("DAYTONA_API_KEY") or not os.environ.get("EXPECTED_PARROT_API_KEY"):
        parser.error("DAYTONA_API_KEY and EXPECTED_PARROT_API_KEY are required")

    run_root = _run_root(args.runs_root)
    plan = generate_run_plan(_reviewed_request())
    request = reviewed_edsl_smoke_request(plan.tasks[0])
    client = Daytona()
    secret = None
    secret_name = f"structagent-ep-smoke-{uuid.uuid4().hex[:12]}"
    try:
        secret = client.secret.create(
            CreateSecretParams(
                name=secret_name,
                value=os.environ["EXPECTED_PARROT_API_KEY"],
                description="Temporary StructAgent EDSL integration smoke",
                hosts=[EXPECTED_PARROT_DOMAIN],
            )
        )
        report = execute_daytona_edsl_smoke(
            request,
            run_root / "result.json",
            secret_name,
            client_factory=lambda: client,
        )
    except EdslDaytonaError as error:
        parser.error(f"{error.code}: {error.detail}")
    finally:
        if secret is not None:
            try:
                client.secret.delete(secret.id)
            except Exception:
                parser.error("secret_cleanup: Daytona could not confirm temporary secret deletion")

    print(
        json.dumps(
            {
                "agent_source": report.result.agent_source,
                "choice_count": len(report.result.choices),
                "choices": [choice.selected for choice in report.result.choices],
                "cleanup_confirmed": report.cleanup_confirmed,
                "domain_allow_list": report.domain_allow_list,
                "edsl_version": report.result.edsl_version,
                "implementation_status": report.result.implementation_status,
                "respondent_model_id": report.result.respondent_model_id,
                "result_digest": report.result_digest,
                "run_root": str(run_root),
                "runtime_canary_confirmed": report.runtime_canary_confirmed,
                "secret_transport": report.secret_transport,
                "temporary_secret_deleted": True,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
