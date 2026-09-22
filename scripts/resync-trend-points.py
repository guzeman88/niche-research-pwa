"""Re-upsert exact trend points from one or more local evidence databases."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("databases", nargs="+", type=Path)
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()
    if args.batch_size < 1:
        raise ValueError("batch size must be positive")

    from services.supabase_evidence_sync import _trend_row, _upsert

    counts: dict[str, int] = {}
    for database in args.databases:
        with sqlite3.connect(database) as connection:
            connection.row_factory = sqlite3.Row
            rows = [dict(row) for row in connection.execute(
                "SELECT * FROM keyword_trend_points ORDER BY id"
            ).fetchall()]
        for start in range(0, len(rows), args.batch_size):
            payload = [_trend_row(row) for row in rows[start:start + args.batch_size]]
            _upsert("keyword_trend_points", "source_trend_point_id", payload)
        counts[str(database)] = len(rows)
    print(json.dumps(counts, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
