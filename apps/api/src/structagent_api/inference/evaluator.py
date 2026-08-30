"""Trusted evaluator that joins truth only after predictions are sealed."""

from __future__ import annotations

import math
from pathlib import Path

import duckdb

from structagent_api.contracts import (
    BatchClassificationEvaluation,
    BatchRegressionEvaluation,
    CompletedPredictionPackage,
    MaterializationResult,
)
from structagent_api.contracts.inference import BatchRegressionMetrics
from structagent_api.contracts.models import ClassificationMetrics, IntegrityCheck
from structagent_api.inference.adapter import RELBENCH_EVALUATOR_REVISION, REVIEWED_TASK_IDS
from structagent_api.inference.artifacts import resolve_artifact


class InferenceEvaluationError(RuntimeError):
    """Sanitized prediction or evaluation failure."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _quote(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _average_rank_auc(labels: list[int], scores: list[float]) -> float:
    positives = sum(labels)
    negatives = len(labels) - positives
    if positives == 0 or negatives == 0:
        raise InferenceEvaluationError(
            "class_support", "classification evaluation requires both truth classes"
        )
    ordered = sorted(zip(scores, labels, strict=True))
    positive_rank_sum = 0.0
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][0] == ordered[index][0]:
            end += 1
        average_rank = ((index + 1) + end) / 2
        positive_rank_sum += average_rank * sum(label for _, label in ordered[index:end])
        index = end
    return (positive_rank_sum - positives * (positives + 1) / 2) / (positives * negatives)


def _average_precision(labels: list[int], scores: list[float]) -> float:
    positives = sum(labels)
    ordered = sorted(zip(scores, labels, strict=True), reverse=True)
    cumulative_positive = 0
    cumulative_count = 0
    result = 0.0
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][0] == ordered[index][0]:
            end += 1
        group_positive = sum(label for _, label in ordered[index:end])
        cumulative_positive += group_positive
        cumulative_count += end - index
        result += (group_positive / positives) * (cumulative_positive / cumulative_count)
        index = end
    return result


def _classification_metrics(labels: list[int], scores: list[float]) -> ClassificationMetrics:
    clipped = [min(max(value, 1e-15), 1 - 1e-15) for value in scores]
    predicted = [int(value >= 0.5) for value in scores]
    true_positive = sum(y == 1 and p == 1 for y, p in zip(labels, predicted, strict=True))
    false_positive = sum(y == 0 and p == 1 for y, p in zip(labels, predicted, strict=True))
    false_negative = sum(y == 1 and p == 0 for y, p in zip(labels, predicted, strict=True))
    denominator = 2 * true_positive + false_positive + false_negative
    return ClassificationMetrics(
        auroc=_average_rank_auc(labels, scores),
        average_precision=_average_precision(labels, scores),
        log_loss=-sum(
            y * math.log(p) + (1 - y) * math.log(1 - p)
            for y, p in zip(labels, clipped, strict=True)
        )
        / len(labels),
        brier_score=sum((p - y) ** 2 for y, p in zip(labels, scores, strict=True)) / len(labels),
        accuracy=sum(y == p for y, p in zip(labels, predicted, strict=True)) / len(labels),
        f1=(2 * true_positive / denominator) if denominator else 0.0,
    )


def _regression_metrics(
    labels: list[float], predictions: list[float], train_targets: list[float]
) -> BatchRegressionMetrics:
    count = len(labels)
    mae = sum(abs(y - p) for y, p in zip(labels, predictions, strict=True)) / count
    rmse = math.sqrt(sum((y - p) ** 2 for y, p in zip(labels, predictions, strict=True)) / count)
    mean_label = sum(labels) / count
    total = sum((value - mean_label) ** 2 for value in labels)
    residual = sum((y - p) ** 2 for y, p in zip(labels, predictions, strict=True))
    train_mean = sum(train_targets) / len(train_targets)
    train_std = math.sqrt(
        sum((value - train_mean) ** 2 for value in train_targets) / (len(train_targets) - 1)
    )
    if total <= 0:
        raise InferenceEvaluationError("regression_scale", "regression test scale is invalid")
    nmae = 1.0 if not math.isfinite(train_std) or train_std <= 0 else mae / train_std
    return BatchRegressionMetrics(mae=mae, rmse=rmse, r2=1 - residual / total, nmae=nmae)


def evaluate_predictions(
    prediction: CompletedPredictionPackage,
    prediction_root: Path,
    materialization: MaterializationResult,
    truth_root: Path,
) -> BatchClassificationEvaluation | BatchRegressionEvaluation:
    """Evaluate one complete prediction file with evaluator-owned truth."""
    task = materialization.model_input.task
    if task.task_id not in REVIEWED_TASK_IDS:
        raise InferenceEvaluationError(
            "reviewed_task", "evaluation is limited to reviewed defaults"
        )
    if (
        prediction.task_id != task.task_id
        or prediction.task_type != task.task_type
        or prediction.entity_column != task.entity_column
        or prediction.dataset_revision != materialization.model_input.dataset_revision
        or prediction.query_sha256 != task.query_sha256
        or prediction.materialization_package_sha256 != materialization.package_sha256
        or prediction.model_input_sha256 != materialization.model_input_sha256
    ):
        raise InferenceEvaluationError("contract_alignment", "prediction contract is misaligned")

    prediction_path = resolve_artifact(prediction_root, prediction.prediction_file)
    truth_reference = materialization.evaluator_truth.test_truth
    truth_path = resolve_artifact(truth_root, truth_reference)
    train_path = resolve_artifact(truth_root, materialization.model_input.train_labels)
    entity = _quote(task.entity_column)
    target = _quote(task.target_column)

    connection = duckdb.connect(":memory:")
    try:
        connection.from_parquet(str(prediction_path)).create_view("predictions")
        connection.from_parquet(str(truth_path)).create_view("truth")
        expected_prediction_columns = ["timestamp", task.entity_column, "prediction"]
        columns = [row[0] for row in connection.execute("DESCRIBE predictions").fetchall()]
        if columns != expected_prediction_columns:
            raise InferenceEvaluationError("prediction_schema", "prediction columns are invalid")
        duplicate = connection.execute(
            f"SELECT COUNT(*) FROM (SELECT timestamp, {entity} FROM predictions "
            f"GROUP BY timestamp, {entity} HAVING COUNT(*) > 1)"
        ).fetchone()
        if duplicate is None or int(duplicate[0]) != 0:
            raise InferenceEvaluationError("prediction_keys", "prediction keys are not unique")
        missing, extra = connection.execute(
            "SELECT (SELECT COUNT(*) FROM truth t ANTI JOIN predictions p "
            f"USING(timestamp, {entity})), "
            f"(SELECT COUNT(*) FROM predictions p ANTI JOIN truth t USING(timestamp, {entity}))"
        ).fetchone() or (1, 1)
        if int(missing) or int(extra):
            raise InferenceEvaluationError("prediction_coverage", "predictions do not cover truth")
        rows = connection.execute(
            f"SELECT CAST(t.{target} AS DOUBLE), CAST(p.prediction AS DOUBLE) "
            f"FROM truth t JOIN predictions p USING(timestamp, {entity}) ORDER BY 1, 2"
        ).fetchall()
        if not rows or any(not math.isfinite(float(value)) for row in rows for value in row):
            raise InferenceEvaluationError(
                "finite_predictions", "targets and predictions must be finite"
            )
        labels = [float(row[0]) for row in rows]
        scores = [float(row[1]) for row in rows]
        integrity_checks = [
            IntegrityCheck(
                name="sealed_truth_boundary",
                status="passed",
                detail="Truth was resolved by the trusted evaluator after predictions were sealed.",
            ),
            IntegrityCheck(
                name="prediction_artifact",
                status="passed",
                detail="Prediction size, digest, schema, keys, and full coverage were verified.",
            ),
            IntegrityCheck(
                name="relbench_evaluator_revision",
                status="passed",
                detail=f"Metric semantics pinned to RelBench {RELBENCH_EVALUATOR_REVISION}.",
            ),
        ]
        if task.task_type == "binary_classification":
            if any(value not in (0.0, 1.0) for value in labels) or any(
                value < 0 or value > 1 for value in scores
            ):
                raise InferenceEvaluationError(
                    "classification_values", "classification values are invalid"
                )
            integer_labels = [int(value) for value in labels]
            return BatchClassificationEvaluation(
                contract_version="v1",
                result_status=prediction.status,
                dataset_id="rel-hm",
                task_id=task.task_id,
                task_type="binary_classification",
                dataset_revision=prediction.dataset_revision,
                query_sha256=prediction.query_sha256,
                materialization_package_sha256=prediction.materialization_package_sha256,
                model_input_sha256=prediction.model_input_sha256,
                checkpoint=prediction.checkpoint,
                config=prediction.config,
                runtime=prediction.runtime,
                sample_count=len(rows),
                coverage=1.0,
                prediction_sha256=prediction.prediction_file.sha256,
                truth_sha256=truth_reference.sha256,
                integrity_checks=integrity_checks,
                prevalence=sum(integer_labels) / len(integer_labels),
                metrics=_classification_metrics(integer_labels, scores),
            )

        train_targets = [
            float(row[0])
            for row in connection.execute(
                f"SELECT CAST({target} AS DOUBLE) FROM read_parquet(?)", [str(train_path)]
            ).fetchall()
        ]
        return BatchRegressionEvaluation(
            contract_version="v1",
            result_status=prediction.status,
            dataset_id="rel-hm",
            task_id=task.task_id,
            task_type="regression",
            dataset_revision=prediction.dataset_revision,
            query_sha256=prediction.query_sha256,
            materialization_package_sha256=prediction.materialization_package_sha256,
            model_input_sha256=prediction.model_input_sha256,
            checkpoint=prediction.checkpoint,
            config=prediction.config,
            runtime=prediction.runtime,
            sample_count=len(rows),
            coverage=1.0,
            prediction_sha256=prediction.prediction_file.sha256,
            truth_sha256=truth_reference.sha256,
            integrity_checks=integrity_checks,
            metrics=_regression_metrics(labels, scores, train_targets),
        )
    except duckdb.Error as error:
        raise InferenceEvaluationError("duckdb_evaluation", "DuckDB rejected evaluation") from error
    finally:
        connection.close()
