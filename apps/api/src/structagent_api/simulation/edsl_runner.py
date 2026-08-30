"""Execute one sanitized three-repeat EDSL integration smoke inside Daytona."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from structagent_api.contracts.simulation import canonical_contract_json, contract_digest
from structagent_api.simulation.edsl import EdslSmokeRequest, run_edsl_smoke


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    if args.output.exists():
        parser.error("output path already exists")
    try:
        request = EdslSmokeRequest.model_validate_json(args.request.read_text(encoding="utf-8"))
        result = run_edsl_smoke(request)
        args.output.write_text(canonical_contract_json(result) + "\n", encoding="utf-8")
    except (Exception, KeyboardInterrupt):
        print(
            json.dumps(
                {"code": "edsl_execution", "status": "failed"},
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 1

    print(
        json.dumps(
            {
                "choice_count": len(result.choices),
                "result_digest": contract_digest(result),
                "status": "succeeded",
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
