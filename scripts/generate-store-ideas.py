"""Pure snapshot generation: no database connection or provider calls."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from pipeline.store_idea_profitability import generate_store_ideas_from_rows

if __name__ == "__main__":
    rows = json.load(sys.stdin)
    print(json.dumps(generate_store_ideas_from_rows(rows, int(sys.argv[1]) if len(sys.argv) > 1 else 12)))
