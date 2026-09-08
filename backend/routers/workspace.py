"""Authenticated, append-only browser-work backups for the solo operator."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from config import WORKSPACE

router = APIRouter(prefix="/api/workspace", tags=["workspace"])
KEYS = {
    "niche-research-pwa:stores:v1", "niche-research-pwa:store-workspace:v1",
    "niche-research-pwa:user-keywords:v1", "niche-research-pwa:user-scan-batches:v1",
}


class Backup(BaseModel):
    schema_version: int
    created_at: str
    data: dict


@contextmanager
def _connection():
    con = sqlite3.connect(WORKSPACE / "operator-backups.sqlite", timeout=30)
    con.execute("CREATE TABLE IF NOT EXISTS backups (revision INTEGER PRIMARY KEY, created_at TEXT NOT NULL, payload TEXT NOT NULL)")
    try:
        with con:
            yield con
    finally:
        con.close()


@router.post("/backups", status_code=201)
def save_backup(backup: Backup):
    if backup.schema_version != 1 or not set(backup.data).issubset(KEYS):
        raise HTTPException(400, "Unsupported backup format")
    payload = json.dumps(backup.model_dump())
    if len(payload.encode()) > 16 * 1024 * 1024:
        raise HTTPException(413, "Backup exceeds 16 MB")
    with _connection() as con:
        result = con.execute("INSERT INTO backups(created_at,payload) VALUES (?,?)",
            (datetime.now(timezone.utc).isoformat(), payload))
        return {"revision": result.lastrowid}


@router.get("/backups")
def list_backups():
    with _connection() as con:
        return [{"revision": row[0], "created_at": row[1]} for row in
            con.execute("SELECT revision,created_at FROM backups ORDER BY revision DESC LIMIT 50")]


@router.get("/backups/{revision}")
def get_backup(revision: int):
    with _connection() as con:
        row = con.execute("SELECT payload FROM backups WHERE revision=?", (revision,)).fetchone()
    if row is None:
        raise HTTPException(404, "Backup not found")
    return json.loads(row[0])
