"""Refresh or verify the reviewed H&M simulation demo artifact cache."""

from __future__ import annotations

import argparse
import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from daytona import CreateSecretParams, Daytona
from structagent_api.contracts.simulation import (
    DatasetReference,
    DatasetStatus,
    SimulationPlanRequest,
    canonical_contract_json,
    contract_digest,
)
from structagent_api.materialization.hm_assets import REL_HM_ASSETS, verify_hm_assets
from structagent_api.simulation.batch import BatchPersona, SimulationBatchRequest
from structagent_api.simulation.cache import (
    SimulationCacheError,
    SimulationCacheIdentity,
    promote_simulation_result,
    verify_simulation_result,
)
from structagent_api.simulation.design import generate_run_plan
from structagent_api.simulation.edsl import EDSL_VERSION
from structagent_api.simulation.edsl_daytona_executor import (
    EXPECTED_PARROT_DOMAIN,
    EdslDaytonaError,
    execute_daytona_edsl_batch,
)
from structagent_api.simulation.estimate import (
    ESTIMATOR_VERSION,
    VALIDATION_VERSION,
    WORKER_VERSION,
    estimate_simulation_result,
)
from structagent_api.simulation.population import derive_hm_population
from structagent_api.simulation_catalog import hm_promo_conjoint_v1

STUDY_ID = "rel-hm/promo-conjoint-v1"


def refresh(cache_root: Path, data_root: Path, runs_root: Path) -> dict[str, object]:
    if not os.environ.get("DAYTONA_API_KEY") or not os.environ.get("EXPECTED_PARROT_API_KEY"):
        raise SimulationCacheError(
            "missing_credential", "simulation refresh credentials are required"
        )
    database_assets = tuple(asset for asset in REL_HM_ASSETS if "/db/" in asset.path)
    staged = verify_hm_assets(data_root, assets=database_assets)
    catalog_study = hm_promo_conjoint_v1()
    population = derive_hm_population(
        staged.dataset,
        cutoff=catalog_study.population.cutoff,
        seed=catalog_study.population.sampling.seed,
        target_agents=catalog_study.population.sampling.target_agents,
    )
    study = catalog_study.model_copy(
        update={
            "dataset": DatasetReference(
                status=DatasetStatus.APPROVED_SNAPSHOT,
                revision=population.dataset_revision,
                manifest_digest=population.dataset_manifest_digest,
            )
        }
    )
    plan = generate_run_plan(
        SimulationPlanRequest(
            study=study,
            agent_keys=tuple(persona.agent_key for persona in population.personas),
        )
    )
    sentinel_count = max(1, round(plan.task_count * study.validation.sentinel_fraction))
    sentinel_task_ids = tuple(task.task_id for task in plan.tasks[::10][:sentinel_count])
    request = SimulationBatchRequest(
        plan=plan,
        personas=tuple(
            BatchPersona(agent_key=persona.agent_key, traits=persona.traits)
            for persona in population.personas
        ),
        sentinel_task_ids=sentinel_task_ids,
    )
    checkpoint_root = runs_root / "simulation-demo-checkpoints"
    checkpoint_root.mkdir(parents=True, exist_ok=True)
    checkpoint_path = checkpoint_root / f"{contract_digest(request).removeprefix('sha256:')}.json"

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_root = runs_root / f"{timestamp}-simulation-demo-refresh"
    run_root.mkdir(parents=True, exist_ok=False)
    (run_root / "population.json").write_text(
        canonical_contract_json(population) + "\n", encoding="utf-8"
    )
    (run_root / "plan.json").write_text(canonical_contract_json(plan) + "\n", encoding="utf-8")

    client = Daytona()
    secret = None
    secret_name = f"structagent-ep-demo-{uuid.uuid4().hex[:12]}"
    try:
        secret = client.secret.create(
            CreateSecretParams(
                name=secret_name,
                value=os.environ["EXPECTED_PARROT_API_KEY"],
                description="Temporary StructAgent full simulation run",
                hosts=[EXPECTED_PARROT_DOMAIN],
            )
        )
        report = execute_daytona_edsl_batch(
            request,
            run_root / "responses.json",
            secret_name,
            checkpoint_path=checkpoint_path,
            client_factory=lambda: client,
        )
    finally:
        if secret is not None:
            client.secret.delete(secret.id)

    result = estimate_simulation_result(study, plan, population, report.batch)
    identity = SimulationCacheIdentity(
        study_digest=result.provenance.study_digest,
        dataset_revision=result.provenance.dataset_revision,
        dataset_manifest_digest=result.provenance.dataset_manifest_digest,
        trait_query_digest=result.provenance.trait_query_digest,
        prompt_template_digest=result.provenance.prompt_template_digest,
        respondent_model_id=result.provenance.respondent_model_id,
        respondent_model_version=result.provenance.respondent_model_version,
        edsl_version=EDSL_VERSION,
        estimator_version=ESTIMATOR_VERSION,
        validation_version=VALIDATION_VERSION,
        worker_version=WORKER_VERSION,
        certification_digest=result.provenance.certification_digest,
        random_seed=result.provenance.random_seed,
    )
    artifact = promote_simulation_result(cache_root, result, identity)
    checkpoint_path.unlink(missing_ok=True)
    return {
        "base_response_count": report.batch.base_response_count,
        "cache_key": artifact.manifest.cache_key,
        "cleanup_confirmed": report.cleanup_confirmed,
        "recommendation_status": result.recommendation_status,
        "result_digest": artifact.manifest.result_digest,
        "run_id": result.run_id,
        "sentinel_response_count": report.batch.sentinel_response_count,
        "temporary_secret_deleted": True,
    }


def verify(cache_root: Path) -> dict[str, object]:
    artifact = verify_simulation_result(cache_root, STUDY_ID)
    return {
        "cache_key": artifact.manifest.cache_key,
        "recommendation_status": artifact.result.recommendation_status,
        "result_digest": artifact.manifest.result_digest,
        "run_id": artifact.result.run_id,
        "validation_gate_count": len(artifact.result.validation),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("refresh", "verify"))
    parser.add_argument("--cache-root", type=Path, default=Path(".artifacts/simulation-results"))
    parser.add_argument("--data-root", type=Path, default=Path(".artifacts/rel-hm"))
    parser.add_argument("--runs-root", type=Path, default=Path(".artifacts/runs"))
    args = parser.parse_args()
    try:
        output = (
            refresh(args.cache_root, args.data_root, args.runs_root)
            if args.action == "refresh"
            else verify(args.cache_root)
        )
    except (SimulationCacheError, EdslDaytonaError, ValueError) as error:
        code = getattr(error, "code", "simulation_demo")
        parser.error(f"{code}: simulation demo artifact operation failed")
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
