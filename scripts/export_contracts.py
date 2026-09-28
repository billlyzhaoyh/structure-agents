"""Export or verify the repository's versioned JSON Schema snapshots."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from structagent_contracts import SimulationRunResult, SimulationStudyArtifact

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIRECTORY = REPOSITORY_ROOT / "packages" / "contracts" / "schemas"
SCHEMAS = {
    "simulation-run-result-v1.schema.json": SimulationRunResult,
    "simulation-study-artifact-v1.schema.json": SimulationStudyArtifact,
}


def serialized_schema(model: type[SimulationRunResult] | type[SimulationStudyArtifact]) -> str:
    """Return a deterministic, human-reviewable schema snapshot."""

    schema: dict[str, Any] = model.model_json_schema(mode="validation")
    return f"{json.dumps(schema, indent=2, sort_keys=True)}\n"


def export_schemas(*, check: bool) -> int:
    """Write snapshots, or return nonzero when committed snapshots have drifted."""

    drifted: list[str] = []
    for filename, model in SCHEMAS.items():
        target = SCHEMA_DIRECTORY / filename
        expected = serialized_schema(model)
        if check:
            if not target.exists() or target.read_text(encoding="utf-8") != expected:
                drifted.append(filename)
        else:
            SCHEMA_DIRECTORY.mkdir(parents=True, exist_ok=True)
            target.write_text(expected, encoding="utf-8")

    if drifted:
        print(f"Contract schema drift detected: {', '.join(sorted(drifted))}")
        print("Run `make contracts-export` and review the generated changes.")
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Reject schema snapshot drift")
    arguments = parser.parse_args()
    return export_schemas(check=arguments.check)


if __name__ == "__main__":
    raise SystemExit(main())
