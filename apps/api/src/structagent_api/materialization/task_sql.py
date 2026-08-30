"""Static SQL policy and reviewed query definitions for RelBench H&M."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Final, Literal, cast

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError
from sqlglot.optimizer.qualify import qualify

from structagent_api.catalog import REL_HM_DEFAULT_TASKS
from structagent_api.contracts import DefaultTaskSqlArtifact, TaskSqlArtifact
from structagent_api.contracts.models import TaskValidationCheck, TaskValidationReport

TaskId = Literal["rel-hm/user-churn", "rel-hm/item-sales"]

_SCHEMA: Final[dict[str, object]] = {
    "article": {
        "article_id": "BIGINT",
        "detail_desc": "VARCHAR",
        "product_type_name": "VARCHAR",
    },
    "customer": {"age": "DOUBLE", "customer_id": "VARCHAR"},
    "timestamps": {"timestamp": "TIMESTAMP"},
    "transactions": {
        "article_id": "BIGINT",
        "customer_id": "VARCHAR",
        "price": "DOUBLE",
        "sales_channel_id": "BIGINT",
        "t_dat": "TIMESTAMP",
    },
}
_ALLOWED_TABLES: Final[frozenset[str]] = frozenset(_SCHEMA)
_ALLOWED_FUNCTIONS: Final[frozenset[str]] = frozenset({"AND", "CAST", "COALESCE", "EXISTS", "SUM"})

_DEFAULT_SQL: Final[dict[TaskId, str]] = {
    "rel-hm/user-churn": """
SELECT
    timestamp,
    customer_id,
    CAST(
        NOT EXISTS (
            SELECT 1
            FROM transactions
            WHERE
                transactions.customer_id = customer.customer_id AND
                t_dat > timestamp AND
                t_dat <= timestamp + INTERVAL '7 days'
        ) AS INTEGER
    ) AS churn
FROM
    timestamps,
    customer
WHERE
    EXISTS (
        SELECT 1
        FROM transactions
        WHERE
            transactions.customer_id = customer.customer_id AND
            t_dat > timestamp - INTERVAL '7 days' AND
            t_dat <= timestamp
    )
""".strip(),
    "rel-hm/item-sales": """
SELECT
    timestamps.timestamp,
    article.article_id,
    COALESCE(SUM(transactions.price), 0) AS sales
FROM
    timestamps
CROSS JOIN article
LEFT JOIN transactions ON
    transactions.article_id = article.article_id AND
    transactions.t_dat > timestamps.timestamp AND
    transactions.t_dat <= timestamps.timestamp + INTERVAL '7 days'
GROUP BY
    timestamps.timestamp,
    article.article_id
""".strip(),
}


class SqlPolicyError(ValueError):
    """Sanitized failure raised before any task SQL is executed."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class ValidatedSql:
    original: str
    normalized: str
    sha256: str
    checks: tuple[TaskValidationCheck, ...]


def _policy_error(code: str, detail: str) -> SqlPolicyError:
    return SqlPolicyError(code=code, detail=detail)


def validate_task_sql(
    sql: str,
    *,
    entity_column: str,
    target_column: str,
    horizon_days: int,
) -> ValidatedSql:
    """Parse, qualify, and normalize one query against the reviewed schema."""
    try:
        statements = [statement for statement in sqlglot.parse(sql, read="duckdb") if statement]
    except SqlglotError as error:
        raise _policy_error("sql_parse", "task SQL is not valid DuckDB SQL") from error

    if len(statements) != 1:
        raise _policy_error("single_query", "task SQL must contain exactly one statement")

    expression = statements[0]
    if not isinstance(expression, exp.Query):
        raise _policy_error("read_only_query", "task SQL must be a read-only query")

    if expression.find(exp.DDL) or expression.find(exp.DML) or expression.find(exp.Command):
        raise _policy_error("read_only_query", "task SQL contains a non-query operation")
    if expression.find(exp.Copy) or expression.find(exp.Attach) or expression.find(exp.Pragma):
        raise _policy_error("unsafe_operation", "task SQL contains a forbidden operation")
    if expression.find(exp.Star):
        raise _policy_error("explicit_columns", "task SQL must name every selected column")

    cte_names = {cte.alias_or_name for cte in expression.find_all(exp.CTE)}
    for table in expression.find_all(exp.Table):
        if table.catalog or table.db:
            raise _policy_error("declared_tables", "qualified catalogs are not permitted")
        if table.name not in _ALLOWED_TABLES and table.name not in cte_names:
            raise _policy_error("declared_tables", "task SQL references an undeclared table")

    for function in expression.find_all(exp.Func):
        if function.sql_name().upper() not in _ALLOWED_FUNCTIONS:
            raise _policy_error("reviewed_functions", "task SQL uses an unreviewed function")

    intervals = list(expression.find_all(exp.Interval))
    if not intervals or any(
        interval.text("this") != str(horizon_days)
        or interval.text("unit").upper() not in {"DAY", "DAYS"}
        for interval in intervals
    ):
        raise _policy_error("bounded_horizon", "query intervals must match the declared horizon")

    try:
        qualified = qualify(
            expression,
            dialect="duckdb",
            schema=_SCHEMA,
            validate_qualify_columns=True,
            quote_identifiers=False,
            identify=False,
        )
    except SqlglotError as error:
        raise _policy_error(
            "declared_columns", "task SQL references an undeclared column"
        ) from error

    expected_columns = ["timestamp", entity_column, target_column]
    if qualified.named_selects != expected_columns:
        raise _policy_error(
            "output_schema",
            "task SQL must return timestamp, the declared entity, and the declared target",
        )

    normalized = qualified.sql(dialect="duckdb", pretty=False)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    checks = tuple(
        TaskValidationCheck(code=code, status="passed", detail=detail)
        for code, detail in (
            ("single_query", "Exactly one DuckDB query parsed."),
            ("read_only_query", "Only read-only query expressions are present."),
            ("declared_tables", "All table references use the reviewed H&M schema."),
            ("declared_columns", "All column references resolve against the reviewed schema."),
            ("reviewed_functions", "All functions are on the reviewed allowlist."),
            ("bounded_horizon", f"Every interval matches the {horizon_days}-day horizon."),
            ("output_schema", "The declared output columns are present in the required order."),
        )
    )
    return ValidatedSql(original=sql, normalized=normalized, sha256=digest, checks=checks)


def build_default_task_sql(task_id: TaskId) -> TaskSqlArtifact:
    """Build the guarded SQL artifact for one pinned default task."""
    task = next(task for task in REL_HM_DEFAULT_TASKS.tasks if task.task_id == task_id)
    validated = validate_task_sql(
        _DEFAULT_SQL[task_id],
        entity_column=task.entity.key_column,
        target_column=task.target.name,
        horizon_days=task.horizon.value,
    )
    return DefaultTaskSqlArtifact(
        contract_version="v1",
        dataset_id="rel-hm",
        task_id=task_id,
        source="default",
        dialect="duckdb",
        sql=validated.original,
        normalized_sql=validated.normalized,
        query_sha256=validated.sha256,
        entity_table=cast(Literal["customer", "article"], task.entity.table),
        entity_column=cast(Literal["customer_id", "article_id"], task.entity.key_column),
        target_column=cast(Literal["churn", "sales"], task.target.name),
        task_type=task.task_type,
        horizon_days=task.horizon.value,
        provenance=task.upstream_manifest,
        validation_report=TaskValidationReport(status="passed", checks=list(validated.checks)),
    )
