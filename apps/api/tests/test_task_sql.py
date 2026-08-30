from __future__ import annotations

import pytest
from structagent_api.materialization.task_sql import (
    SqlPolicyError,
    build_default_task_sql,
    validate_task_sql,
)


@pytest.mark.parametrize("task_id", ["rel-hm/user-churn", "rel-hm/item-sales"])
def test_reviewed_default_sql_is_normalized_and_content_addressed(task_id: str) -> None:
    artifact = build_default_task_sql(task_id)  # type: ignore[arg-type]
    repeated = build_default_task_sql(task_id)  # type: ignore[arg-type]

    assert artifact.query_sha256 == repeated.query_sha256
    assert artifact.normalized_sql == repeated.normalized_sql
    assert artifact.validation_report.status == "passed"
    assert {check.code for check in artifact.validation_report.checks} == {
        "bounded_horizon",
        "declared_columns",
        "declared_tables",
        "output_schema",
        "read_only_query",
        "reviewed_functions",
        "single_query",
    }


@pytest.mark.parametrize(
    ("sql", "expected_code"),
    [
        ("DROP TABLE customer", "read_only_query"),
        ("SELECT customer_id FROM customer; SELECT article_id FROM article", "single_query"),
        ("SELECT * FROM customer", "explicit_columns"),
        (
            "SELECT timestamp, customer_id, 0 AS churn "
            "FROM timestamps, missing WHERE timestamp < timestamp + INTERVAL '7 days'",
            "declared_tables",
        ),
        (
            "SELECT timestamp, customer_id, read_csv('secret.csv') AS churn "
            "FROM timestamps, customer WHERE timestamp < timestamp + INTERVAL '7 days'",
            "reviewed_functions",
        ),
        (
            "SELECT timestamp, missing, 0 AS churn FROM timestamps, customer "
            "WHERE timestamp < timestamp + INTERVAL '7 days'",
            "declared_columns",
        ),
        (
            "SELECT timestamp, customer_id, 0 AS churn FROM timestamps, customer "
            "WHERE timestamp < timestamp + INTERVAL '8 days'",
            "bounded_horizon",
        ),
        (
            "SELECT customer_id, timestamp, 0 AS churn FROM timestamps, customer "
            "WHERE timestamp < timestamp + INTERVAL '7 days'",
            "output_schema",
        ),
    ],
)
def test_sql_policy_rejects_unsafe_or_incompatible_queries(
    sql: str,
    expected_code: str,
) -> None:
    with pytest.raises(SqlPolicyError) as raised:
        validate_task_sql(
            sql,
            entity_column="customer_id",
            target_column="churn",
            horizon_days=7,
        )

    assert raised.value.code == expected_code
    assert "secret.csv" not in raised.value.detail
