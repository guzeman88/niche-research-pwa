"""Run the automated keyword validation pipeline from cron or a terminal."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.keyword_validation_pipeline import KeywordValidationPipeline


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect and score EtGen keyword evidence")
    parser.add_argument("--force", action="store_true", help="Ignore the normal monthly refresh window")
    parser.add_argument("--no-expand", action="store_true", help="Skip keyword idea generation")
    args = parser.parse_args()

    result = KeywordValidationPipeline().run(force=args.force, expand=not args.no_expand)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("status") in {"completed", "not_configured"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
