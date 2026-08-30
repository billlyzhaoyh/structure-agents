"""Fixed entrypoint uploaded to a private Daytona SQL sandbox."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from structagent_api.materialization.materializer import HMDatasetFiles, materialize_default_task
from structagent_api.materialization.synthetic import SYNTHETIC_CUTOFFS

RunnerTaskId = Literal["rel-hm/user-churn", "rel-hm/item-sales"]


class RunnerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_revision: str = Field(min_length=1)
    task_ids: list[RunnerTaskId] = Field(min_length=1, max_length=2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path)
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()

    request = RunnerRequest.model_validate_json(args.request.read_text(encoding="utf-8"))
    if len(request.task_ids) != len(set(request.task_ids)):
        parser.error("task IDs must be unique")

    dataset = HMDatasetFiles.from_directory(
        args.input_dir,
        revision=request.dataset_revision,
    )
    packages: dict[str, str] = {}
    cutoffs = SYNTHETIC_CUTOFFS if request.dataset_revision == "synthetic" else None
    for task_id in request.task_ids:
        task_output = args.output_dir / task_id.rsplit("/", maxsplit=1)[1]
        if cutoffs is None:
            result = materialize_default_task(task_id, dataset, task_output)
        else:
            result = materialize_default_task(task_id, dataset, task_output, cutoffs=cutoffs)
        packages[task_id] = result.package_sha256

    print(
        json.dumps(
            {"packages": packages, "status": "succeeded"},
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
