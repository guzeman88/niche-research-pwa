"""Run one quota-aware evidence batch in an ephemeral worker."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--batch-size",
        type=int,
        default=int(os.environ.get("SCHEDULED_BATCH_SIZE", "50")),
    )
    parser.add_argument("--skip-discovery", action="store_true")
    parser.add_argument("--ignore-rate-limit", action="store_true")
    args = parser.parse_args()

    if not os.environ.get("SUPABASE_URL") or not os.environ.get("SUPABASE_SERVICE_ROLE_KEY"):
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")

    from pipeline import keyword_database as kdb
    from pipeline.autonomous_scheduler import AutonomousScheduler

    kdb.ensure_seed_snapshot()
    scheduler = AutonomousScheduler(
        store_slug="__global__",
        mode="continuous",
        batch_size=args.batch_size,
        log_fn=print,
    )
    result = scheduler.run_batch_once(
        batch_size=args.batch_size,
        run_discovery=not args.skip_discovery,
        respect_rate_limit=not args.ignore_rate_limit,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
