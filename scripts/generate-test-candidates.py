"""Generate the shared test-candidate portfolio from a keyword snapshot."""
from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def main() -> int:
    payload = json.load(sys.stdin)
    if not isinstance(payload, list):
        raise ValueError("keyword snapshot must be an array")
    from services.candidate_portfolio import build_candidate_portfolio

    result = build_candidate_portfolio(payload)
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
