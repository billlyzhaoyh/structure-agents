"""Sandbox entry point for a complete EDSL simulation response batch."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from structagent_api.contracts.simulation import canonical_contract_json, contract_digest
from structagent_api.simulation.batch import (
    SimulationBatchCheckpoint,
    SimulationBatchRequest,
    run_edsl_batch,
)


def main() -> int:
    if len(sys.argv) != 4:
        print(json.dumps({"code": "arguments", "status": "failed"}, sort_keys=True))
        return 2
    request_path, result_path, checkpoint_path = map(Path, sys.argv[1:])
    try:
        request = SimulationBatchRequest.model_validate_json(request_path.read_bytes())
        checkpoint = (
            SimulationBatchCheckpoint.model_validate_json(checkpoint_path.read_bytes())
            if checkpoint_path.exists()
            else None
        )

        def save_checkpoint(value: SimulationBatchCheckpoint) -> None:
            checkpoint_path.write_text(canonical_contract_json(value) + "\n", encoding="utf-8")

        result = run_edsl_batch(
            request,
            checkpoint=checkpoint,
            save_checkpoint=save_checkpoint,
        )
        result_path.write_text(canonical_contract_json(result) + "\n", encoding="utf-8")
        print(
            json.dumps(
                {
                    "base_response_count": result.base_response_count,
                    "result_digest": contract_digest(result),
                    "sentinel_response_count": result.sentinel_response_count,
                    "status": "succeeded",
                },
                sort_keys=True,
            )
        )
        return 0
    except Exception as error:
        print(
            json.dumps(
                {
                    "code": "batch_execution",
                    "error_type": type(error).__name__,
                    "status": "failed",
                },
                sort_keys=True,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
