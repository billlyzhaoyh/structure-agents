"""V1 interface models for the fixture-only StructAgent workflow."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ContractVersion = Literal["v1"]
TaskType = Literal["binary_classification", "regression"]
TaskSource = Literal["default", "custom"]
DefaultTaskId = Literal["rel-hm/user-churn", "rel-hm/item-sales"]
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


class ArtifactReference(StrictModel):
    """Immutable provenance for a reviewed upstream artifact."""

    repository_url: str = Field(min_length=1, pattern=r"^https://")
    revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


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
    source: Literal["custom"]
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


class DefaultTaskDefinitionBase(StrictModel):
    task_id: str = Field(min_length=1)
    dataset_id: str = Field(min_length=1)
    source: Literal["default"]
    display_name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    entity: EntitySpec
    prediction_time: PredictionTimeSpec
    horizon: HorizonSpec
    target: TargetSpec
    eligibility_definition: str = Field(min_length=1)
    label_definition: str = Field(min_length=1)
    upstream_manifest: ArtifactReference


class DefaultBinaryTaskDefinition(DefaultTaskDefinitionBase):
    task_id: Literal["rel-hm/user-churn"]
    dataset_id: Literal["rel-hm"]
    task_type: Literal["binary_classification"]
    benchmark_metric: Literal["roc_auc"]
    diagnostic_metrics: list[ClassificationMetric] = Field(min_length=1)


class DefaultRegressionTaskDefinition(DefaultTaskDefinitionBase):
    task_id: Literal["rel-hm/item-sales"]
    dataset_id: Literal["rel-hm"]
    task_type: Literal["regression"]
    benchmark_metric: Literal["nmae"]
    diagnostic_metrics: list[RegressionMetric] = Field(min_length=1)


DefaultTaskDefinition = Annotated[
    DefaultBinaryTaskDefinition | DefaultRegressionTaskDefinition,
    Field(discriminator="task_type"),
]


class DefaultTaskCatalog(StrictModel):
    contract_version: ContractVersion
    fixture: Literal[True]
    implementation_status: Literal["metadata_only"]
    dataset_id: str = Field(min_length=1)
    benchmark_evaluator: ArtifactReference
    tasks: list[DefaultTaskDefinition] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_task_inventory(self) -> DefaultTaskCatalog:
        task_ids = [task.task_id for task in self.tasks]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("default task catalog contains duplicate task IDs")

        expected_prefix = f"{self.dataset_id}/"
        for task in self.tasks:
            if task.dataset_id != self.dataset_id:
                raise ValueError("default task dataset does not match its catalog")
            if not task.task_id.startswith(expected_prefix):
                raise ValueError("default task ID does not match its catalog dataset")
        return self


class DaytonaMaterializationRequest(StrictModel):
    """Explicit approval to materialize reviewed tasks on synthetic data."""

    contract_version: ContractVersion
    dataset_id: Literal["rel-hm"]
    task_ids: list[DefaultTaskId] = Field(min_length=1, max_length=2)
    approved: Literal[True]

    @model_validator(mode="after")
    def validate_unique_tasks(self) -> DaytonaMaterializationRequest:
        if len(self.task_ids) != len(set(self.task_ids)):
            raise ValueError("Daytona materialization contains duplicate task IDs")
        return self


class DaytonaTaskSummary(StrictModel):
    """Sanitized evidence for one materialized task package."""

    task_id: DefaultTaskId
    package_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    validation_status: Literal["passed"]
    train_rows: int = Field(ge=0)
    validation_rows: int = Field(ge=0)
    test_rows: int = Field(ge=0)


class DaytonaResourceSummary(StrictModel):
    """Bounded resources requested for the ephemeral sandbox."""

    cpu_cores: int = Field(gt=0)
    memory_gib: int = Field(gt=0)
    disk_gib: int = Field(gt=0)


class DaytonaMaterializationResponse(StrictModel):
    """Successful synthetic Daytona execution after verified cleanup."""

    contract_version: ContractVersion
    fixture: Literal[True]
    implementation_status: Literal["synthetic_execution"]
    execution_id: str = Field(pattern=r"^mat-[0-9a-f]{16}$")
    dataset_id: Literal["rel-hm"]
    mode: Literal["daytona-synthetic"]
    status: Literal["succeeded"]
    cleanup_confirmed: Literal[True]
    network_block_all: Literal[True]
    sql_canary_confirmed: Literal[True]
    resources: DaytonaResourceSummary
    tasks: list[DaytonaTaskSummary] = Field(min_length=1, max_length=2)

    @model_validator(mode="after")
    def validate_unique_tasks(self) -> DaytonaMaterializationResponse:
        task_ids = [task.task_id for task in self.tasks]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("Daytona response contains duplicate task IDs")
        return self


class TaskValidationCheck(StrictModel):
    """One sanitized, machine-readable materialization check."""

    code: str = Field(min_length=1)
    status: Literal["passed"]
    detail: str = Field(min_length=1)


class TaskValidationReport(StrictModel):
    """Evidence attached only after every guarded check passes."""

    status: Literal["passed"]
    checks: list[TaskValidationCheck] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_checks(self) -> TaskValidationReport:
        codes = [check.code for check in self.checks]
        if len(codes) != len(set(codes)):
            raise ValueError("validation report contains duplicate check codes")
        return self


class DefaultTaskSqlArtifact(StrictModel):
    """Reviewed DuckDB query for one pinned default task."""

    contract_version: ContractVersion
    dataset_id: Literal["rel-hm"]
    task_id: Literal["rel-hm/user-churn", "rel-hm/item-sales"]
    source: Literal["default"]
    dialect: Literal["duckdb"]
    sql: str = Field(min_length=1)
    normalized_sql: str = Field(min_length=1)
    query_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    entity_table: Literal["customer", "article"]
    entity_column: Literal["customer_id", "article_id"]
    target_column: Literal["churn", "sales"]
    task_type: TaskType
    horizon_days: int = Field(ge=1, le=7)
    provenance: ArtifactReference
    validation_report: TaskValidationReport

    @model_validator(mode="after")
    def validate_default_shape(self) -> DefaultTaskSqlArtifact:
        expected = {
            "rel-hm/user-churn": (
                "customer",
                "customer_id",
                "churn",
                "binary_classification",
            ),
            "rel-hm/item-sales": ("article", "article_id", "sales", "regression"),
        }[self.task_id]
        observed = (
            self.entity_table,
            self.entity_column,
            self.target_column,
            self.task_type,
        )
        if observed != expected:
            raise ValueError("task SQL shape does not match its reviewed default")
        return self


class CompilerProvenance(StrictModel):
    """Non-sensitive provenance for one agent-compiled query."""

    model: str = Field(min_length=1)
    prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    schema_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    instructions_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    attempt_count: int = Field(ge=1, le=3)


class CustomTaskSqlArtifact(StrictModel):
    """Validated DuckDB query produced by the trusted task compiler."""

    contract_version: ContractVersion
    dataset_id: Literal["rel-hm"]
    task_id: str = Field(pattern=r"^rel-hm/custom/[0-9a-f]{64}$")
    source: Literal["custom"]
    dialect: Literal["duckdb"]
    sql: str = Field(min_length=1)
    normalized_sql: str = Field(min_length=1)
    query_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    entity_table: Literal["customer", "article"]
    entity_column: Literal["customer_id", "article_id"]
    target_column: Literal["target"]
    task_type: TaskType
    horizon_days: int = Field(ge=1, le=7)
    provenance: CompilerProvenance
    validation_report: TaskValidationReport

    @model_validator(mode="after")
    def validate_entity_shape(self) -> CustomTaskSqlArtifact:
        expected_column = {
            "customer": "customer_id",
            "article": "article_id",
        }[self.entity_table]
        if self.entity_column != expected_column:
            raise ValueError("custom task entity does not match its reviewed key")
        return self


TaskSqlArtifact = Annotated[
    DefaultTaskSqlArtifact | CustomTaskSqlArtifact,
    Field(discriminator="source"),
]


class MaterializedFileReference(StrictModel):
    """Content-addressed reference to an untracked Parquet artifact."""

    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    row_count: int = Field(ge=0)
    byte_count: int = Field(gt=0)
    columns: list[str] = Field(min_length=1)

    @field_validator("path")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or value != path.as_posix():
            raise ValueError("artifact path must be a normalized relative POSIX path")
        return value


class DatasetTableReference(MaterializedFileReference):
    """Pinned relational table supplied separately to the future inference worker."""

    table: Literal["article", "customer", "transactions"]


class ModelTaskPackage(StrictModel):
    """Only the files that the guarded Modal RT-J worker may receive."""

    contract_version: ContractVersion
    dataset_id: Literal["rel-hm"]
    dataset_revision: str = Field(pattern=r"^[0-9a-f]{40}$|^synthetic$")
    task: TaskSqlArtifact
    database_files: list[DatasetTableReference] = Field(min_length=3, max_length=3)
    train_labels: MaterializedFileReference
    validation_labels: MaterializedFileReference
    test_rows: MaterializedFileReference

    @model_validator(mode="after")
    def validate_model_visible_files(self) -> ModelTaskPackage:
        tables = {reference.table for reference in self.database_files}
        if tables != {"article", "customer", "transactions"}:
            raise ValueError("model package requires each reviewed H&M table exactly once")

        expected_database_paths = {
            reference.table: f"{reference.table}.parquet" for reference in self.database_files
        }
        if any(
            reference.path != expected_database_paths[reference.table]
            for reference in self.database_files
        ):
            raise ValueError("database file paths must match their reviewed H&M tables")

        if (
            self.train_labels.path != "train.parquet"
            or self.validation_labels.path != "validation.parquet"
            or self.test_rows.path != "test.parquet"
        ):
            raise ValueError("task file paths must use the model-visible allowlist")
        all_paths = [
            *(reference.path for reference in self.database_files),
            self.train_labels.path,
            self.validation_labels.path,
            self.test_rows.path,
        ]
        if len(all_paths) != len(set(all_paths)):
            raise ValueError("model-visible file paths must be unique")
        if any("truth" in path.lower() for path in all_paths):
            raise ValueError("model-visible file paths cannot reference evaluator truth")

        labelled_columns = ["timestamp", self.task.entity_column, self.task.target_column]
        if self.train_labels.columns != labelled_columns:
            raise ValueError("train label columns do not match the task")
        if self.validation_labels.columns != labelled_columns:
            raise ValueError("validation label columns do not match the task")
        if self.test_rows.columns != ["timestamp", self.task.entity_column]:
            raise ValueError("model-visible test rows must not contain the target")
        return self


class EvaluatorTruthPackage(StrictModel):
    """Evaluator-owned target file that must not enter model construction."""

    contract_version: ContractVersion
    dataset_id: Literal["rel-hm"]
    task_id: str = Field(pattern=r"^rel-hm/(?:user-churn|item-sales|custom/[0-9a-f]{64})$")
    query_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    test_truth: MaterializedFileReference


class MaterializationResult(StrictModel):
    """Trusted-side result that preserves the model/evaluator separation."""

    contract_version: ContractVersion
    package_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_input: ModelTaskPackage
    evaluator_truth: EvaluatorTruthPackage
    validation_report: TaskValidationReport

    @model_validator(mode="after")
    def validate_package_alignment(self) -> MaterializationResult:
        task = self.model_input.task
        truth = self.evaluator_truth
        if truth.task_id != task.task_id or truth.query_sha256 != task.query_sha256:
            raise ValueError("evaluator truth does not match the model task")
        if truth.test_truth.row_count != self.model_input.test_rows.row_count:
            raise ValueError("model test rows and evaluator truth have different row counts")
        expected_truth_columns = ["timestamp", task.entity_column, task.target_column]
        if truth.test_truth.columns != expected_truth_columns:
            raise ValueError("evaluator truth columns do not match the task")
        return self


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
