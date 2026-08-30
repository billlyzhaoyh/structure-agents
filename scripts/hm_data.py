"""Stage or verify the revision-pinned RelBench H&M assets outside Git."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from structagent_api.catalog import RELBENCH_V1_REVISION
from structagent_api.materialization.hm_assets import (
    REL_HM_ASSETS,
    AssetStagingError,
    stage_hm_assets,
    verify_hm_assets,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("sync", "verify"))
    parser.add_argument(
        "--cache-root",
        type=Path,
        default=Path(".artifacts/rel-hm"),
        help="ignored root for pinned external files",
    )
    args = parser.parse_args()

    try:
        if args.action == "sync":
            staged = stage_hm_assets(args.cache_root)
        else:
            staged = verify_hm_assets(args.cache_root)
    except AssetStagingError as error:
        parser.error(f"{error.code}: {error.detail}")

    print(
        json.dumps(
            {
                "asset_count": len(REL_HM_ASSETS),
                "cache": str(staged.root),
                "revision": RELBENCH_V1_REVISION,
                "total_bytes": sum(asset.byte_count for asset in REL_HM_ASSETS),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
