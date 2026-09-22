"""Import one or more provider evidence exports into the configured evidence store."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--geography")
    parser.add_argument("--period-start")
    parser.add_argument("--period-end")
    parser.add_argument("--currency-code")
    args = parser.parse_args()

    from pipeline import keyword_database as kdb
    from services.evidence_import_service import import_evidence

    kdb.init_db()
    results = []
    for path in args.files:
        result = import_evidence(
            source=args.source,
            text=path.read_text(encoding="utf-8-sig"),
            name=path.name,
            geography=args.geography,
            period_start=args.period_start,
            period_end=args.period_end,
            currency_code=args.currency_code,
        )
        results.append(result)
    print(json.dumps(results, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
