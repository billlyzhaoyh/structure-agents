"""Exact model-visible upload inventory for the Modal worker."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from structagent_api.contracts import MaterializationResult, MaterializedFileReference
from structagent_api.inference.artifacts import resolve_artifact


@dataclass(frozen=True)
class ModelUpload:
    """One digest-verified file and its unique worker-visible destination."""

    source: Path
    remote_path: PurePosixPath
    reference: MaterializedFileReference


def build_upload_inventory(
    materialization: MaterializationResult,
    *,
    dataset_root: Path,
    task_root: Path,
) -> tuple[ModelUpload, ...]:
    """Resolve only the seven files explicitly permitted to enter model context."""
    model = materialization.model_input
    task_name = model.task.task_id.rsplit("/", maxsplit=1)[1]
    database = sorted(model.database_files, key=lambda reference: reference.table)
    uploads = [
        ModelUpload(
            source=resolve_artifact(dataset_root, reference),
            remote_path=PurePosixPath(f"/run/input/rel-hm/db/{reference.table}.parquet"),
            reference=reference,
        )
        for reference in database
    ]
    for split, reference in (
        ("train", model.train_labels),
        ("val", model.validation_labels),
        ("test", model.test_rows),
    ):
        uploads.append(
            ModelUpload(
                source=resolve_artifact(task_root, reference),
                remote_path=PurePosixPath(f"/run/input/rel-hm/tasks/{task_name}/{split}.parquet"),
                reference=reference,
            )
        )

    remote_paths = [upload.remote_path for upload in uploads]
    if len(uploads) != 6 or len(remote_paths) != len(set(remote_paths)):
        raise ValueError("model upload inventory must contain six unique files")
    if any("truth" in str(path).lower() or path.name == "manifest.json" for path in remote_paths):
        raise ValueError("evaluator truth and run manifests cannot enter the upload inventory")
    return tuple(uploads)
