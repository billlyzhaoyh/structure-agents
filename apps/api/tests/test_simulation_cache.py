from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from structagent_api.contracts.simulation import (
    GateStatus,
    ProfileLevel,
    RankedAlternative,
    RecommendationStatus,
    RunProvenance,
    RunValidationGate,
    SimulationRunResult,
    ValidationGateResult,
)
from structagent_api.simulation.cache import (
    SimulationCacheError,
    SimulationCacheIdentity,
    promote_simulation_result,
    verify_simulation_result,
)


def identity() -> SimulationCacheIdentity:
    return SimulationCacheIdentity(
        study_digest="sha256:" + "1" * 64,
        dataset_revision="revision",
        dataset_manifest_digest="sha256:" + "2" * 64,
        trait_query_digest="sha256:" + "3" * 64,
        prompt_template_digest="sha256:" + "4" * 64,
        respondent_model_id="model",
        respondent_model_version="model-version",
        edsl_version="1.0.8",
        estimator_version="1",
        validation_version="1",
        worker_version="1",
        certification_digest="sha256:" + "5" * 64,
        random_seed=17,
    )


def result() -> SimulationRunResult:
    item = identity()
    return SimulationRunResult(
        run_id="simulation-run-1",
        study_artifact_id="rel-hm/promo-conjoint-v1",
        recommendation_status=RecommendationStatus.RECOMMENDED,
        validation=(
            ValidationGateResult(
                gate=RunValidationGate.DESIGN_INVARIANTS,
                status=GateStatus.PASSED,
                hard_gate=True,
                summary="The reviewed design passed.",
            ),
        ),
        rankings=(
            RankedAlternative(
                rank=1,
                profile=(ProfileLevel(attribute="discount_form", level="percent_off"),),
                rank_stability=0.9,
            ),
        ),
        limitations=("This is simulated screening evidence, not measured business impact.",),
        provenance=RunProvenance(
            dataset_revision=item.dataset_revision,
            dataset_manifest_digest=item.dataset_manifest_digest,
            study_digest=item.study_digest,
            trait_query_digest=item.trait_query_digest,
            prompt_template_digest=item.prompt_template_digest,
            certification_digest=item.certification_digest,
            respondent_model_id=item.respondent_model_id,
            respondent_model_version=item.respondent_model_version,
            edsl_version=item.edsl_version,
            random_seed=item.random_seed,
        ),
    )


def test_promote_and_verify_are_canonical_idempotent_and_network_free(tmp_path: Path) -> None:
    created_at = datetime(2026, 8, 30, tzinfo=UTC)

    first = promote_simulation_result(tmp_path, result(), identity(), created_at=created_at)
    second = promote_simulation_result(tmp_path, result(), identity(), created_at=created_at)
    verified = verify_simulation_result(tmp_path, "rel-hm/promo-conjoint-v1")

    assert first == second == verified
    assert verified.manifest.result_digest.startswith("sha256:")
    assert len([path for path in tmp_path.iterdir() if path.is_dir()]) == 1
    assert (
        json.loads(next(tmp_path.glob("*.latest.json")).read_text())["cache_key"]
        == verified.manifest.cache_key
    )


def test_verify_rejects_tampered_result(tmp_path: Path) -> None:
    artifact = promote_simulation_result(tmp_path, result(), identity())
    result_path = tmp_path / artifact.manifest.cache_key.removeprefix("sha256:") / "result.json"
    result_path.write_text(result_path.read_text().replace("simulation-run-1", "tampered-run"))

    with pytest.raises(SimulationCacheError) as raised:
        verify_simulation_result(tmp_path, "rel-hm/promo-conjoint-v1")

    assert raised.value.code == "simulation_result_unavailable"


def test_promote_accepts_withheld_but_rejects_mismatched_results(tmp_path: Path) -> None:
    withheld = result().model_copy(
        update={"recommendation_status": RecommendationStatus.WITHHELD, "rankings": ()}
    )
    assert promote_simulation_result(tmp_path, withheld, identity()).result.rankings == ()

    mismatched = identity().model_copy(update={"worker_version": "2", "random_seed": 18})
    with pytest.raises(SimulationCacheError, match="provenance"):
        promote_simulation_result(tmp_path, result(), mismatched)
