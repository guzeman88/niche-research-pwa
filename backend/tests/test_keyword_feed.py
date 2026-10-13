"""Local durability mode, replay and private feed freshness boundaries."""
from datetime import date, timedelta
import json
import pytest
from pipeline import keyword_database as db
from services import supabase_evidence_sync as sync
from services.keyword_feed_status import freshness, status


def test_ephemeral_workers_still_fail_closed_local_workers_keep_committed_runs(monkeypatch):
    monkeypatch.setattr(sync, "sync_collection_run", lambda _: {"configured": True, "status": "failed"})
    monkeypatch.delenv("EVIDENCE_DURABILITY_MODE", raising=False)
    with pytest.raises(sync.DurableEvidenceSyncError):
        sync.require_collection_sync("run")
    monkeypatch.setenv("EVIDENCE_DURABILITY_MODE", "local-outbox")
    assert sync.require_collection_sync("run")["locally_preserved"]


def test_committed_outbox_retries_and_acknowledges_without_losing_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "research.sqlite")
    db.init_db()
    run = db.start_evidence_collection("etsy_open_api", {"keyword": "mug"})
    db.mark_evidence_collection_sync(run, "failed", "temporary host outage")
    def replay(identity):
        db.mark_evidence_collection_sync(identity, "synced")
        return {"status": "synced"}
    monkeypatch.setattr(sync, "sync_collection_run", replay)
    assert sync.retry_collection_outbox() == {"synced": 1, "failed": 0, "pending": 0}
    assert sync.retry_collection_outbox()["synced"] == 0
    with db._conn() as con:
        assert con.execute("SELECT count(*) FROM evidence_collection_runs").fetchone()[0] == 1


def test_freshness_keeps_sources_and_reporting_windows_separate():
    today = date.today()
    old = (today - timedelta(days=8)).isoformat()
    rows = [{"kind": "competitors", "payload": {"keyword": "mug", "source": "etsy_open_api", "observed_at": old}},
            {"kind": "google", "payload": {"collected_at": today.isoformat(), "signals": [{"matched_queue_keywords": ["mug"], "monthly_searches": None}]}}]
    result = freshness(rows, "mug")
    assert [r["status"] for r in result] == ["due", "missing", "current"]
    assert result[2]["observations"] == 1  # Unknown measurement is still a collected result.


def test_new_host_outbox_does_not_relabel_historical_source_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "research.sqlite")
    db.init_db()
    old = db.start_evidence_collection("etsy_open_api")
    new = db.start_evidence_collection("etsy_open_api")
    with db._conn() as con:
        con.execute("UPDATE evidence_collection_runs SET started_at='2020-01-01' WHERE id=?", (old,))
    monkeypatch.setenv("EVIDENCE_OUTBOX_SINCE", "2025-01-01")
    replayed = []
    def replay(identity):
        replayed.append(identity)
        db.mark_evidence_collection_sync(identity, "synced")
        return {"status": "synced"}
    monkeypatch.setattr(sync, "sync_collection_run", replay)
    assert sync.retry_collection_outbox()["pending"] == 0
    assert replayed == [new]
    with db._conn() as con:
        assert con.execute("SELECT durable_sync_status FROM evidence_collection_runs WHERE id=?", (old,)).fetchone()[0] != 'synced'


def test_status_does_not_expose_paths_or_configuration(tmp_path, monkeypatch):
    monkeypatch.setenv("VALIDATION_DB_PATH", str(tmp_path / "validation.sqlite"))
    (tmp_path / "feed-status.json").write_text(json.dumps({"status": "completed", "started_at": "date", "secret": "private", "focused": {"before": "private/path"}}))
    result = status()
    assert "private" not in json.dumps(result)
    assert result["status"] == "completed"
