"""Immutable, digest-verified storage for terminal simulation artifacts."""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import Field

from structagent_api.contracts.models import StrictModel
from structagent_api.contracts.simulation import (
    ContractDigest,
    SimulationRunResult,
    canonical_contract_json,
    contract_digest,
)


class SimulationCacheError(RuntimeError):
    """A sanitized missing, stale, or invalid cache failure."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


class SimulationCacheIdentity(StrictModel):
    """Every versioned input that invalidates a cached result."""

    schema_version: Literal["1"] = "1"
    study_digest: ContractDigest = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    dataset_revision: str = Field(min_length=1)
    dataset_manifest_digest: ContractDigest = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    trait_query_digest: ContractDigest = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    prompt_template_digest: ContractDigest = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    respondent_model_id: str = Field(min_length=1)
    respondent_model_version: str = Field(min_length=1)
    edsl_version: str = Field(min_length=1)
    estimator_version: str = Field(min_length=1)
    validation_version: str = Field(min_length=1)
    worker_version: str = Field(min_length=1)
    certification_digest: ContractDigest = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    random_seed: int = Field(ge=0, le=2**32 - 1)


class SimulationCacheManifest(StrictModel):
    """Canonical manifest stored beside one immutable terminal result."""

    schema_version: Literal["1"] = "1"
    cache_key: ContractDigest = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    result_digest: ContractDigest = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    study_artifact_id: str = Field(min_length=1)
    created_at: datetime
    identity: SimulationCacheIdentity


class SimulationCachePointer(StrictModel):
    """Small atomic pointer to the current reviewed artifact."""

    schema_version: Literal["1"] = "1"
    study_artifact_id: str = Field(min_length=1)
    cache_key: ContractDigest = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class VerifiedSimulationArtifact(StrictModel):
    """Validated cache evidence returned to the trusted API or verifier."""

    manifest: SimulationCacheManifest
    result: SimulationRunResult


def _canonical_bytes(model: StrictModel) -> bytes:
    return (canonical_contract_json(model) + "\n").encode()


def _artifact_directory(root: Path, cache_key: str) -> Path:
    return root / cache_key.removeprefix("sha256:")


def _pointer_path(root: Path, study_artifact_id: str) -> Path:
    safe_name = study_artifact_id.replace("/", "__")
    if not safe_name or any(
        character not in "abcdefghijklmnopqrstuvwxyz0123456789-_." for character in safe_name
    ):
        raise SimulationCacheError("cache_study_id", "simulation study identity is invalid")
    return root / f"{safe_name}.latest.json"


def _read_canonical(path: Path, model_type: type[StrictModel]) -> StrictModel:
    try:
        contents = path.read_bytes()
        model = model_type.model_validate_json(contents)
    except (OSError, ValueError) as error:
        raise SimulationCacheError(
            "simulation_result_unavailable", "verified simulation result is unavailable"
        ) from error
    if contents != _canonical_bytes(model):
        raise SimulationCacheError(
            "simulation_result_unavailable", "verified simulation result is unavailable"
        )
    return model


def promote_simulation_result(
    root: Path,
    result: SimulationRunResult,
    identity: SimulationCacheIdentity,
    *,
    created_at: datetime | None = None,
) -> VerifiedSimulationArtifact:
    """Atomically store and promote one validated canonical terminal result."""
    provenance = result.provenance
    compared = {
        "study_digest": provenance.study_digest,
        "dataset_revision": provenance.dataset_revision,
        "dataset_manifest_digest": provenance.dataset_manifest_digest,
        "trait_query_digest": provenance.trait_query_digest,
        "prompt_template_digest": provenance.prompt_template_digest,
        "respondent_model_id": provenance.respondent_model_id,
        "respondent_model_version": provenance.respondent_model_version,
        "edsl_version": provenance.edsl_version,
        "certification_digest": provenance.certification_digest,
        "random_seed": provenance.random_seed,
    }
    if any(getattr(identity, key) != value for key, value in compared.items()):
        raise SimulationCacheError(
            "cache_identity", "result provenance does not match its cache identity"
        )

    root.mkdir(parents=True, exist_ok=True)
    cache_key = contract_digest(identity)
    manifest = SimulationCacheManifest(
        cache_key=cache_key,
        result_digest=contract_digest(result),
        study_artifact_id=result.study_artifact_id,
        created_at=created_at or datetime.now(UTC),
        identity=identity,
    )
    destination = _artifact_directory(root, cache_key)
    if not destination.exists():
        temporary = Path(tempfile.mkdtemp(prefix=".simulation-", dir=root))
        try:
            (temporary / "result.json").write_bytes(_canonical_bytes(result))
            (temporary / "manifest.json").write_bytes(_canonical_bytes(manifest))
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                for child in temporary.iterdir():
                    child.unlink()
                temporary.rmdir()

    pointer = SimulationCachePointer(
        study_artifact_id=result.study_artifact_id,
        cache_key=cache_key,
    )
    pointer_path = _pointer_path(root, result.study_artifact_id)
    pointer_temporary = pointer_path.with_suffix(".tmp")
    pointer_temporary.write_bytes(_canonical_bytes(pointer))
    os.replace(pointer_temporary, pointer_path)
    return verify_simulation_result(root, result.study_artifact_id)


def verify_simulation_result(root: Path, study_artifact_id: str) -> VerifiedSimulationArtifact:
    """Read the current artifact and reject canonical, digest, or identity drift."""

    pointer = _read_canonical(_pointer_path(root, study_artifact_id), SimulationCachePointer)
    assert isinstance(pointer, SimulationCachePointer)
    if pointer.study_artifact_id != study_artifact_id:
        raise SimulationCacheError(
            "simulation_result_unavailable", "verified simulation result is unavailable"
        )
    artifact_root = _artifact_directory(root, pointer.cache_key)
    manifest = _read_canonical(artifact_root / "manifest.json", SimulationCacheManifest)
    result = _read_canonical(artifact_root / "result.json", SimulationRunResult)
    assert isinstance(manifest, SimulationCacheManifest)
    assert isinstance(result, SimulationRunResult)
    if (
        manifest.cache_key != pointer.cache_key
        or manifest.cache_key != contract_digest(manifest.identity)
        or manifest.result_digest != contract_digest(result)
        or manifest.study_artifact_id != study_artifact_id
        or result.study_artifact_id != study_artifact_id
    ):
        raise SimulationCacheError(
            "simulation_result_unavailable", "verified simulation result is unavailable"
        )
    return VerifiedSimulationArtifact(manifest=manifest, result=result)
