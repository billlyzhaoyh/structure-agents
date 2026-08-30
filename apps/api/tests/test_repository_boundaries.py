from __future__ import annotations

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
        Path("app.js"),
        Path("demo-data.js"),
        Path("index.html"),
        Path("styles.css"),
        Path("tests/demo-data.test.mjs"),
        Path("tests/workspace-state.test.mjs"),
        Path("workspace-state.js"),
    }
    assert worker_files == [Path("README.md")]
