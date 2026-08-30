"""Static validation and bounded cache for agent-proposed H&M SQL."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Literal

from structagent_api.contracts import CompilerProvenance, CustomTaskSqlArtifact
from structagent_api.contracts.models import TaskValidationReport
from structagent_api.materialization.task_sql import SqlPolicyError, validate_task_sql

EntityTable = Literal["customer", "article"]
EntityColumn = Literal["customer_id", "article_id"]
CustomTaskType = Literal["binary_classification", "regression"]


class CandidateLimitError(ValueError):
    """Raised after three distinct SQL candidates have been submitted."""


@dataclass(frozen=True)
class CandidateSpec:
    sql: str
    entity_table: EntityTable
    entity_column: EntityColumn
    task_type: CustomTaskType
    horizon_days: int


@dataclass
class CandidateCache:
    draft_id: str
    model: str
    prompt_sha256: str
    schema_sha256: str
    instructions_sha256: str
    max_candidates: int = 3
    _raw_digests: set[str] = field(default_factory=set)
    _artifacts: dict[str, CustomTaskSqlArtifact] = field(default_factory=dict)

    @property
    def attempt_count(self) -> int:
        return len(self._raw_digests)

    def validate(self, candidate: CandidateSpec) -> CustomTaskSqlArtifact:
        if len(candidate.sql) > 20_000:
            raise SqlPolicyError("sql_size", "task SQL exceeds the V1 size limit")
        expected_column = {"customer": "customer_id", "article": "article_id"}[
            candidate.entity_table
        ]
        if candidate.entity_column != expected_column:
            raise SqlPolicyError("entity_key", "task entity must use its reviewed key")
        if not 1 <= candidate.horizon_days <= 7:
            raise SqlPolicyError("bounded_horizon", "task horizon must be from one to seven days")

        raw_digest = hashlib.sha256(candidate.sql.encode("utf-8")).hexdigest()
        if raw_digest not in self._raw_digests:
            if self.attempt_count >= self.max_candidates:
                raise CandidateLimitError("the three-candidate SQL repair budget is exhausted")
            self._raw_digests.add(raw_digest)

        validated = validate_task_sql(
            candidate.sql,
            entity_column=candidate.entity_column,
            target_column="target",
            horizon_days=candidate.horizon_days,
        )
        existing = self._artifacts.get(validated.sha256)
        if existing is not None:
            return existing

        artifact = CustomTaskSqlArtifact(
            contract_version="v1",
            dataset_id="rel-hm",
            task_id=f"rel-hm/custom/{validated.sha256}",
            source="custom",
            dialect="duckdb",
            sql=validated.original,
            normalized_sql=validated.normalized,
            query_sha256=validated.sha256,
            entity_table=candidate.entity_table,
            entity_column=candidate.entity_column,
            target_column="target",
            task_type=candidate.task_type,
            horizon_days=candidate.horizon_days,
            provenance=CompilerProvenance(
                model=self.model,
                prompt_sha256=self.prompt_sha256,
                schema_sha256=self.schema_sha256,
                instructions_sha256=self.instructions_sha256,
                attempt_count=self.attempt_count,
            ),
            validation_report=TaskValidationReport(
                status="passed",
                checks=list(validated.checks),
            ),
        )
        self._artifacts[validated.sha256] = artifact
        return artifact

    def get(self, query_sha256: str) -> CustomTaskSqlArtifact | None:
        return self._artifacts.get(query_sha256)
