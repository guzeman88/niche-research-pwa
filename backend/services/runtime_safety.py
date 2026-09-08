"""Non-destructive startup and logging for desktop and hosted processes."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


def safe_log(message: str) -> None:
    stream = sys.stdout
    if stream is None:
        return
    try:
        print(message, flush=True)
    except UnicodeEncodeError:
        encoding = getattr(stream, "encoding", None) or "utf-8"
        print(message.encode(encoding, errors="backslashreplace").decode(encoding), flush=True)
    except (OSError, ValueError):
        # A closed redirected console must never terminate a worker.
        return


def initialize_workspace(database: Path, seed_database: Path) -> bool:
    """Seed only an absent database. Existing, empty, or damaged files are preserved."""
    if database.exists() or not seed_database.exists():
        return False
    database.parent.mkdir(parents=True, exist_ok=True)
    # SQLite backup includes committed WAL content without copying live sidecars.
    with sqlite3.connect(seed_database.as_uri() + "?mode=ro", uri=True) as source:
        with sqlite3.connect(database) as target:
            source.backup(target)
    return True
