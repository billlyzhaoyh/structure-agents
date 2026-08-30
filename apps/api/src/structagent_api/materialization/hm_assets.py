"""Revision-pinned RelBench H&M assets staged outside version control."""

from __future__ import annotations

import hashlib
import os
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final

from structagent_api.catalog import RELBENCH_V1_REPOSITORY, RELBENCH_V1_REVISION
from structagent_api.materialization.materializer import HMDatasetFiles
from structagent_api.materialization.task_sql import TaskId

FetchTo = Callable[[str, Path], None]


class AssetStagingError(RuntimeError):
    """Sanitized download or integrity failure."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class PinnedAsset:
    path: str
    sha256: str
    byte_count: int

    def __post_init__(self) -> None:
        path = PurePosixPath(self.path)
        if path.is_absolute() or ".." in path.parts or path.as_posix() != self.path:
            raise ValueError("asset path must be a normalized relative POSIX path")
        if len(self.sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.sha256
        ):
            raise ValueError("asset SHA-256 must contain 64 lowercase hexadecimal characters")
        if self.byte_count <= 0:
            raise ValueError("asset byte count must be positive")


REL_HM_ASSETS: Final[tuple[PinnedAsset, ...]] = (
    PinnedAsset(
        "rel-hm/db/article.parquet",
        "e119bbe9d882d1cbb6488e578b0e74a76e135b3cf51523dd6eb19ba306e53000",
        6_344_990,
    ),
    PinnedAsset(
        "rel-hm/db/customer.parquet",
        "531a89244a2dbb31008fe897eec5d262e1b25179d7b97dbd6dfcc6e7caa8e462",
        89_777_474,
    ),
    PinnedAsset(
        "rel-hm/db/transactions.parquet",
        "6d3d83a378467a02beba8e9855d2fdb6df8e8e87d4cac53c81b94a363af9559a",
        91_593_833,
    ),
    PinnedAsset(
        "rel-hm/tasks/item-sales/manifest.yaml",
        "fc3f971da007d7c17872d3c0d840ca79609af5942ebec166154d4aaf9e7a6675",
        696,
    ),
    PinnedAsset(
        "rel-hm/tasks/item-sales/train.parquet",
        "430b3dcd9ead430129d4773ab14e7f39b164d49f75ca3d48eac91799520782a2",
        21_671_305,
    ),
    PinnedAsset(
        "rel-hm/tasks/item-sales/val.parquet",
        "e414700034dd8e9c9ef49b48ccc7fa7edea1aa1c32e00635d2f5ec365758f092",
        775_013,
    ),
    PinnedAsset(
        "rel-hm/tasks/item-sales/test.parquet",
        "cdf1f7d9d62e4a9bafbe010899b3ea75406cdb8c5099e4a3f6ef30184d1c0f07",
        768_123,
    ),
    PinnedAsset(
        "rel-hm/tasks/user-churn/manifest.yaml",
        "546bef09917d3453e00bd25d356493c7dd97c9a9039fc9af37c4997fef8aa9f9",
        940,
    ),
    PinnedAsset(
        "rel-hm/tasks/user-churn/train.parquet",
        "b883a46a271db7ada278055cc490c1ab39700d1fb842db5583e1ed3bab7e81fd",
        17_225_190,
    ),
    PinnedAsset(
        "rel-hm/tasks/user-churn/val.parquet",
        "7cbc759a34467e801c6fc71521ade8330f1080a1b23de492f088a9c32efaead4",
        479_197,
    ),
    PinnedAsset(
        "rel-hm/tasks/user-churn/test.parquet",
        "dec07e46e479540a5d21f8f1edc2d6fb983e08196f57daf49385ee142379f248",
        466_867,
    ),
)


@dataclass(frozen=True)
class StagedHMAssets:
    root: Path

    @property
    def dataset(self) -> HMDatasetFiles:
        return HMDatasetFiles.from_directory(
            self.root / "rel-hm" / "db",
            revision=RELBENCH_V1_REVISION,
        )

    def expected_labels(self, task_id: TaskId) -> dict[str, Path]:
        task_name = task_id.rsplit("/", maxsplit=1)[1]
        task_root = self.root / "rel-hm" / "tasks" / task_name
        return {
            "train": task_root / "train.parquet",
            "validation": task_root / "val.parquet",
            "test": task_root / "test.parquet",
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _asset_url(asset: PinnedAsset) -> str:
    return f"{RELBENCH_V1_REPOSITORY}/resolve/{RELBENCH_V1_REVISION}/{asset.path}?download=true"


def _fetch_to(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "StructAgent/0.1"})
    with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)


def _is_valid(path: Path, asset: PinnedAsset) -> bool:
    return (
        path.is_file() and path.stat().st_size == asset.byte_count and _sha256(path) == asset.sha256
    )


def stage_hm_assets(
    cache_root: Path,
    *,
    assets: tuple[PinnedAsset, ...] = REL_HM_ASSETS,
    fetch_to: FetchTo = _fetch_to,
) -> StagedHMAssets:
    """Download missing pinned files atomically and verify every content digest."""
    revision_root = cache_root / RELBENCH_V1_REVISION
    revision_root.mkdir(parents=True, exist_ok=True)
    resolved_root = revision_root.resolve()

    for asset in assets:
        destination = revision_root / asset.path
        if not destination.resolve().is_relative_to(resolved_root):
            raise AssetStagingError("asset_path", "asset destination escapes the cache root")
        if _is_valid(destination, asset):
            continue

        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_name(destination.name + ".part")
        if partial.exists():
            partial.unlink()
        try:
            fetch_to(_asset_url(asset), partial)
            if not _is_valid(partial, asset):
                raise AssetStagingError(
                    "asset_integrity", "downloaded asset failed its pinned size or SHA-256"
                )
            os.replace(partial, destination)
        except AssetStagingError:
            raise
        except Exception as error:
            raise AssetStagingError(
                "asset_download", "failed to download a pinned asset"
            ) from error
        finally:
            if partial.exists():
                partial.unlink()

    return StagedHMAssets(root=revision_root)


def verify_hm_assets(
    cache_root: Path,
    *,
    assets: tuple[PinnedAsset, ...] = REL_HM_ASSETS,
) -> StagedHMAssets:
    """Validate an existing cache without making a network request."""
    revision_root = cache_root / RELBENCH_V1_REVISION
    invalid = [asset.path for asset in assets if not _is_valid(revision_root / asset.path, asset)]
    if invalid:
        raise AssetStagingError(
            "asset_integrity", f"{len(invalid)} pinned H&M asset(s) are missing or invalid"
        )
    return StagedHMAssets(root=revision_root)
