from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_provider_and_model_runtimes_are_not_locked_dependencies() -> None:
    lockfile = (ROOT / "uv.lock").read_text(encoding="utf-8")

    forbidden_packages = {
        "daytona",
        "openai",
        "relbench",
        "relational-transformer",
        "torch",
    }
    for package in forbidden_packages:
        assert f'name = "{package}"' not in lockfile


def test_frontend_is_dependency_free_and_worker_is_documentation_only() -> None:
    web_files = {
        path.relative_to(ROOT / "apps" / "web")
        for path in (ROOT / "apps" / "web").rglob("*")
        if path.is_file()
    }
    worker_files = [
        path.relative_to(ROOT / "workers" / "rtj")
        for path in (ROOT / "workers" / "rtj").rglob("*")
        if path.is_file()
    ]

    assert web_files == {
        Path("README.md"),
        Path("api-client.js"),
        Path("app.js"),
        Path("demo-data.js"),
        Path("index.html"),
        Path("styles.css"),
        Path("tests/api-client.test.mjs"),
        Path("tests/demo-data.test.mjs"),
        Path("tests/workspace-state.test.mjs"),
        Path("workspace-state.js"),
    }
    assert worker_files == [Path("README.md")]


def test_external_asset_cache_is_ignored() -> None:
    result = subprocess.run(
        ["git", "check-ignore", "--quiet", ".artifacts/rel-hm/example.parquet"],
        cwd=ROOT,
        check=False,
    )

    assert result.returncode == 0
