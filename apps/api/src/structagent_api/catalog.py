"""Reviewed, metadata-only catalog for the active H&M V1 dataset."""

from __future__ import annotations

from structagent_api.contracts.models import (
    ArtifactReference,
    ColumnDescriptor,
    DatasetDescriptor,
    DefaultBinaryTaskDefinition,
    DefaultRegressionTaskDefinition,
    DefaultTaskCatalog,
    EntitySpec,
    ForeignKeyReference,
    HorizonSpec,
    PredictionTimeSpec,
    TableDescriptor,
    TargetSpec,
)

ACTIVE_DATASET_ID = "rel-hm"

RELBENCH_V1_REPOSITORY = "https://huggingface.co/datasets/stanford-star/relbench-v1"
RELBENCH_V1_REVISION = "d8e976fd0a4b78877204bc8dfbcfc9a9f7f48600"
RELBENCH_REPOSITORY = "https://github.com/stanford-star/relbench"
RELBENCH_REVISION = "9a223758cea1fd486a8d20f9e2f7ac4f42c88d0f"

REL_HM_DATASET = DatasetDescriptor(
    contract_version="v1",
    fixture=True,
    implementation_status="metadata_only",
    dataset_id=ACTIVE_DATASET_ID,
    display_name="RelBench H&M",
    description="Metadata-only schema subset for the active H&M V1 dataset.",
    supported_task_types=["binary_classification", "regression"],
    tables=[
        TableDescriptor(
            name="customer",
            columns=[
                ColumnDescriptor(
                    name="customer_id",
                    data_type="string",
                    primary_key=True,
                ),
                ColumnDescriptor(name="age", data_type="number"),
            ],
        ),
        TableDescriptor(
            name="article",
            columns=[
                ColumnDescriptor(
                    name="article_id",
                    data_type="integer",
                    primary_key=True,
                ),
                ColumnDescriptor(name="product_type_name", data_type="categorical"),
                ColumnDescriptor(name="detail_desc", data_type="text"),
            ],
        ),
        TableDescriptor(
            name="transactions",
            columns=[
                ColumnDescriptor(
                    name="customer_id",
                    data_type="string",
                    foreign_key=ForeignKeyReference(
                        table="customer",
                        column="customer_id",
                    ),
                ),
                ColumnDescriptor(
                    name="article_id",
                    data_type="integer",
                    foreign_key=ForeignKeyReference(
                        table="article",
                        column="article_id",
                    ),
                ),
                ColumnDescriptor(
                    name="t_dat",
                    data_type="timestamp",
                    time_column=True,
                ),
                ColumnDescriptor(name="price", data_type="number"),
                ColumnDescriptor(name="sales_channel_id", data_type="integer"),
            ],
        ),
    ],
)

BENCHMARK_EVALUATOR = ArtifactReference(
    repository_url=RELBENCH_REPOSITORY,
    revision=RELBENCH_REVISION,
    path="relbench/load.py",
    sha256="bc2f1fad23405e2f8c195d6079cb8883b9e652aec4f2868a5ccd884aba08f5c5",
)

REL_HM_DEFAULT_TASKS = DefaultTaskCatalog(
    contract_version="v1",
    fixture=True,
    implementation_status="metadata_only",
    dataset_id=ACTIVE_DATASET_ID,
    benchmark_evaluator=BENCHMARK_EVALUATOR,
    tasks=[
        DefaultBinaryTaskDefinition(
            task_id="rel-hm/user-churn",
            dataset_id=ACTIVE_DATASET_ID,
            source="default",
            display_name="Customer churn",
            description=(
                "Predict whether an eligible customer will make no transaction in the "
                "next seven days."
            ),
            task_type="binary_classification",
            entity=EntitySpec(table="customer", key_column="customer_id"),
            prediction_time=PredictionTimeSpec(table="timestamps", column="timestamp"),
            horizon=HorizonSpec(value=7, unit="days"),
            target=TargetSpec(
                name="churn",
                description=(
                    "One when an eligible customer makes no transaction in the next "
                    "seven days; otherwise zero."
                ),
                positive_class="No transaction in (timestamp, timestamp + 7 days].",
                unit=None,
            ),
            eligibility_definition=(
                "Customer has at least one transaction in (timestamp - 7 days, timestamp]."
            ),
            label_definition=(
                "One when no customer transaction occurs in "
                "(timestamp, timestamp + 7 days]; otherwise zero."
            ),
            benchmark_metric="roc_auc",
            diagnostic_metrics=[
                "average_precision",
                "accuracy",
                "f1",
                "log_loss",
                "brier_score",
            ],
            upstream_manifest=ArtifactReference(
                repository_url=RELBENCH_V1_REPOSITORY,
                revision=RELBENCH_V1_REVISION,
                path="rel-hm/tasks/user-churn/manifest.yaml",
                sha256=("546bef09917d3453e00bd25d356493c7dd97c9a9039fc9af37c4997fef8aa9f9"),
            ),
        ),
        DefaultRegressionTaskDefinition(
            task_id="rel-hm/item-sales",
            dataset_id=ACTIVE_DATASET_ID,
            source="default",
            display_name="Article sales",
            description="Predict each known article's total sales over the next seven days.",
            task_type="regression",
            entity=EntitySpec(table="article", key_column="article_id"),
            prediction_time=PredictionTimeSpec(table="timestamps", column="timestamp"),
            horizon=HorizonSpec(value=7, unit="days"),
            target=TargetSpec(
                name="sales",
                description=(
                    "Sum of transaction price values for the article over the next "
                    "seven days, or zero when no transaction occurs."
                ),
                positive_class=None,
                unit="sum of transaction price values",
            ),
            eligibility_definition="Every known article at each prediction timestamp.",
            label_definition=(
                "Sum transaction price for the article in "
                "(timestamp, timestamp + 7 days], defaulting to zero."
            ),
            benchmark_metric="nmae",
            diagnostic_metrics=["mae", "rmse", "r2"],
            upstream_manifest=ArtifactReference(
                repository_url=RELBENCH_V1_REPOSITORY,
                revision=RELBENCH_V1_REVISION,
                path="rel-hm/tasks/item-sales/manifest.yaml",
                sha256=("fc3f971da007d7c17872d3c0d840ca79609af5942ebec166154d4aaf9e7a6675"),
            ),
        ),
    ],
)
