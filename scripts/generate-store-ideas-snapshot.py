"""Generate static store ideas from the backend keyword snapshot."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def scan_count(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        con = sqlite3.connect(path)
        count = con.execute("SELECT COUNT(DISTINCT keyword) FROM scans").fetchone()[0]
        con.close()
        return int(count or 0)
    except Exception:
        return 0


def choose_db() -> Path:
    workspace_db = BACKEND / "workspace" / "_keyword_db" / "keywords.sqlite"
    seed_db = BACKEND / "seed_data" / "_keyword_db" / "keywords.sqlite"
    return workspace_db if scan_count(workspace_db) > 0 else seed_db


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--signal-limit", type=int, default=1000)
    parser.add_argument("--domain", default=None)
    args = parser.parse_args()

    db_path = choose_db()
    if not db_path.exists():
        print("[]")
        return 0

    from pipeline import keyword_database as kdb
    from pipeline.store_idea_profitability import generate_profitable_store_ideas

    kdb.DB_PATH = db_path
    if "workspace" in db_path.parts:
        kdb.init_db()
    ideas = generate_profitable_store_ideas(
        limit=args.limit,
        signal_limit=args.signal_limit,
        domain=args.domain,
    )
    print(json.dumps(ideas, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
