from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from structagent_api.materialization.hm_assets import (
    AssetStagingError,
    PinnedAsset,
    stage_hm_assets,
    verify_hm_assets,
)


def pinned(path: str, contents: bytes) -> PinnedAsset:
    return PinnedAsset(
        path=path,
        sha256=hashlib.sha256(contents).hexdigest(),
        byte_count=len(contents),
    )


def test_stage_assets_is_atomic_verified_and_idempotent(tmp_path: Path) -> None:
    payloads = {
        "rel-hm/db/article.parquet": b"article",
        "rel-hm/db/customer.parquet": b"customer",
    }
    assets = tuple(pinned(path, contents) for path, contents in payloads.items())
    calls: list[str] = []

    def fetch_to(url: str, destination: Path) -> None:
        calls.append(url)
        path = next(path for path in payloads if path in url)
        destination.write_bytes(payloads[path])

    first = stage_hm_assets(tmp_path, assets=assets, fetch_to=fetch_to)
    second = stage_hm_assets(tmp_path, assets=assets, fetch_to=fetch_to)

    assert first == second
    assert len(calls) == 2
    assert verify_hm_assets(tmp_path, assets=assets) == first
    assert not list(tmp_path.rglob("*.part"))


def test_stage_assets_removes_failed_partial_download(tmp_path: Path) -> None:
    asset = pinned("rel-hm/db/article.parquet", b"expected")

    def fetch_to(_url: str, destination: Path) -> None:
        destination.write_bytes(b"wrong")

    with pytest.raises(AssetStagingError) as raised:
        stage_hm_assets(tmp_path, assets=(asset,), fetch_to=fetch_to)

    assert raised.value.code == "asset_integrity"
    assert not list(tmp_path.rglob("*.part"))
    assert not list(tmp_path.rglob("article.parquet"))


def test_stage_assets_sanitizes_fetch_failures(tmp_path: Path) -> None:
    asset = pinned("rel-hm/db/article.parquet", b"expected")

    def fetch_to(_url: str, _destination: Path) -> None:
        raise RuntimeError("secret provider detail")

    with pytest.raises(AssetStagingError) as raised:
        stage_hm_assets(tmp_path, assets=(asset,), fetch_to=fetch_to)

    assert raised.value.code == "asset_download"
    assert "secret provider detail" not in raised.value.detail


def test_pinned_asset_rejects_path_traversal() -> None:
    with pytest.raises(ValueError, match="normalized relative POSIX path"):
        pinned("../outside.parquet", b"contents")


def test_verify_assets_rejects_missing_cache(tmp_path: Path) -> None:
    asset = pinned("rel-hm/db/article.parquet", b"expected")

    with pytest.raises(AssetStagingError) as raised:
        verify_hm_assets(tmp_path, assets=(asset,))

    assert raised.value.code == "asset_integrity"
