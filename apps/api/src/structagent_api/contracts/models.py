"""V1 interface models for the fixture-only StructAgent workflow."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ContractVersion = Literal["v1"]
TaskType = Literal["binary_classification", "regression"]
DataType = Literal[
    "boolean",
    "categorical",
    "integer",
    "number",
    "string",
    "text",
    "timestamp",
]


class StrictModel(BaseModel):
    """Reject undeclared fields at every public contract boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class FixtureEnvelope(StrictModel):
    """Marks data that exists only to support initial frontend integration."""

    contract_version: ContractVersion
    fixture: Literal[True]
    implementation_status: Literal["placeholder"]


class ForeignKeyReference(StrictModel):
    table: str = Field(min_length=1)
    column: str = Field(min_length=1)


class ColumnDescriptor(StrictModel):
    name: str = Field(min_length=1)
    data_type: DataType
    primary_key: bool = False
    foreign_key: ForeignKeyReference | None = None
    time_column: bool = False


class TableDescriptor(StrictModel):
    name: str = Field(min_length=1)
    columns: list[ColumnDescriptor] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_column_names(self) -> TableDescriptor:
        names = [column.name for column in self.columns]
        if len(names) != len(set(names)):
            raise ValueError(f"table {self.name!r} contains duplicate column names")
        return self


class DatasetDescriptor(StrictModel):
    contract_version: ContractVersion
    fixture: Literal[True]
    implementation_status: Literal["metadata_only"]
    dataset_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    supported_task_types: list[TaskType] = Field(min_length=1)
    tables: list[TableDescriptor] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_relational_schema(self) -> DatasetDescriptor:
        table_names = [table.name for table in self.tables]
        if len(table_names) != len(set(table_names)):
            raise ValueError("dataset contains duplicate table names")
        if len(self.supported_task_types) != len(set(self.supported_task_types)):
            raise ValueError("dataset contains duplicate supported task types")

        table_columns = {
            table.name: {column.name for column in table.columns} for table in self.tables
        }
        for table in self.tables:
            for column in table.columns:
                reference = column.foreign_key
                if reference is None:
                    continue
                if reference.table not in table_columns:
                    raise ValueError(
                        f"column {table.name}.{column.name} references unknown table "
                        f"{reference.table}"
                    )
                if reference.column not in table_columns[reference.table]:
                    raise ValueError(
                        f"column {table.name}.{column.name} references unknown column "
                        f"{reference.table}.{reference.column}"
                    )
        return self


class TaskDraftRequest(StrictModel):
    contract_version: ContractVersion
    dataset_id: str = Field(min_length=1)
    prompt: str = Field(min_length=1)


class ClarificationQuestion(StrictModel):
    question_id: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    answer_kind: Literal["free_text", "single_choice"]
    choices: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_choices(self) -> ClarificationQuestion:
        if self.answer_kind == "single_choice" and len(self.choices) < 2:
            raise ValueError("single-choice questions require at least two choices")
        if self.answer_kind == "free_text" and self.choices:
            raise ValueError("free-text questions cannot define choices")
        return self


class NeedsClarification(FixtureEnvelope):
    outcome: Literal["needs_clarification"]
    draft_id: str = Field(min_length=1)
    questions: list[ClarificationQuestion] = Field(min_length=1)


class EntitySpec(StrictModel):
    table: str = Field(min_length=1)
    key_column: str = Field(min_length=1)


class PredictionTimeSpec(StrictModel):
    table: str = Field(min_length=1)
    column: str = Field(min_length=1)


class HorizonSpec(StrictModel):
    value: int = Field(gt=0)
    unit: Literal["days", "weeks", "months"]


class TargetSpec(StrictModel):
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    positive_class: str | None = None
    unit: str | None = None


class QueryArtifact(StrictModel):
    purpose: Literal["eligibility", "label"]
    status: Literal["generated", "not_generated"]
    dialect: Literal["duckdb"]
    sql: str | None

    @model_validator(mode="after")
    def validate_sql_state(self) -> QueryArtifact:
        if self.status == "generated" and not self.sql:
            raise ValueError("generated query artifacts require SQL")
        if self.status == "not_generated" and self.sql is not None:
            raise ValueError("non-generated query artifacts cannot contain SQL")
        return self


class TaskContractBase(StrictModel):
    draft_id: str = Field(min_length=1)
    dataset_id: str = Field(min_length=1)
    entity: EntitySpec
    prediction_time: PredictionTimeSpec
    horizon: HorizonSpec
    target: TargetSpec
    eligibility_definition: str = Field(min_length=1)
    label_definition: str = Field(min_length=1)
    query_artifacts: list[QueryArtifact] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def validate_query_artifacts(self) -> TaskContractBase:
        purposes = {artifact.purpose for artifact in self.query_artifacts}
        if purposes != {"eligibility", "label"}:
            raise ValueError("task contracts require one eligibility and one label query")
        return self


ClassificationMetric = Literal[
    "accuracy",
    "auroc",
    "average_precision",
    "brier_score",
    "f1",
    "log_loss",
]
RegressionMetric = Literal["mae", "r2", "rmse"]


class BinaryTaskContract(TaskContractBase):
    task_type: Literal["binary_classification"]
    recommended_metrics: list[ClassificationMetric] = Field(min_length=1)


class RegressionTaskContract(TaskContractBase):
    task_type: Literal["regression"]
    recommended_metrics: list[RegressionMetric] = Field(min_length=1)


TaskContract = Annotated[
    BinaryTaskContract | RegressionTaskContract,
    Field(discriminator="task_type"),
]


class DraftReady(FixtureEnvelope):
    outcome: Literal["draft_ready"]
    contract: TaskContract


TaskDraftOutcome = Annotated[
    NeedsClarification | DraftReady,
    Field(discriminator="outcome"),
]

RunStatus = Literal[
    "awaiting_approval",
    "queued",
    "preparing",
    "predicting",
    "evaluating",
    "succeeded",
    "failed",
]


class RunRecord(FixtureEnvelope):
    run_id: str = Field(min_length=1)
    draft_id: str = Field(min_length=1)
    status: RunStatus
    progress_percent: int = Field(ge=0, le=100)
    message: str = Field(min_length=1)


class IntegrityCheck(StrictModel):
    name: str = Field(min_length=1)
    status: Literal["failed", "not_run", "passed"]
    detail: str = Field(min_length=1)


class EvaluationProvenance(StrictModel):
    dataset_revision: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    model_revision: str = Field(min_length=1)
    context_length: int = Field(gt=0)
    duration_seconds: float = Field(ge=0)


class ClassificationMetrics(StrictModel):
    auroc: float = Field(ge=0, le=1)
    average_precision: float = Field(ge=0, le=1)
    log_loss: float = Field(ge=0)
    brier_score: float = Field(ge=0, le=1)
    accuracy: float = Field(ge=0, le=1)
    f1: float = Field(ge=0, le=1)


class RegressionMetrics(StrictModel):
    mae: float = Field(ge=0)
    rmse: float = Field(ge=0)
    r2: float


class EvaluationResultBase(FixtureEnvelope):
    run_id: str = Field(min_length=1)
    dataset_id: str = Field(min_length=1)
    sample_count: int = Field(gt=0)
    coverage: float = Field(ge=0, le=1)
    provenance: EvaluationProvenance
    integrity_checks: list[IntegrityCheck] = Field(min_length=1)


class ClassificationEvaluationResult(EvaluationResultBase):
    task_type: Literal["binary_classification"]
    prevalence: float = Field(ge=0, le=1)
    metrics: ClassificationMetrics


class RegressionEvaluationResult(EvaluationResultBase):
    task_type: Literal["regression"]
    target_unit: str = Field(min_length=1)
    metrics: RegressionMetrics


EvaluationResult = Annotated[
    ClassificationEvaluationResult | RegressionEvaluationResult,
    Field(discriminator="task_type"),
]
