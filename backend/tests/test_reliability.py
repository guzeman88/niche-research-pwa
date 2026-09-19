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
    @app.get("/api/evidence/example")
    def evidence(): return {}
    client = TestClient(app)
    for route in ["/api/settings", "/api/workspace/backups", "/api/evidence/example"]:
        assert client.get(route).status_code == 401
    assert client.post("/api/designs/generate").status_code == 401
    response = client.get("/api/settings", headers={"Authorization": "Bearer test-only-secret"})
    assert response.status_code == 200
    assert "private" not in response.text


def test_evidence_bundle_returns_exact_economics_and_outcomes(database):
    database.record_product_economics(
        keyword="exact keyword", product_type="mug", sale_price_usd=24,
        production_cost_usd=8, shipping_cost_usd=4, marketplace_fees_usd=2,
        advertising_cost_usd=1, refund_allowance_usd=0, source="invoice",
        observed_at="2026-09-01T00:00:00Z",
    )
    database.record_keyword_outcome(
        keyword="exact keyword", listing_id="listing-1", product_type="mug",
        period_start="2026-09-01", period_end="2026-09-07", impressions=100,
        clicks=10, orders=2, revenue_usd=48, marketplace_fees_usd=4,
        advertising_cost_usd=2, production_cost_usd=16, shipping_cost_usd=8,
        refunds_usd=0, source="etsy-export",
    )
    bundle = database.get_keyword_evidence("exact keyword")
    assert bundle is not None
    assert bundle["product_economics"][0]["contribution_profit_usd"] == 9
    assert bundle["outcomes"][0]["contribution_profit_usd"] == 18
    assert bundle["latest_verified_evidence"] is None


def test_scheduler_requires_explicit_operating_settings():
    from fastapi import HTTPException
    from models.schemas import SchedulerAction
    from routers.scheduler import start
    with pytest.raises(HTTPException, match="mode and batch_size"):
        start(SchedulerAction())


def test_new_store_configuration_has_no_business_defaults():
    from pipeline.store_config import StoreConfig
    store = StoreConfig(store_slug="test", display_name="Test")
    assert store.listing_count_target is None
    assert store.pricing.strategy is None
    assert store.pricing.digital_fixed_price is None


def test_store_ideas_require_versioned_evidence_and_keep_derived_scores_tbd():
    from pipeline.store_idea_profitability import generate_store_ideas_from_rows

    unverified = {"keyword": "teacher mug", "domain": "teachers", "opportunity_score": 91}
    assert generate_store_ideas_from_rows([unverified]) == []

    verified = {
        **unverified,
        "evidence_status": "verified",
        "score_version": "calibrated-v1",
        "avg_price_usd": 24.0,
        "listing_count": 125,
    }
    idea = generate_store_ideas_from_rows([verified])[0]
    assert idea["keywords"][0]["opportunity"] == 91
    assert idea["avgPrice"] == 24.0
    assert idea["nicheScore"] is None
    assert idea["profitScore"] is None
    assert idea["confidenceScore"] is None
    assert idea["feeModel"] is None


def test_etsy_listing_evidence_never_infers_sales_revenue_or_rank():
    from adapters.research.etsy_search_scraper import EtsyListingData, EtsySearchResult

    listing = EtsyListingData(
        listing_id="123",
        title="Observed listing",
        price_usd=25.0,
        review_count=10,
        is_star_seller=None,
        is_bestseller=None,
        shop_name="shop",
        url="https://www.etsy.com/listing/123/",
    )
    result = EtsySearchResult(keyword="observed", total_listing_count=None, listings=[listing])
    result.compute_aggregates()

    assert not hasattr(listing, "estimated_lifetime_sales")
    assert not hasattr(listing, "estimated_monthly_revenue_usd")
    assert result.estimated_total_monthly_revenue_usd is None
    assert result.competition_quality_score is None
    assert result.avg_review_count == 10.0
    assert result.avg_favorites is None


def test_schema_v12_clears_unversioned_derived_business_values(database):
    database.add_seed("legacy estimate", source="test")
    with database._conn() as con:
        con.execute("""
            INSERT INTO scans
                (keyword, scanned_at, opportunity_score, monthly_revenue_usd,
                 competition_quality, profitability_index, pct_high_favorites, evidence_status)
            VALUES ('legacy estimate', '2026-09-01', 88, 9999, 77, 66, 50, 'unverified')
        """)
        con.execute("DELETE FROM schema_version")
        con.execute("INSERT INTO schema_version(version) VALUES (10)")
    database.init_db()
    with database._conn() as con:
        row = con.execute("""
            SELECT opportunity_score, monthly_revenue_usd, competition_quality,
                   profitability_index, pct_high_favorites
            FROM scans WHERE keyword='legacy estimate'
        """).fetchone()
    assert database.SCHEMA_VERSION == 12
    assert tuple(row) == (None, None, None, None, None)


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
