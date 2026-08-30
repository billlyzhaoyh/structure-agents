"""Guarded controller for ephemeral Modal RT-J inference sessions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Literal, Protocol

from structagent_api.contracts import CompletedPredictionPackage, RTJInferenceRequest
from structagent_api.contracts.models import MaterializedFileReference

MODEL_UPLOAD_ALLOWLIST = frozenset(
    {
        "article.parquet",
        "customer.parquet",
        "transactions.parquet",
        "train.parquet",
        "validation.parquet",
        "test.parquet",
    }
)
PREFLIGHT_ROWS = 512
SAFETY_FACTOR = Decimal("1.5")
PROJECTED_COST_GATE_USD = Decimal("23")
MAX_COMBINED_COST_USD = Decimal("25")
MAX_COMBINED_DURATION_SECONDS = Decimal(16 * 60 * 60)
APPROVED_MODAL_GPUS = ("L4", "L40S")


class ModalRunnerError(RuntimeError):
    """Sanitized failure at the Modal controller boundary."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class ModalExecutionPolicy:
    """The fixed provider policy an implementation must apply."""

    ephemeral_app: bool = True
    anonymous_volume: bool = True
    deploy: bool = False
    named_volume: bool = False
    modal_secret: bool = False
    asset_staging_network_enabled: bool = True
    gpu: Literal["L4", "L40S"] = "L4"
    cpu: int = 8
    memory_mib: int = 32 * 1024
    block_network: bool = True
    restrict_modal_access: bool = True
    single_use_container: bool = True


@dataclass(frozen=True)
class VerifiedUpload:
    remote_name: str
    local_path: Path
    byte_count: int
    sha256: str


@dataclass(frozen=True)
class InferenceObservation:
    processed_rows: int
    duration_seconds: Decimal
    estimated_cost_usd: Decimal
    prediction: CompletedPredictionPackage | None = None


@dataclass(frozen=True)
class Projection:
    duration_seconds: Decimal
    estimated_cost_usd: Decimal


@dataclass
class ProjectionLedger:
    """Combined admission budget shared by the two reviewed default tasks."""

    duration_seconds: Decimal = Decimal(0)
    estimated_cost_usd: Decimal = Decimal(0)


@dataclass(frozen=True)
class ModalRunResult:
    prediction: CompletedPredictionPackage
    projection: Projection
    cleanup_confirmed: bool


class RTWorker(Protocol):
    """Injectable RT worker body owned by the separate worker slice."""

    def __call__(self, request_json: str, row_limit: int | None) -> dict[str, object]: ...


class ModalSession(Protocol):
    """One ephemeral App and anonymous Volume lifecycle."""

    def stage_public_assets(self) -> None: ...

    def run_inference(self, request_json: str, row_limit: int | None) -> InferenceObservation: ...

    def cleanup(self) -> None: ...


class ModalProvider(Protocol):
    """Fakeable provider boundary; implementations must not deploy persistent resources."""

    def create_ephemeral_session(
        self,
        *,
        uploads: tuple[VerifiedUpload, ...],
        policy: ModalExecutionPolicy,
        worker: RTWorker,
    ) -> ModalSession: ...


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _references(request: RTJInferenceRequest) -> list[MaterializedFileReference]:
    model_input = request.model_input
    return [
        *model_input.database_files,
        model_input.train_labels,
        model_input.validation_labels,
        model_input.test_rows,
    ]


def build_upload_manifest(
    roots: tuple[Path, ...], request: RTJInferenceRequest
) -> tuple[VerifiedUpload, ...]:
    """Resolve and verify exactly the six model-visible files."""
    rendered = json.dumps(
        request.model_input.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if hashlib.sha256(rendered).hexdigest() != request.model_input_sha256:
        raise ModalRunnerError("model_input_digest", "Model input metadata digest is invalid.")

    references = _references(request)
    if {reference.path for reference in references} != MODEL_UPLOAD_ALLOWLIST:
        raise ModalRunnerError("upload_allowlist", "Model uploads do not match the allowlist.")

    resolved_roots = tuple(root.resolve(strict=True) for root in roots)
    uploads: list[VerifiedUpload] = []
    for reference in references:
        candidates = [
            candidate for root in resolved_roots if (candidate := (root / reference.path)).is_file()
        ]
        if len(candidates) != 1:
            raise ModalRunnerError("upload_path", "A model upload is missing or ambiguous.")
        path = candidates[0].resolve(strict=True)
        if not any(path.is_relative_to(root) for root in resolved_roots):
            raise ModalRunnerError("upload_path", "A model upload is outside its declared roots.")
        if path.stat().st_size != reference.byte_count or _sha256(path) != reference.sha256:
            raise ModalRunnerError(
                "upload_integrity", "A model upload failed size or SHA validation."
            )
        uploads.append(
            VerifiedUpload(
                remote_name=reference.path,
                local_path=path,
                byte_count=reference.byte_count,
                sha256=reference.sha256,
            )
        )
    return tuple(sorted(uploads, key=lambda upload: upload.remote_name))


def _projection(preflight: InferenceObservation, total_rows: int) -> Projection:
    if preflight.processed_rows < 1 or preflight.processed_rows > min(PREFLIGHT_ROWS, total_rows):
        raise ModalRunnerError("preflight_rows", "Preflight returned an invalid row count.")
    if preflight.duration_seconds <= 0 or preflight.estimated_cost_usd < 0:
        raise ModalRunnerError("preflight_evidence", "Preflight timing or cost is invalid.")
    scale = Decimal(total_rows) / Decimal(preflight.processed_rows)
    return Projection(
        duration_seconds=preflight.duration_seconds * scale * SAFETY_FACTOR,
        estimated_cost_usd=preflight.estimated_cost_usd * scale * SAFETY_FACTOR,
    )


def _admit(projection: Projection, ledger: ProjectionLedger) -> None:
    if projection.estimated_cost_usd > PROJECTED_COST_GATE_USD:
        raise ModalRunnerError("projected_cost", "Projected task cost exceeds USD 23.")
    combined_duration = ledger.duration_seconds + projection.duration_seconds
    combined_cost = ledger.estimated_cost_usd + projection.estimated_cost_usd
    if combined_duration > MAX_COMBINED_DURATION_SECONDS:
        raise ModalRunnerError("combined_duration", "Combined projection exceeds 16 hours.")
    if combined_cost > MAX_COMBINED_COST_USD:
        raise ModalRunnerError("combined_cost", "Combined projection exceeds USD 25.")
    ledger.duration_seconds = combined_duration
    ledger.estimated_cost_usd = combined_cost


def run_modal_inference(
    request: RTJInferenceRequest,
    artifact_roots: tuple[Path, ...],
    provider: ModalProvider,
    worker: RTWorker,
    ledger: ProjectionLedger,
    *,
    policy: ModalExecutionPolicy | None = None,
) -> ModalRunResult:
    """Preflight, budget, and run one task within an ephemeral provider session."""
    uploads = build_upload_manifest(artifact_roots, request)
    selected_policy = policy or ModalExecutionPolicy()
    if request.config.gpu != selected_policy.gpu:
        raise ModalRunnerError("gpu_alignment", "Requested and allocated GPUs do not match.")
    session = provider.create_ephemeral_session(
        uploads=uploads, policy=selected_policy, worker=worker
    )
    request_json = request.model_dump_json()
    result: ModalRunResult | None = None
    failure: BaseException | None = None
    try:
        session.stage_public_assets()
        total_rows = request.model_input.test_rows.row_count
        preflight = session.run_inference(request_json, min(PREFLIGHT_ROWS, total_rows))
        projection = _projection(preflight, total_rows)
        _admit(projection, ledger)
        prediction: CompletedPredictionPackage | None
        if preflight.processed_rows == total_rows and preflight.prediction is not None:
            prediction = preflight.prediction
        else:
            full = session.run_inference(request_json, None)
            prediction = full.prediction
        if prediction is None:
            raise ModalRunnerError("prediction_missing", "Modal returned no sealed prediction.")
        if (
            prediction.task_id != request.model_input.task.task_id
            or prediction.materialization_package_sha256 != request.materialization_package_sha256
            or prediction.model_input_sha256 != request.model_input_sha256
            or prediction.query_sha256 != request.model_input.task.query_sha256
        ):
            raise ModalRunnerError(
                "prediction_alignment", "Modal prediction metadata is misaligned."
            )
        result = ModalRunResult(
            prediction=prediction,
            projection=projection,
            cleanup_confirmed=True,
        )
    except BaseException as error:
        failure = error
    try:
        session.cleanup()
    except BaseException as error:
        raise ModalRunnerError("cleanup", "Modal ephemeral cleanup failed.") from error
    if failure is not None:
        raise failure
    if result is None:  # pragma: no cover - guarded by result construction or failure
        raise ModalRunnerError("prediction_missing", "Modal returned no result.")
    return result
