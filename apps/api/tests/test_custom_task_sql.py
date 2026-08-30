from __future__ import annotations

import pytest
from structagent_api.compiler.service import draft_id_for
from structagent_api.compiler.sql import CandidateCache, CandidateLimitError, CandidateSpec
from structagent_api.materialization.task_sql import SqlPolicyError, build_default_task_sql


def cache() -> CandidateCache:
    return CandidateCache(
        draft_id=draft_id_for("rel-hm", "Predict churn"),
        model="gpt-5.6-terra",
        prompt_sha256="a" * 64,
        schema_sha256="b" * 64,
        instructions_sha256="c" * 64,
    )


def valid_candidate() -> CandidateSpec:
    sql = build_default_task_sql("rel-hm/user-churn").sql.replace("AS churn", "AS target")
    return CandidateSpec(
        sql=sql,
        entity_table="customer",
        entity_column="customer_id",
        task_type="binary_classification",
        horizon_days=7,
    )


def test_custom_sql_is_content_addressed_and_uses_fixed_target_alias() -> None:
    artifact = cache().validate(valid_candidate())

    assert artifact.task_id == f"rel-hm/custom/{artifact.query_sha256}"
    assert artifact.target_column == "target"
    assert artifact.provenance.attempt_count == 1


@pytest.mark.parametrize(
    ("candidate", "code"),
    [
        (
            CandidateSpec(
                sql="DROP TABLE customer",
                entity_table="customer",
                entity_column="customer_id",
                task_type="binary_classification",
                horizon_days=7,
            ),
            "read_only_query",
        ),
        (
            CandidateSpec(
                sql="SELECT 1" * 3_000,
                entity_table="customer",
                entity_column="customer_id",
                task_type="binary_classification",
                horizon_days=7,
            ),
            "sql_size",
        ),
        (
            CandidateSpec(
                sql=valid_candidate().sql,
                entity_table="customer",
                entity_column="article_id",
                task_type="binary_classification",
                horizon_days=7,
            ),
            "entity_key",
        ),
    ],
)
def test_custom_sql_fails_closed(candidate: CandidateSpec, code: str) -> None:
    with pytest.raises(SqlPolicyError) as raised:
        cache().validate(candidate)

    assert raised.value.code == code


def test_three_distinct_candidate_budget_counts_rejected_sql() -> None:
    candidate_cache = cache()
    for index in range(3):
        with pytest.raises(SqlPolicyError):
            candidate_cache.validate(
                CandidateSpec(
                    sql=f"DROP TABLE customer -- {index}",
                    entity_table="customer",
                    entity_column="customer_id",
                    task_type="binary_classification",
                    horizon_days=7,
                )
            )

    with pytest.raises(CandidateLimitError):
        candidate_cache.validate(valid_candidate())
