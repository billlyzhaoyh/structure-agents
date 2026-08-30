from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from structagent_api.contracts import (
    CompletedPredictionPackage,
    RTJCheckpointReference,
    RTJInferenceConfig,
    RTJInferenceRequest,
    RTJRuntimeProvenance,
)
from structagent_api.contracts.models import MaterializedFileReference
from structagent_api.inference.modal_runner import (
    MODEL_UPLOAD_ALLOWLIST,
    InferenceObservation,
    ModalExecutionPolicy,
    ModalRunnerError,
    ProjectionLedger,
    RTWorker,
    VerifiedUpload,
    build_upload_manifest,
    run_modal_inference,
)
from structagent_api.materialization import (
    SYNTHETIC_CUTOFFS,
    create_synthetic_hm,
    materialize_default_task,
)


def _request(tmp_path: Path) -> tuple[RTJInferenceRequest, tuple[Path, ...]]:
    dataset_root = tmp_path / "dataset"
    output_root = tmp_path / "output"
    dataset = create_synthetic_hm(dataset_root)
    result = materialize_default_task(
        "rel-hm/user-churn",
        dataset,
        output_root,
        cutoffs=SYNTHETIC_CUTOFFS,
    )
    return (
        RTJInferenceRequest(
            contract_version="v1",
            materialization_package_sha256=result.package_sha256,
            model_input_sha256=result.model_input_sha256,
            model_input=result.model_input,
            source_revision="455df27c1458e093eac00133d5bbf41a8263a2e3",
            checkpoint=RTJCheckpointReference(
                repository_url="https://huggingface.co/stanford-star/rt-j",
                revision="a2c204c79d493ed0056661140e6fd24db3118381",
                variant="classification",
                config_path="classification/config.json",
                weights_path="classification/model.safetensors",
                license="CC-BY-NC-SA-4.0",
            ),
            config=RTJInferenceConfig(),
        ),
        (dataset_root, output_root),
    )


def _prediction(request: RTJInferenceRequest) -> CompletedPredictionPackage:
    return CompletedPredictionPackage(
        contract_version="v1",
        status="observed",
        dataset_id="rel-hm",
        task_id=request.model_input.task.task_id,
        task_type="binary_classification",
        entity_column="customer_id",
        dataset_revision=request.model_input.dataset_revision,
        materialization_package_sha256=request.materialization_package_sha256,
        model_input_sha256=request.model_input_sha256,
        query_sha256=request.model_input.task.query_sha256,
        prediction_file=MaterializedFileReference(
            path="predictions.parquet",
            sha256="f" * 64,
            row_count=request.model_input.test_rows.row_count,
            byte_count=1,
            columns=["timestamp", "customer_id", "prediction"],
        ),
        checkpoint=request.checkpoint,
        config=request.config,
        runtime=RTJRuntimeProvenance(
            provider="modal",
            gpu="L4",
            duration_seconds=1,
            source_revision=request.source_revision,
            checkpoint_revision=request.checkpoint.revision,
        ),
    )


class FakeSession:
    def __init__(self, observations: list[InferenceObservation]) -> None:
        self.observations = observations
        self.row_limits: list[int | None] = []
        self.request_payloads: list[str] = []
        self.staged = False
        self.cleaned = False

    def stage_public_assets(self) -> None:
        self.staged = True

    def run_inference(self, request_json: str, row_limit: int | None) -> InferenceObservation:
        assert "test_truth" not in request_json
        self.request_payloads.append(request_json)
        self.row_limits.append(row_limit)
        return self.observations.pop(0)

    def cleanup(self) -> None:
        self.cleaned = True


class FakeProvider:
    def __init__(self, session: FakeSession) -> None:
        self.session = session
        self.uploads: tuple[VerifiedUpload, ...] = ()
        self.policy: ModalExecutionPolicy | None = None

    def create_ephemeral_session(
        self,
        *,
        uploads: tuple[VerifiedUpload, ...],
        policy: ModalExecutionPolicy,
        worker: RTWorker,
    ) -> FakeSession:
        del worker
        self.uploads = uploads
        self.policy = policy
        return self.session


def _worker(request_json: str, row_limit: int | None) -> dict[str, object]:
    del request_json, row_limit
    return {}


def test_runner_uploads_only_verified_model_files_and_applies_modal_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, roots = _request(tmp_path)
    credential_values = ("openai-secret", "daytona-secret", "modal-id", "modal-secret")
    for name, value in zip(
        ("OPENAI_API_KEY", "DAYTONA_API_KEY", "MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET"),
        credential_values,
        strict=True,
    ):
        monkeypatch.setenv(name, value)
    preflight_rows = min(512, request.model_input.test_rows.row_count)
    session = FakeSession(
        [
            InferenceObservation(preflight_rows, Decimal("1"), Decimal("0.10")),
            InferenceObservation(
                request.model_input.test_rows.row_count,
                Decimal("2"),
                Decimal("0.20"),
                _prediction(request),
            ),
        ]
    )
    provider = FakeProvider(session)

    result = run_modal_inference(request, roots, provider, _worker, ProjectionLedger())

    assert {upload.remote_name for upload in provider.uploads} == MODEL_UPLOAD_ALLOWLIST
    assert "manifest.json" not in {upload.remote_name for upload in provider.uploads}
    assert "test-truth.parquet" not in {upload.remote_name for upload in provider.uploads}
    assert provider.policy == ModalExecutionPolicy()
    assert provider.policy.ephemeral_app and provider.policy.anonymous_volume
    assert provider.policy.asset_staging_network_enabled
    assert provider.policy.gpu == "L4"
    assert (provider.policy.cpu, provider.policy.memory_mib) == (8, 32 * 1024)
    assert provider.policy.block_network and provider.policy.restrict_modal_access
    assert provider.policy.single_use_container
    assert not provider.policy.deploy and not provider.policy.named_volume
    assert not provider.policy.modal_secret
    assert session.row_limits == [preflight_rows, None]
    assert all(
        secret not in payload
        for payload in session.request_payloads
        for secret in credential_values
    )
    assert session.staged and session.cleaned and result.cleanup_confirmed


def test_upload_manifest_rejects_changed_file(tmp_path: Path) -> None:
    request, roots = _request(tmp_path)
    with (roots[1] / "test.parquet").open("ab") as handle:
        handle.write(b"changed")

    with pytest.raises(ModalRunnerError, match="size or SHA"):
        build_upload_manifest(roots, request)


@pytest.mark.parametrize(
    ("preflight_cost", "ledger", "code"),
    [
        (Decimal("24"), ProjectionLedger(), "projected_cost"),
        (Decimal("1"), ProjectionLedger(estimated_cost_usd=Decimal("24.5")), "combined_cost"),
        (
            Decimal("1"),
            ProjectionLedger(duration_seconds=Decimal(16 * 60 * 60)),
            "combined_duration",
        ),
    ],
)
def test_projection_gates_fail_closed_and_cleanup(
    tmp_path: Path,
    preflight_cost: Decimal,
    ledger: ProjectionLedger,
    code: str,
) -> None:
    request, roots = _request(tmp_path)
    rows = min(512, request.model_input.test_rows.row_count)
    session = FakeSession([InferenceObservation(rows, Decimal("1"), preflight_cost)])

    with pytest.raises(ModalRunnerError) as error:
        run_modal_inference(request, roots, FakeProvider(session), _worker, ledger)

    assert error.value.code == code
    assert session.cleaned
    assert session.row_limits == [rows]


def test_cleanup_runs_when_remote_inference_fails(tmp_path: Path) -> None:
    request, roots = _request(tmp_path)

    class FailingSession(FakeSession):
        def run_inference(self, request_json: str, row_limit: int | None) -> InferenceObservation:
            del request_json, row_limit
            raise RuntimeError("remote failed")

    session = FailingSession([])
    with pytest.raises(RuntimeError, match="remote failed"):
        run_modal_inference(request, roots, FakeProvider(session), _worker, ProjectionLedger())

    assert session.cleaned


def test_preflight_covering_the_full_cohort_is_not_repeated(tmp_path: Path) -> None:
    request, roots = _request(tmp_path)
    rows = request.model_input.test_rows.row_count
    session = FakeSession(
        [
            InferenceObservation(
                rows,
                Decimal("1"),
                Decimal("0.01"),
                _prediction(request),
            )
        ]
    )

    result = run_modal_inference(
        request,
        roots,
        FakeProvider(session),
        _worker,
        ProjectionLedger(),
    )

    assert result.prediction.task_id == request.model_input.task.task_id
    assert session.row_limits == [rows]
    assert session.cleaned


def test_cleanup_runs_when_public_asset_staging_fails(tmp_path: Path) -> None:
    request, roots = _request(tmp_path)

    class FailingStageSession(FakeSession):
        def stage_public_assets(self) -> None:
            raise RuntimeError("staging failed")

    session = FailingStageSession([])
    with pytest.raises(RuntimeError, match="staging failed"):
        run_modal_inference(request, roots, FakeProvider(session), _worker, ProjectionLedger())

    assert session.cleaned


def test_prediction_alignment_failure_is_cleaned_up(tmp_path: Path) -> None:
    request, roots = _request(tmp_path)
    wrong = _prediction(request).model_copy(update={"query_sha256": "0" * 64})
    rows = min(512, request.model_input.test_rows.row_count)
    session = FakeSession(
        [
            InferenceObservation(rows, Decimal("1"), Decimal("0.01")),
            InferenceObservation(rows, Decimal("1"), Decimal("0.01"), wrong),
        ]
    )

    with pytest.raises(ModalRunnerError) as error:
        run_modal_inference(request, roots, FakeProvider(session), _worker, ProjectionLedger())

    assert error.value.code == "prediction_alignment"
    assert session.cleaned
