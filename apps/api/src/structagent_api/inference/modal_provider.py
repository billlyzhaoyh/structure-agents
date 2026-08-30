"""Concrete private Modal adapter for the sealed RT-J controller."""

from __future__ import annotations

import os
import time
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from structagent_api.contracts import (
    CompletedPredictionPackage,
    RTJInferenceRequest,
    RTJRuntimeProvenance,
)
from structagent_api.contracts.models import MaterializedFileReference
from structagent_api.inference.artifacts import sha256_file
from structagent_api.inference.modal_runner import (
    InferenceObservation,
    ModalExecutionPolicy,
    ModalProvider,
    ModalRunnerError,
    ModalSession,
    RTWorker,
    VerifiedUpload,
)

MOUNT_ROOT = "/mnt/structagent"
SOURCE_REPOSITORY = "https://github.com/stanford-star/relational-transformer.git"
SOURCE_REVISION = "455df27c1458e093eac00133d5bbf41a8263a2e3"
CHECKPOINT_REPOSITORY = "stanford-star/rt-j"
CHECKPOINT_REVISION = "a2c204c79d493ed0056661140e6fd24db3118381"
EMBEDDING_REPOSITORY = "sentence-transformers/all-MiniLM-L12-v2"
EMBEDDING_REVISION = "a50ef00143b4d5391434df20ae11632588ac25be"

# L4 + 8 requested physical CPU cores + 32 GiB at Modal's 2026-08-30 rates is
# USD 0.00039784/s. This deliberately rounded-up rate keeps admission conservative.
CONSERVATIVE_INFERENCE_USD_PER_SECOND = Decimal("0.00050")

_RUNTIME_PACKAGES = (
    "duckdb==1.5.5",
    "einops==0.8.2",
    "huggingface-hub==1.28.0",
    "lazy-loader==0.5",
    "maturin==1.14.1",
    "ml-dtypes==0.6.0",
    "numpy==2.5.2",
    "orjson==3.12.0",
    "pandas==3.0.5",
    "pyyaml==6.0.3",
    "safetensors==0.8.0",
    "scikit-learn==1.5.2",
    "scipy==1.18.1",
    "sentence-transformers==6.0.0",
    "torch==2.13.0",
    "tqdm==4.70.0",
    "transformers==5.15.1",
)


def _runtime_image(modal: Any) -> Any:
    repository_root = Path(__file__).resolve().parents[5]
    image = (
        modal.Image.debian_slim("3.12")
        .apt_install("build-essential", "curl", "git")
        .run_commands("curl -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal")
        .env(
            {
                "CARGO_HOME": "/root/.cargo",
                "HF_HUB_DISABLE_TELEMETRY": "1",
                "PATH": "/root/.cargo/bin:/usr/local/bin:/usr/bin:/bin",
                "PIP_DISABLE_PIP_VERSION_CHECK": "1",
                "PIP_NO_INPUT": "1",
            }
        )
        .pip_install(*_RUNTIME_PACKAGES)
        .add_local_dir(repository_root / "workers", "/root/workers", copy=True)
    )
    return image


def _volume_destination(task_name: str, upload: VerifiedUpload) -> str:
    if upload.remote_name in {"article.parquet", "customer.parquet", "transactions.parquet"}:
        return f"/input/rel-hm/db/{upload.remote_name}"
    split_name = {"validation.parquet": "val.parquet"}.get(upload.remote_name, upload.remote_name)
    return f"/input/rel-hm/tasks/{task_name}/{split_name}"


def _exit_sync_context(context: Any) -> None:
    # Modal's synchronicity-generated context wrappers do not publish typed __exit__ methods.
    context.__exit__(None, None, None)


class EphemeralModalProvider(ModalProvider):
    """Create one anonymous volume and one undeployed app for a single task."""

    def __init__(
        self,
        *,
        task_name: str,
        checkpoint_variant: Literal["classification", "regression"],
        prediction_root: Path,
    ) -> None:
        if task_name not in {"user-churn", "item-sales"}:
            raise ValueError("Modal RT-J is limited to the two reviewed task names")
        self._task_name = task_name
        self._checkpoint_variant = checkpoint_variant
        self._prediction_root = prediction_root

    def create_ephemeral_session(
        self,
        *,
        uploads: tuple[VerifiedUpload, ...],
        policy: ModalExecutionPolicy,
        worker: RTWorker,
    ) -> ModalSession:
        if policy != ModalExecutionPolicy():
            raise ModalRunnerError("modal_policy", "Modal execution policy was changed.")
        if (getattr(worker, "__module__", None), getattr(worker, "__name__", None)) != (
            "workers.rtj.runtime",
            "run_task_inference",
        ):
            raise ModalRunnerError("worker_identity", "The approved RT-J worker was changed.")
        return _EphemeralModalSession(
            uploads=uploads,
            policy=policy,
            task_name=self._task_name,
            checkpoint_variant=self._checkpoint_variant,
            prediction_root=self._prediction_root,
        )


class _EphemeralModalSession:
    def __init__(
        self,
        *,
        uploads: tuple[VerifiedUpload, ...],
        policy: ModalExecutionPolicy,
        task_name: str,
        checkpoint_variant: Literal["classification", "regression"],
        prediction_root: Path,
    ) -> None:
        try:
            import modal
        except ImportError as error:  # pragma: no cover - live dependency gate
            raise ModalRunnerError(
                "modal_dependency", "The pinned Modal SDK is unavailable."
            ) from error

        self._task_name = task_name
        self._checkpoint_variant = checkpoint_variant
        self._prediction_root = prediction_root
        self._run_count = 0
        self._cleaned = False
        self._volume_context: Any = modal.Volume.ephemeral()
        self._volume = self._volume_context.__enter__()
        self._app_context: Any | None = None

        try:
            with self._volume.batch_upload() as batch:
                for upload in uploads:
                    batch.put_file(
                        upload.local_path,
                        _volume_destination(task_name, upload),
                    )
            self._app = modal.App("structagent-rtj-private")
            image = _runtime_image(modal)
            volume = self._volume

            @self._app.function(
                image=image,
                volumes={MOUNT_ROOT: volume},
                cpu=4,
                memory=8 * 1024,
                timeout=30 * 60,
                block_network=False,
                restrict_modal_access=True,
                single_use_containers=True,
                serialized=True,
            )
            def stage_assets(variant: str) -> dict[str, str]:
                import os
                import subprocess
                import sys
                from pathlib import Path

                from huggingface_hub import snapshot_download  # type: ignore[import-not-found]

                assets = Path(MOUNT_ROOT) / "assets"
                source = assets / "relational-transformer"
                site_packages = assets / "site-packages"
                checkpoint = assets / "checkpoint"
                hf_cache = assets / "hf" / "hub"
                assets.mkdir(parents=True, exist_ok=False)
                subprocess.run(
                    ["git", "clone", "--filter=blob:none", SOURCE_REPOSITORY, str(source)],
                    check=True,
                    stdout=subprocess.DEVNULL,
                )
                subprocess.run(
                    ["git", "-C", str(source), "checkout", "--detach", SOURCE_REVISION],
                    check=True,
                    stdout=subprocess.DEVNULL,
                )
                observed_revision = subprocess.run(
                    ["git", "-C", str(source), "rev-parse", "HEAD"],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip()
                if observed_revision != SOURCE_REVISION:
                    raise RuntimeError("source revision mismatch")
                environment = os.environ.copy()
                environment["PATH"] = "/root/.cargo/bin:" + environment["PATH"]
                subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "pip",
                        "install",
                        "--no-build-isolation",
                        "--no-deps",
                        "--target",
                        str(site_packages),
                        str(source),
                    ],
                    check=True,
                    env=environment,
                    stdout=subprocess.DEVNULL,
                )
                snapshot_download(
                    repo_id=CHECKPOINT_REPOSITORY,
                    revision=CHECKPOINT_REVISION,
                    allow_patterns=[f"{variant}/*"],
                    local_dir=checkpoint,
                )
                snapshot_download(
                    repo_id=EMBEDDING_REPOSITORY,
                    revision=EMBEDDING_REVISION,
                    cache_dir=hf_cache,
                )
                embedding_cache = hf_cache / "models--sentence-transformers--all-MiniLM-L12-v2"
                refs = embedding_cache / "refs"
                refs.mkdir(parents=True, exist_ok=True)
                (refs / "main").write_text(EMBEDDING_REVISION, encoding="utf-8")
                required = (
                    checkpoint / variant / "config.json",
                    checkpoint / variant / "model.safetensors",
                )
                rust_extensions = list((site_packages / "rt").glob("_rustler*.so"))
                if len(rust_extensions) != 1 or not all(path.is_file() for path in required):
                    raise RuntimeError("staged RT-J assets are incomplete")
                volume.commit()
                return {
                    "checkpoint_revision": CHECKPOINT_REVISION,
                    "embedding_revision": EMBEDDING_REVISION,
                    "source_revision": observed_revision,
                }

            @self._app.function(
                image=image,
                volumes={MOUNT_ROOT: volume},
                gpu=policy.gpu,
                cpu=policy.cpu,
                memory=policy.memory_mib,
                timeout=60 * 60,
                block_network=policy.block_network,
                restrict_modal_access=policy.restrict_modal_access,
                single_use_containers=policy.single_use_container,
                serialized=True,
                env={
                    "HF_HOME": f"{MOUNT_ROOT}/assets/hf",
                    "HF_HUB_DISABLE_TELEMETRY": "1",
                    "HF_HUB_OFFLINE": "1",
                    "TRANSFORMERS_OFFLINE": "1",
                },
            )
            def infer(request_json: str, row_limit: int | None, run_name: str) -> dict[str, Any]:
                import json
                import sys

                sys.path.insert(0, f"{MOUNT_ROOT}/assets/site-packages")
                sys.path.insert(0, "/root")
                from workers.rtj.runtime import run_task_inference

                result = run_task_inference(
                    f"{MOUNT_ROOT}/input",
                    f"{MOUNT_ROOT}/{run_name}",
                    f"{MOUNT_ROOT}/assets",
                    json.loads(request_json),
                    row_limit,
                )
                volume.commit()
                return result

            self._stage_assets = stage_assets
            self._infer = infer
            self._app_context = self._app.run(name="structagent-rtj-private")
            self._app_context.__enter__()
        except BaseException:
            _exit_sync_context(self._volume_context)
            raise

    def stage_public_assets(self) -> None:
        result: dict[str, str] = self._stage_assets.remote(self._checkpoint_variant)
        if result != {
            "checkpoint_revision": CHECKPOINT_REVISION,
            "embedding_revision": EMBEDDING_REVISION,
            "source_revision": SOURCE_REVISION,
        }:
            raise ModalRunnerError("asset_staging", "Modal staged unexpected RT-J assets.")

    def run_inference(self, request_json: str, row_limit: int | None) -> InferenceObservation:
        request = RTJInferenceRequest.model_validate_json(request_json)
        if request.checkpoint.variant != self._checkpoint_variant:
            raise ModalRunnerError("checkpoint_variant", "Modal checkpoint variant is misaligned.")
        self._run_count += 1
        run_name = f"inference-{self._run_count}"
        started = time.monotonic()
        raw: dict[str, Any] = self._infer.remote(request_json, row_limit, run_name)
        elapsed = time.monotonic() - started
        reference = MaterializedFileReference.model_validate(raw.get("prediction_file"))
        remote_path = f"/{run_name}/outputs/{self._task_name}/predictions.parquet"
        self._prediction_root.mkdir(parents=True, exist_ok=True)
        prediction_path = self._prediction_root / "predictions.parquet"
        partial_path = prediction_path.with_suffix(".parquet.part")
        with partial_path.open("wb") as output:
            for chunk in self._volume.read_file(remote_path):
                output.write(chunk)
        if (
            partial_path.stat().st_size != reference.byte_count
            or sha256_file(partial_path) != reference.sha256
        ):
            partial_path.unlink(missing_ok=True)
            raise ModalRunnerError("prediction_download", "Modal prediction integrity failed.")
        os.replace(partial_path, prediction_path)
        prediction = CompletedPredictionPackage(
            contract_version="v1",
            status="observed",
            dataset_id="rel-hm",
            task_id=request.model_input.task.task_id,
            task_type=request.model_input.task.task_type,
            entity_column=request.model_input.task.entity_column,
            dataset_revision=request.model_input.dataset_revision,
            materialization_package_sha256=request.materialization_package_sha256,
            model_input_sha256=request.model_input_sha256,
            query_sha256=request.model_input.task.query_sha256,
            prediction_file=reference,
            checkpoint=request.checkpoint,
            config=request.config,
            runtime=RTJRuntimeProvenance(
                provider="modal",
                gpu="L4",
                duration_seconds=float(raw["duration_seconds"]),
                source_revision=request.source_revision,
                checkpoint_revision=request.checkpoint.revision,
            ),
        )
        return InferenceObservation(
            processed_rows=reference.row_count,
            duration_seconds=Decimal(str(elapsed)),
            estimated_cost_usd=Decimal(str(elapsed)) * CONSERVATIVE_INFERENCE_USD_PER_SECOND,
            prediction=prediction,
        )

    def cleanup(self) -> None:
        if self._cleaned:
            return
        self._cleaned = True
        app_error: BaseException | None = None
        try:
            if self._app_context is not None:
                _exit_sync_context(self._app_context)
        except BaseException as error:
            app_error = error
        try:
            _exit_sync_context(self._volume_context)
        except BaseException as error:
            raise ModalRunnerError("volume_cleanup", "Modal volume cleanup failed.") from error
        if app_error is not None:
            raise ModalRunnerError("app_cleanup", "Modal app cleanup failed.") from app_error
