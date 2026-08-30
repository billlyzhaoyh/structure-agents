from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_local_materialization_cli_runs_both_defaults(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/materialize_hm.py",
            "local",
            "--runs-root",
            str(tmp_path),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["mode"] == "local-synthetic"
    assert set(report["tasks"]) == {"rel-hm/user-churn", "rel-hm/item-sales"}
    assert all(task["validation_status"] == "passed" for task in report["tasks"].values())
    assert len(list(tmp_path.glob("*-local-synthetic/tasks/*/manifest.json"))) == 2
