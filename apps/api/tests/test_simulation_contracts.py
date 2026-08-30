from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError
from structagent_api.contracts.simulation import (
    CertificationGate,
    DatasetReference,
    DatasetStatus,
    GateStatus,
    ProfileLevel,
    RankedAlternative,
    RecommendationStatus,
    RunProvenance,
    RunValidationGate,
    SimulationPlanRequest,
    SimulationRunResult,
    SimulationStudyArtifact,
    ValidationGateResult,
    canonical_contract_json,
    contract_digest,
)
from structagent_api.simulation_catalog import hm_promo_conjoint_v1

DIGEST = f"sha256:{'a' * 64}"


def provenance() -> RunProvenance:
    return RunProvenance(
        dataset_revision="rel-hm-reviewed-revision",
        dataset_manifest_digest=DIGEST,
        study_digest=DIGEST,
        trait_query_digest=DIGEST,
        prompt_template_digest=DIGEST,
        certification_digest=DIGEST,
        respondent_model_id="system-model",
        respondent_model_version="pinned-version",
        edsl_version="1.0.0",
        random_seed=17,
    )


def passed_gate() -> ValidationGateResult:
    return ValidationGateResult(
        gate=RunValidationGate.DESIGN_INVARIANTS,
        status=GateStatus.PASSED,
        hard_gate=True,
        summary="Every generated task satisfied the reviewed design.",
    )


def failed_gate() -> ValidationGateResult:
    return ValidationGateResult(
        gate=CertificationGate.TEMPORAL_HOLDOUT,
        status=GateStatus.FAILED,
        hard_gate=True,
        summary="Purchase intent did not clear the certified threshold.",
        metric=0.5,
    )


def top_rank() -> RankedAlternative:
    return RankedAlternative(
        rank=1,
        profile=(ProfileLevel(attribute="discount_form", level="percent_off"),),
        rank_stability=0.94,
    )


def result_payload(**updates: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "run_id": "run-123",
        "study_artifact_id": "rel-hm/promo-conjoint-v1",
        "recommendation_status": RecommendationStatus.WITHHELD,
        "validation": (failed_gate(),),
        "limitations": ("This is a simulated H&M-conditioned choice result.",),
        "provenance": provenance(),
    }
    payload.update(updates)
    return payload


def test_reviewed_default_captures_the_agreed_study_without_claiming_live_data() -> None:
    artifact = hm_promo_conjoint_v1()

    assert artifact.artifact_id == "rel-hm/promo-conjoint-v1"
    assert artifact.dataset.status is DatasetStatus.METADATA_ONLY_PLACEHOLDER
    assert artifact.dataset.revision is None
    assert artifact.population.sampling.target_agents == 400
    assert artifact.study.alternatives_per_task == 2
    assert artifact.study.include_no_choice is True
    assert artifact.study.tasks_per_agent == 10
    assert [attribute.name for attribute in artifact.study.attributes] == [
        "discount_form",
        "depth",
        "threshold",
        "urgency",
        "framing",
    ]
    assert set(artifact.validation.certification_gates) == set(CertificationGate)
    assert artifact.validation.sentinel_fraction == 0.1


def test_approved_dataset_snapshot_requires_pinned_provenance() -> None:
    with pytest.raises(ValidationError, match="require a revision and manifest digest"):
        DatasetReference(status=DatasetStatus.APPROVED_SNAPSHOT)

    reference = DatasetReference(
        status=DatasetStatus.APPROVED_SNAPSHOT,
        revision="rel-hm-reviewed-revision",
        manifest_digest=DIGEST,
    )

    assert reference.revision == "rel-hm-reviewed-revision"


def test_default_study_round_trips_with_a_stable_digest() -> None:
    artifact = hm_promo_conjoint_v1()
    encoded = canonical_contract_json(artifact)
    decoded = SimulationStudyArtifact.model_validate_json(encoded)

    assert decoded == artifact
    assert contract_digest(decoded) == contract_digest(artifact)
    assert contract_digest(artifact).startswith("sha256:")


def test_plan_request_requires_the_reviewed_agent_count() -> None:
    with pytest.raises(ValidationError, match="agent count must match"):
        SimulationPlanRequest(study=hm_promo_conjoint_v1(), agent_keys=("agent-1",))


def test_plan_request_rejects_duplicate_pseudonymous_agents() -> None:
    artifact = hm_promo_conjoint_v1()
    keys = tuple(f"agent-{index:03d}" for index in range(399)) + ("agent-000",)

    with pytest.raises(ValidationError, match="agent keys must be unique"):
        SimulationPlanRequest(study=artifact, agent_keys=keys)


def test_hard_gate_failure_can_only_return_a_withheld_result() -> None:
    withheld = SimulationRunResult.model_validate(result_payload())

    assert withheld.recommendation_status is RecommendationStatus.WITHHELD
    assert withheld.rankings == ()

    with pytest.raises(ValidationError, match="cannot be returned after a hard-gate failure"):
        SimulationRunResult.model_validate(
            result_payload(
                recommendation_status=RecommendationStatus.RECOMMENDED,
                rankings=(top_rank(),),
            )
        )


def test_withheld_result_cannot_leak_a_ranking() -> None:
    with pytest.raises(ValidationError, match="withheld recommendations cannot expose rankings"):
        SimulationRunResult.model_validate(result_payload(rankings=(top_rank(),)))


def test_passing_evidence_can_return_an_ordered_shortlist() -> None:
    result = SimulationRunResult.model_validate(
        result_payload(
            recommendation_status=RecommendationStatus.RECOMMENDED,
            validation=(passed_gate(),),
            rankings=(top_rank(),),
        )
    )

    assert result.rankings[0].rank == 1
    assert result.evidence_kind == "simulated"


def test_result_contract_rejects_prohibited_magnitude_claim_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        SimulationRunResult.model_validate(result_payload(uplift_percentage=12.5))
