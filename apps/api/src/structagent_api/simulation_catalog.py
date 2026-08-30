"""Reviewed, metadata-only catalog for default simulation studies."""

from __future__ import annotations

from datetime import date

from structagent_api.contracts.simulation import (
    AttributeApplicability,
    CertificationGate,
    DatasetReference,
    DatasetStatus,
    DiscreteChoiceStudySpec,
    MonotonicityConstraint,
    PopulationSpec,
    ProfileLevel,
    RespondentModelPolicy,
    RunValidationGate,
    SamplingSpec,
    SimulationStudyArtifact,
    StudyAttribute,
    StudySource,
    TraitName,
    ValidationPolicy,
)


def hm_promo_conjoint_v1() -> SimulationStudyArtifact:
    """Return the reviewed promo study, blocked until the upstream snapshot is pinned."""

    attributes = (
        StudyAttribute(
            name="discount_form",
            label="Discount form",
            levels=(
                "none",
                "percent_off",
                "bogo",
                "free_shipping",
                "member_exclusive_price",
            ),
            baseline_level="none",
        ),
        StudyAttribute(
            name="depth",
            label="Discount depth",
            levels=("0_percent", "10_percent", "20_percent", "30_percent", "40_percent"),
            baseline_level="0_percent",
            applicability=AttributeApplicability(
                controlling_attribute="discount_form",
                allowed_levels=("percent_off", "member_exclusive_price"),
            ),
        ),
        StudyAttribute(
            name="threshold",
            label="Purchase threshold",
            levels=("none", "buy_2", "buy_3"),
            baseline_level="none",
            applicability=AttributeApplicability(
                controlling_attribute="discount_form",
                allowed_levels=("bogo",),
            ),
        ),
        StudyAttribute(
            name="urgency",
            label="Urgency",
            levels=("none", "weekend_only", "last_chance_sizes"),
            baseline_level="none",
        ),
        StudyAttribute(
            name="framing",
            label="Framing",
            levels=("plain", "new_season", "member_perk", "back_in_stock"),
            baseline_level="plain",
        ),
    )
    return SimulationStudyArtifact(
        artifact_id="rel-hm/promo-conjoint-v1",
        source=StudySource.DEFAULT,
        title="H&M promotional offer screening",
        decision=(
            "Rank promotional offer designs for one eligible H&M customer population to "
            "shortlist candidates for a later field experiment."
        ),
        dataset=DatasetReference(status=DatasetStatus.METADATA_ONLY_PLACEHOLDER),
        population=PopulationSpec(
            cutoff=date(2020, 9, 7),
            cohort_description="Customers with at least one transaction before the cutoff.",
            traits=tuple(TraitName),
            sampling=SamplingSpec(target_agents=400, seed=17),
        ),
        respondent_model=RespondentModelPolicy(),
        validation=ValidationPolicy(
            certification_gates=tuple(CertificationGate),
            run_gates=tuple(RunValidationGate),
            sentinel_fraction=0.1,
        ),
        study=DiscreteChoiceStudySpec(
            alternatives_per_task=2,
            include_no_choice=True,
            tasks_per_agent=10,
            attributes=attributes,
            control_profile=tuple(
                ProfileLevel(attribute=attribute.name, level=attribute.baseline_level)
                for attribute in attributes
            ),
            monotonicity_constraints=(
                MonotonicityConstraint(
                    attribute="depth",
                    ordered_levels=("10_percent", "20_percent", "30_percent", "40_percent"),
                ),
            ),
        ),
    )
