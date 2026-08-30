"""Versioned simulation study and result contracts."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from structagent_api.contracts.models import StrictModel

ContractDigest = str
AgentKey = Annotated[str, Field(min_length=1, max_length=200)]


class DatasetStatus(StrEnum):
    """Whether a dataset reference can be resolved for observed execution."""

    METADATA_ONLY_PLACEHOLDER = "metadata_only_placeholder"
    APPROVED_SNAPSHOT = "approved_snapshot"


class StudySource(StrEnum):
    """How a reviewed study entered the product."""

    DEFAULT = "default"
    CUSTOM = "custom"


class TraitName(StrEnum):
    """Aggregate H&M traits approved for model-visible personas."""

    AGE_BAND = "age_band"
    CLUB_MEMBER_STATUS = "club_member_status"
    FASHION_NEWS_FREQUENCY = "fashion_news_frequency"
    TENURE_BAND = "tenure_band"
    FREQUENCY_BAND = "frequency_band"
    RECENCY_BAND = "recency_band"
    BASKET_VALUE_BAND = "basket_value_band"
    PRIMARY_CATEGORY = "primary_category"
    INDEX_GROUP = "index_group"
    CHANNEL_MIX = "channel_mix"
    MARKDOWN_SHARE_BAND = "markdown_share_band"


class CertificationGate(StrEnum):
    """Evidence required when the simulation machinery is certified."""

    ORDER_INVARIANCE = "order_invariance"
    FULL_REPEAT_VARIANCE = "full_repeat_variance"
    TRAIT_ABLATION = "trait_ablation"
    MARKDOWN_CONCORDANCE = "markdown_concordance"
    TEMPORAL_HOLDOUT = "temporal_holdout"


class RunValidationGate(StrEnum):
    """Evidence checked for each approved simulation run."""

    CERTIFICATION_CURRENCY = "certification_currency"
    DESIGN_INVARIANTS = "design_invariants"
    RANDOMIZATION_BALANCE = "randomization_balance"
    SENTINEL_REPEAT_VARIANCE = "sentinel_repeat_variance"
    DECLARED_MONOTONICITY = "declared_monotonicity"


class GateStatus(StrEnum):
    """Structured outcome of a validation gate."""

    PASSED = "passed"
    FAILED = "failed"
    NOT_APPLICABLE = "not_applicable"


class RecommendationStatus(StrEnum):
    """Whether the result may expose a treatment ranking."""

    RECOMMENDED = "recommended"
    WITHHELD = "withheld"


class DatasetReference(StrictModel):
    """Public metadata for the private dataset snapshot resolved at execution time."""

    dataset_id: Literal["rel-hm"] = "rel-hm"
    status: DatasetStatus
    revision: str | None = Field(default=None, min_length=1)
    manifest_digest: ContractDigest | None = Field(
        default=None,
        pattern=r"^sha256:[0-9a-f]{64}$",
    )

    @model_validator(mode="after")
    def approved_snapshots_are_pinned(self) -> Self:
        if self.status is DatasetStatus.APPROVED_SNAPSHOT and (
            self.revision is None or self.manifest_digest is None
        ):
            raise ValueError("approved snapshots require a revision and manifest digest")
        if self.status is DatasetStatus.METADATA_ONLY_PLACEHOLDER and (
            self.revision is not None or self.manifest_digest is not None
        ):
            raise ValueError("placeholder dataset references cannot claim pinned provenance")
        return self


class SamplingSpec(StrictModel):
    """Bounded population sampling policy for a study."""

    method: Literal["proportional"] = "proportional"
    target_agents: int = Field(default=400, ge=300, le=600)
    seed: int = Field(ge=0, le=2**32 - 1)


class PopulationSpec(StrictModel):
    """Reviewed H&M population semantics and model-visible trait projection."""

    entity: Literal["customer"] = "customer"
    cutoff: date
    cohort_description: str = Field(min_length=1, max_length=500)
    traits: tuple[TraitName, ...] = Field(min_length=1)
    sampling: SamplingSpec

    @field_validator("traits")
    @classmethod
    def traits_are_unique(cls, traits: tuple[TraitName, ...]) -> tuple[TraitName, ...]:
        if len(traits) != len(set(traits)):
            raise ValueError("population traits must be unique")
        return traits


class AttributeApplicability(StrictModel):
    """Condition under which a dependent attribute varies from its baseline."""

    controlling_attribute: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    allowed_levels: tuple[str, ...] = Field(min_length=1)

    @field_validator("allowed_levels")
    @classmethod
    def allowed_levels_are_unique(cls, levels: tuple[str, ...]) -> tuple[str, ...]:
        if len(levels) != len(set(levels)):
            raise ValueError("applicability levels must be unique")
        return levels


class StudyAttribute(StrictModel):
    """A bounded categorical attribute in a discrete-choice profile."""

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1, max_length=100)
    levels: tuple[str, ...] = Field(min_length=2, max_length=10)
    baseline_level: str
    applicability: AttributeApplicability | None = None

    @model_validator(mode="after")
    def levels_are_valid(self) -> Self:
        if len(self.levels) != len(set(self.levels)):
            raise ValueError("attribute levels must be unique")
        if self.baseline_level not in self.levels:
            raise ValueError("baseline_level must be one of the attribute levels")
        return self


class ProfileLevel(StrictModel):
    """One named attribute level in a profile."""

    attribute: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    level: str = Field(min_length=1)


class MonotonicityConstraint(StrictModel):
    """A reviewed ordering expected from a meaningful simulated response."""

    attribute: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    ordered_levels: tuple[str, ...] = Field(min_length=2)


class DiscreteChoiceStudySpec(StrictModel):
    """Executable grammar for the first simulation study family."""

    study_type: Literal["discrete_choice"] = "discrete_choice"
    alternatives_per_task: Literal[2] = 2
    include_no_choice: Literal[True] = True
    tasks_per_agent: int = Field(default=10, ge=1, le=20)
    attributes: tuple[StudyAttribute, ...] = Field(min_length=1, max_length=10)
    control_profile: tuple[ProfileLevel, ...] | None = None
    monotonicity_constraints: tuple[MonotonicityConstraint, ...] = ()

    @model_validator(mode="after")
    def references_are_valid(self) -> Self:
        attributes_by_name = {attribute.name: attribute for attribute in self.attributes}
        if len(attributes_by_name) != len(self.attributes):
            raise ValueError("study attribute names must be unique")

        attribute_positions = {
            attribute.name: position for position, attribute in enumerate(self.attributes)
        }
        for attribute in self.attributes:
            applicability = attribute.applicability
            if applicability is None:
                continue
            controller = attributes_by_name.get(applicability.controlling_attribute)
            if controller is None:
                raise ValueError("attribute applicability references an unknown attribute")
            if controller.name == attribute.name:
                raise ValueError("an attribute cannot control its own applicability")
            if attribute_positions[controller.name] >= attribute_positions[attribute.name]:
                raise ValueError("controlling attributes must precede dependent attributes")
            unknown_levels = set(applicability.allowed_levels) - set(controller.levels)
            if unknown_levels:
                raise ValueError("attribute applicability references unknown controller levels")

        if self.control_profile is not None:
            control_by_attribute = {item.attribute: item.level for item in self.control_profile}
            if len(control_by_attribute) != len(self.control_profile):
                raise ValueError("control profile attributes must be unique")
            if set(control_by_attribute) != set(attributes_by_name):
                raise ValueError("control profile must define every study attribute exactly once")
            for name, level in control_by_attribute.items():
                attribute = attributes_by_name[name]
                if level not in attribute.levels:
                    raise ValueError("control profile references an unknown attribute level")
                if level != attribute.baseline_level:
                    raise ValueError("control profile must use every attribute baseline")

        for constraint in self.monotonicity_constraints:
            constrained_attribute = attributes_by_name.get(constraint.attribute)
            if constrained_attribute is None:
                raise ValueError("monotonicity constraint references an unknown attribute")
            if len(constraint.ordered_levels) != len(set(constraint.ordered_levels)):
                raise ValueError("monotonicity levels must be unique")
            if set(constraint.ordered_levels) - set(constrained_attribute.levels):
                raise ValueError("monotonicity constraint references unknown levels")
        return self


class RespondentModelPolicy(StrictModel):
    """Product-owned selection policy; the resolved model is recorded per run."""

    selection: Literal["system_selected"] = "system_selected"
    models_per_run: Literal[1] = 1


class ValidationPolicy(StrictModel):
    """Certification and per-run evidence required before a ranking is returned."""

    certification_gates: tuple[CertificationGate, ...]
    run_gates: tuple[RunValidationGate, ...]
    sentinel_fraction: float = Field(default=0.1, gt=0, le=0.25)

    @model_validator(mode="after")
    def gates_are_unique_and_complete(self) -> Self:
        if len(self.certification_gates) != len(set(self.certification_gates)):
            raise ValueError("certification gates must be unique")
        if len(self.run_gates) != len(set(self.run_gates)):
            raise ValueError("run gates must be unique")
        if set(self.certification_gates) != set(CertificationGate):
            raise ValueError("every certification gate is required")
        required_run_gates = set(RunValidationGate) - {RunValidationGate.DECLARED_MONOTONICITY}
        if not required_run_gates.issubset(self.run_gates):
            raise ValueError("required per-run validation gates are missing")
        return self


class SimulationStudyArtifact(StrictModel):
    """Reviewed, versioned semantics accepted by the simulation worker."""

    schema_version: Literal["1"] = "1"
    artifact_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._/-]*$")
    source: StudySource
    title: str = Field(min_length=1, max_length=200)
    decision: str = Field(min_length=1, max_length=500)
    dataset: DatasetReference
    population: PopulationSpec
    respondent_model: RespondentModelPolicy
    validation: ValidationPolicy
    study: DiscreteChoiceStudySpec


class SimulationPlanRequest(StrictModel):
    """Reviewed study plus pseudonymous agents accepted by the design worker."""

    schema_version: Literal["1"] = "1"
    study: SimulationStudyArtifact
    agent_keys: tuple[AgentKey, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def agent_inventory_matches_sampling_contract(self) -> Self:
        if len(self.agent_keys) != len(set(self.agent_keys)):
            raise ValueError("agent keys must be unique")
        if len(self.agent_keys) != self.study.population.sampling.target_agents:
            raise ValueError("agent count must match the reviewed sampling target")
        return self


class ChoiceAlternative(StrictModel):
    """One ordered profile shown in a discrete-choice task."""

    position: Literal[1, 2]
    profile: tuple[ProfileLevel, ...] = Field(min_length=1)
    is_control: bool

    @field_validator("profile")
    @classmethod
    def profile_attributes_are_unique(
        cls, profile: tuple[ProfileLevel, ...]
    ) -> tuple[ProfileLevel, ...]:
        attributes = [item.attribute for item in profile]
        if len(attributes) != len(set(attributes)):
            raise ValueError("choice profiles must define each attribute once")
        return profile


class ChoiceTask(StrictModel):
    """One independently ordered pair plus the mandatory no-choice option."""

    task_id: str = Field(min_length=1)
    agent_key: str = Field(min_length=1)
    sequence: int = Field(ge=1)
    alternatives: tuple[ChoiceAlternative, ChoiceAlternative]
    include_no_choice: Literal[True] = True

    @model_validator(mode="after")
    def alternatives_are_ordered_and_distinct(self) -> Self:
        if tuple(item.position for item in self.alternatives) != (1, 2):
            raise ValueError("choice alternatives must be stored in display order")
        profiles = [item.profile for item in self.alternatives]
        if profiles[0] == profiles[1]:
            raise ValueError("choice alternatives must use distinct profiles")
        return self


class SimulationRunPlan(StrictModel):
    """Canonical design-only output produced before respondent-model execution."""

    schema_version: Literal["1"] = "1"
    implementation_status: Literal["design_only"] = "design_only"
    study_artifact_id: str = Field(min_length=1)
    study_digest: ContractDigest = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    random_seed: int = Field(ge=0, le=2**32 - 1)
    agent_count: int = Field(gt=0)
    tasks_per_agent: int = Field(gt=0)
    task_count: int = Field(gt=0)
    tasks: tuple[ChoiceTask, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def counts_and_sequences_are_coherent(self) -> Self:
        if self.task_count != len(self.tasks):
            raise ValueError("task count does not match the task inventory")
        agents = {task.agent_key for task in self.tasks}
        if self.agent_count != len(agents):
            raise ValueError("agent count does not match the task inventory")
        if self.task_count != self.agent_count * self.tasks_per_agent:
            raise ValueError("task count does not match the per-agent design")
        for agent_key in agents:
            sequences = tuple(task.sequence for task in self.tasks if task.agent_key == agent_key)
            if sequences != tuple(range(1, self.tasks_per_agent + 1)):
                raise ValueError("every agent must have one ordered, complete task sequence")
        task_ids = [task.task_id for task in self.tasks]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("task IDs must be unique")
        return self


class ValidationGateResult(StrictModel):
    """Observed evidence for one certification or run-specific gate."""

    gate: CertificationGate | RunValidationGate
    status: GateStatus
    hard_gate: bool
    summary: str = Field(min_length=1, max_length=500)
    metric: float | None = None


class RankedAlternative(StrictModel):
    """A validated treatment profile in the user-facing shortlist."""

    rank: int = Field(ge=1, le=3)
    profile: tuple[ProfileLevel, ...] = Field(min_length=1)
    rank_stability: float = Field(ge=0, le=1)


class EffectDiagnostic(StrictModel):
    """Technical simulated-choice diagnostic, never a business uplift claim."""

    attribute: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    level: str = Field(min_length=1)
    estimate_percentage_points: float
    confidence_interval_lower: float
    confidence_interval_upper: float
    suppressed: bool
    suppression_reason: str | None = None

    @model_validator(mode="after")
    def interval_and_suppression_are_coherent(self) -> Self:
        if self.confidence_interval_lower > self.confidence_interval_upper:
            raise ValueError("confidence interval bounds are reversed")
        if self.suppressed and self.suppression_reason is None:
            raise ValueError("suppressed diagnostics require a reason")
        if not self.suppressed and self.suppression_reason is not None:
            raise ValueError("unsuppressed diagnostics cannot have a suppression reason")
        return self


class RunProvenance(StrictModel):
    """Execution identity required to audit a simulated result."""

    dataset_revision: str = Field(min_length=1)
    dataset_manifest_digest: ContractDigest = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    study_digest: ContractDigest = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    trait_query_digest: ContractDigest = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    prompt_template_digest: ContractDigest = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    certification_digest: ContractDigest = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    respondent_model_id: str = Field(min_length=1)
    respondent_model_version: str = Field(min_length=1)
    edsl_version: str = Field(min_length=1)
    random_seed: int = Field(ge=0, le=2**32 - 1)


class SimulationRunResult(StrictModel):
    """Canonical terminal JSON contract for a simulation run."""

    schema_version: Literal["1"] = "1"
    run_id: str = Field(min_length=1)
    study_artifact_id: str = Field(min_length=1)
    evidence_kind: Literal["simulated"] = "simulated"
    recommendation_status: RecommendationStatus
    validation: tuple[ValidationGateResult, ...] = Field(min_length=1)
    rankings: tuple[RankedAlternative, ...] = ()
    diagnostics: tuple[EffectDiagnostic, ...] = ()
    limitations: tuple[str, ...] = Field(min_length=1)
    provenance: RunProvenance

    @model_validator(mode="after")
    def recommendation_requires_passing_evidence(self) -> Self:
        hard_failure = any(
            result.hard_gate and result.status is not GateStatus.PASSED
            for result in self.validation
        )
        if self.recommendation_status is RecommendationStatus.RECOMMENDED:
            if hard_failure:
                raise ValueError("a recommendation cannot be returned after a hard-gate failure")
            if not self.rankings:
                raise ValueError("a recommendation requires at least one ranked alternative")
            ranks = tuple(item.rank for item in self.rankings)
            if ranks != tuple(range(1, len(self.rankings) + 1)):
                raise ValueError("ranked alternatives must be sequential and ordered")
        elif self.rankings:
            raise ValueError("withheld recommendations cannot expose rankings")
        return self


def canonical_contract_json(contract: StrictModel) -> str:
    """Serialize a contract deterministically for review and digesting."""

    return json.dumps(
        contract.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def contract_digest(contract: StrictModel) -> ContractDigest:
    """Return a namespaced SHA-256 digest of a canonical contract."""

    payload = canonical_contract_json(contract).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"
