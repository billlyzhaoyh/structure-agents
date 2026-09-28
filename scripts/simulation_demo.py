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
    SimulationRunPlan,
    SimulationStudyArtifact,
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
    OPENAI_DOMAIN,
    EdslDaytonaError,
    execute_daytona_edsl_batch,
)
from structagent_api.simulation.estimate import (
    ESTIMATOR_VERSION,
    VALIDATION_VERSION,
    WORKER_VERSION,
    estimate_simulation_result,
)
from structagent_api.simulation.population import (
    SimulationPopulationPackage,
    derive_hm_population,
)
from structagent_api.simulation_catalog import hm_promo_conjoint_v1

STUDY_ID = "rel-hm/promo-conjoint-v1"


def _require_credentials() -> None:
    if not os.environ.get("DAYTONA_API_KEY") or not os.environ.get("OPENAI_API_KEY"):
        raise SimulationCacheError(
            "missing_credential", "simulation refresh credentials are required"
        )


def _derive(
    data_root: Path,
) -> tuple[SimulationStudyArtifact, SimulationRunPlan, SimulationPopulationPackage]:
    """Derive the approved population and the full reviewed design."""

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
    return study, plan, population


def _batch_request(
    study: SimulationStudyArtifact,
    plan: SimulationRunPlan,
    population: SimulationPopulationPackage,
) -> SimulationBatchRequest:
    sentinel_count = max(1, round(plan.task_count * study.validation.sentinel_fraction))
    sentinel_task_ids = tuple(task.task_id for task in plan.tasks[::10][:sentinel_count])
    return SimulationBatchRequest(
        plan=plan,
        personas=tuple(
            BatchPersona(agent_key=persona.agent_key, traits=persona.traits)
            for persona in population.personas
        ),
        sentinel_task_ids=sentinel_task_ids,
    )


def refresh(cache_root: Path, data_root: Path, runs_root: Path) -> dict[str, object]:
    _require_credentials()
    study, plan, population = _derive(data_root)
    request = _batch_request(study, plan, population)
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
    secret_name = f"structagent-oai-demo-{uuid.uuid4().hex[:12]}"
    try:
        secret = client.secret.create(
            CreateSecretParams(
                name=secret_name,
                value=os.environ["OPENAI_API_KEY"],
                description="Temporary StructAgent full simulation run",
                hosts=[OPENAI_DOMAIN],
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


def pilot(data_root: Path, runs_root: Path, persona_limit: int) -> dict[str, object]:
    """Prove the Daytona and respondent-model boundary on a slice of the reviewed design.

    The slice is a genuine sub-plan of the approved study, so prompts, personas, and
    task profiles are the real ones. It is never promoted to the artifact cache: a
    partial population cannot support a population-level estimate.
    """

    _require_credentials()
    study, plan, population = _derive(data_root)
    if not 1 <= persona_limit <= plan.agent_count:
        raise SimulationCacheError("persona_limit", "the pilot persona limit is out of range")

    personas = population.personas[:persona_limit]
    selected = {persona.agent_key for persona in personas}
    tasks = tuple(task for task in plan.tasks if task.agent_key in selected)
    sliced_plan = plan.model_copy(
        update={
            "agent_count": len(selected),
            "task_count": len(tasks),
            "tasks": tasks,
        }
    )
    sliced_population = population.model_copy(update={"personas": personas})
    request = _batch_request(study, sliced_plan, sliced_population)

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_root = runs_root / f"{timestamp}-simulation-demo-pilot"
    run_root.mkdir(parents=True, exist_ok=False)
    (run_root / "plan.json").write_text(
        canonical_contract_json(sliced_plan) + "\n", encoding="utf-8"
    )

    client = Daytona()
    secret = None
    secret_name = f"structagent-oai-pilot-{uuid.uuid4().hex[:12]}"
    try:
        secret = client.secret.create(
            CreateSecretParams(
                name=secret_name,
                value=os.environ["OPENAI_API_KEY"],
                description="Temporary StructAgent simulation pilot",
                hosts=[OPENAI_DOMAIN],
            )
        )
        report = execute_daytona_edsl_batch(
            request,
            run_root / "responses.json",
            secret_name,
            client_factory=lambda: client,
        )
    finally:
        if secret is not None:
            client.secret.delete(secret.id)

    selections: dict[str, int] = {}
    for response in report.batch.responses:
        selections[response.selected] = selections.get(response.selected, 0) + 1
    return {
        "agent_count": sliced_plan.agent_count,
        "base_response_count": report.batch.base_response_count,
        "choice_distribution": dict(sorted(selections.items())),
        "cleanup_confirmed": report.cleanup_confirmed,
        "promoted_to_cache": False,
        "respondent_model_id": report.batch.respondent_model_id,
        "result_digest": report.result_digest,
        "runtime_canary_confirmed": report.runtime_canary_confirmed,
        "sentinel_response_count": report.batch.sentinel_response_count,
        "task_count": sliced_plan.task_count,
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
    parser.add_argument("action", choices=("refresh", "pilot", "verify"))
    parser.add_argument("--cache-root", type=Path, default=Path(".artifacts/simulation-results"))
    parser.add_argument("--data-root", type=Path, default=Path(".artifacts/rel-hm"))
    parser.add_argument("--runs-root", type=Path, default=Path(".artifacts/runs"))
    parser.add_argument("--persona-limit", type=int, default=25)
    args = parser.parse_args()
    try:
        if args.action == "refresh":
            output = refresh(args.cache_root, args.data_root, args.runs_root)
        elif args.action == "pilot":
            output = pilot(args.data_root, args.runs_root, args.persona_limit)
        else:
            output = verify(args.cache_root)
    except (SimulationCacheError, EdslDaytonaError, ValueError) as error:
        code = getattr(error, "code", "simulation_demo")
        detail = getattr(error, "detail", "simulation demo artifact operation failed")
        parser.error(f"{code}: {detail}")
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
