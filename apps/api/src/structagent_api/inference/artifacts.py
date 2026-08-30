"""Content-addressed file resolution for private inference artifacts."""

from __future__ import annotations

import hashlib
from pathlib import Path

from structagent_api.contracts import MaterializedFileReference


class InferenceArtifactError(RuntimeError):
    """Sanitized artifact validation failure."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_artifact(root: Path, reference: MaterializedFileReference) -> Path:
    """Resolve and verify one contract-addressed file below an explicit root."""
    resolved_root = root.resolve(strict=True)
    path = (resolved_root / reference.path).resolve(strict=True)
    if not path.is_relative_to(resolved_root) or not path.is_file():
        raise InferenceArtifactError("artifact_path", "artifact is outside its declared root")
    if path.stat().st_size != reference.byte_count or sha256_file(path) != reference.sha256:
        raise InferenceArtifactError("artifact_integrity", "artifact size or digest is invalid")
    return path
