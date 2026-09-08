import io
import sqlite3
import time
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pipeline import keyword_database as db
from pipeline.autonomous_scheduler import AutonomousScheduler
from services import runtime_safety, scheduler_service
from security import protect_operator_api, redact_settings


@pytest.fixture
def database(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "keywords.sqlite")
    db.init_db()
    return db


@pytest.mark.parametrize("contents", [b"", b"damaged but valuable"])
def test_startup_never_replaces_existing_database(tmp_path, contents):
    target = tmp_path / "existing.sqlite"
    seed = tmp_path / "seed.sqlite"
    target.write_bytes(contents)
    with sqlite3.connect(seed) as con: con.execute("create table marker(id integer)")
    assert runtime_safety.initialize_workspace(target, seed) is False
    assert target.read_bytes() == contents


def test_windows_logging_does_not_kill_worker(monkeypatch):
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1252")
    monkeypatch.setattr(runtime_safety.sys, "stdout", stream)
    runtime_safety.safe_log("Price: ₹20")
    assert b"\\u20b9" in raw.getvalue()


def test_worker_failure_finalizes_run(database, tmp_path, monkeypatch):
    monkeypatch.setattr("pipeline.autonomous_scheduler.STATE_FILE", tmp_path / "state.json")
    worker = AutonomousScheduler(log_fn=lambda _: None)
    monkeypatch.setattr(worker, "_loop", Mock(side_effect=RuntimeError("database unavailable")))
    worker.start(); worker._thread.join(2)
    assert worker.status()["health"] == "failed"
    assert database.get_scheduler_history(1)[0]["status"] == "failed"


def test_watchdog_respects_stop_and_pause(monkeypatch):
    worker = Mock()
    monkeypatch.setattr(scheduler_service, "_scheduler", worker)
    worker.status.return_value = {"fatal_error": None}
    worker.is_running.return_value = False; worker.is_paused.return_value = False
    assert scheduler_service.ensure_scheduler_running()["status"] == "stopped"
    worker.is_running.return_value = True; worker.is_paused.return_value = True
    assert scheduler_service.ensure_scheduler_running()["status"] == "paused"
    worker.start.assert_not_called(); worker.resume.assert_not_called()


def test_attempts_are_not_evidence(database):
    database.save_scan("empty scan", {"sources_used": []})
    database.save_scan("failed scan", {"scan_error": "provider unavailable"})
    database.save_scan("signal scan", {"sources_used": ["google_suggest"]})
    stats = database.get_stats()
    assert (stats["attempted"], stats["successful"], stats["evidence_backed"], stats["failed"], stats["no_data"]) == (3, 1, 0, 1, 1)


def test_default_scanner_registers_google_suggest():
    from pipeline.stages.niche_research import _build_adapters
    from pipeline.autonomous_scheduler import _scheduler_research_adapters
    assert "google_suggest" in _scheduler_research_adapters()
    adapters = _build_adapters(None, ["google_suggest"], lambda _: None)
    assert len(adapters) == 1 and adapters[0].name == "google_suggest"


def test_private_api_requires_token_and_settings_are_redacted(monkeypatch):
    monkeypatch.setenv("PIPELINE_API_TOKEN", "test-only-secret")
    app = FastAPI()
    app.middleware("http")(protect_operator_api)
    @app.get("/api/settings")
    def settings(): return redact_settings({"airtable": {"api_key": "private", "tables": {"stores": "Stores"}}})
    @app.post("/api/designs/generate")
    def generate(): return {"ok": True}
    @app.get("/api/workspace/backups")
    def backups(): return []
    client = TestClient(app)
    for route in ["/api/settings", "/api/workspace/backups"]:
        assert client.get(route).status_code == 401
    assert client.post("/api/designs/generate").status_code == 401
    response = client.get("/api/settings", headers={"Authorization": "Bearer test-only-secret"})
    assert response.status_code == 200
    assert "private" not in response.text


def test_local_origin_cannot_bypass_tunnel_auth(monkeypatch):
    from starlette.requests import Request
    from security import is_authorized
    monkeypatch.delenv("PIPELINE_API_TOKEN", raising=False)
    def request(headers):
        return Request({"type":"http", "method":"POST", "scheme":"http", "path":"/api/settings",
            "server":("127.0.0.1",8001), "client":("127.0.0.1",5000), "query_string":b"", "headers":headers})
    assert is_authorized(request([(b"host",b"127.0.0.1:8001")]))
    assert not is_authorized(request([(b"host",b"public.example"), (b"origin",b"http://localhost")]))
    assert not is_authorized(request([(b"host",b"127.0.0.1:8001"), (b"origin",b"https://untrusted.example")]))


def test_server_backups_preserve_revisions(tmp_path, monkeypatch):
    from routers import workspace
    monkeypatch.setattr(workspace, "WORKSPACE", tmp_path)
    first = workspace.Backup(schema_version=1, created_at="2026-09-08", data={})
    second = workspace.Backup(schema_version=1, created_at="2026-09-09", data={})
    assert workspace.save_backup(first)["revision"] == 1
    assert workspace.save_backup(second)["revision"] == 2
    assert workspace.get_backup(1)["created_at"] == first.created_at
    assert len(workspace.list_backups()) == 2
