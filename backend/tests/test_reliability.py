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


def test_etsy_autocomplete_is_not_reported_ready_without_verified_endpoint(monkeypatch):
    from adapters.research.etsy_autocomplete import EtsyAutocompleteAdapter

    monkeypatch.delenv("ETSY_AUTOCOMPLETE_URL", raising=False)
    adapter = EtsyAutocompleteAdapter(request_delay=0)

    assert adapter.is_configured() is False
    assert adapter.search("teacher mug") == []


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


def test_schema_v15_clears_unversioned_values_and_adds_raw_evidence_tables(database):
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
        seed_columns = {item[1] for item in con.execute("PRAGMA table_info(seeds)").fetchall()}
    assert database.SCHEMA_VERSION == 16
    assert tuple(row) == (None, None, None, None, None)
    assert "priority" not in seed_columns
    with database._conn() as con:
        tables = {item[0] for item in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        observation_columns = {item[1] for item in con.execute("PRAGMA table_info(keyword_observations)")}
    assert {"evidence_collection_runs", "keyword_suggestions", "keyword_trend_points", "keyword_listing_snapshots"} <= tables
    assert {"geography", "period_start", "period_end", "provider_record_id", "collection_run_id"} <= observation_columns


def test_marketplace_insights_import_requires_period_and_preserves_source(database):
    from services.evidence_import_service import import_evidence

    with pytest.raises(ValueError, match="period_start"):
        import_evidence(
            source="etsy_marketplace_insights",
            text="Keyword,Searches,Listings\nteacher mug,120,4500",
        )

    result = import_evidence(
        source="etsy_marketplace_insights",
        text="Keyword,Searches,Listings\nteacher mug,120,4500",
        period_start="2026-08-20",
        period_end="2026-09-18",
        geography="US",
    )
    assert result["keywords"] == 1
    assert result["observations"] == 2
    bundle = database.get_keyword_evidence("teacher mug")
    observations = {row["metric"]: row for row in bundle["observations"]}
    assert observations["searches"]["value"] == 120
    assert observations["searches"]["period_start"] == "2026-08-20"
    assert observations["listing_count"]["source"] == "etsy_marketplace_insights"
    assert bundle["collection_runs"][0]["durable_sync_status"] == "not_configured"


def test_google_trends_import_keeps_every_dated_point(database):
    from services.evidence_import_service import import_evidence

    result = import_evidence(
        source="google_trends",
        geography="US",
        text="Category: All categories\n\nWeek,teacher mug\n2026-09-01,32\n2026-09-08,47",
    )
    assert result["observations"] == 2
    bundle = database.get_keyword_evidence("teacher mug")
    assert [row["value"] for row in bundle["trend_points"]] == [47, 32]
    assert {row["geography"] for row in bundle["trend_points"]} == {"US"}


def test_google_keyword_planner_import_requires_context_and_preserves_metrics(database):
    from services.evidence_import_service import import_evidence

    text = (
        "Keyword,Avg. monthly searches,Competition (indexed value),"
        "Top of page bid (low range),Top of page bid (high range)\n"
        "teacher mug,1200,34,0.52,1.84"
    )
    with pytest.raises(ValueError, match="period_start"):
        import_evidence(source="google_keyword_planner", text=text)

    result = import_evidence(
        source="google_keyword_planner",
        text=text,
        period_start="2025-09-01",
        period_end="2026-08-31",
        geography="US",
        currency_code="USD",
    )
    assert result["observations"] == 4
    observations = {
        row["metric"]: row for row in database.get_keyword_evidence("teacher mug")["observations"]
    }
    assert observations["monthly_searches"]["value"] == 1200
    assert observations["provider_competition"]["value"] == 34
    assert observations["top_of_page_bid_low"]["unit"] == "usd"
    assert observations["top_of_page_bid_high"]["geography"] == "US"


def test_marmalead_import_keeps_provider_values(database):
    from services.evidence_import_service import import_evidence

    result = import_evidence(
        source="marmalead",
        text="Keyword,Search Volume,Engagement,Competition\nteacher mug,875,62,48",
        geography="US",
    )
    assert result["observations"] == 3
    observations = {
        row["metric"]: row for row in database.get_keyword_evidence("teacher mug")["observations"]
    }
    assert observations["monthly_searches"]["source"] == "marmalead"
    assert observations["provider_engagement"]["value"] == 62


def test_erank_import_preserves_current_average_and_upper_bound(database):
    from services.evidence_import_service import import_evidence

    result = import_evidence(
        source="erank",
        text=(
            "Keyword,Current searches,Average searches,Average clicks,CTR,Competition listings\n"
            "cat crochet pattern amigurumi,10620,896,73,<20%,6827"
        ),
        period_start="2026-08-01",
        period_end="2026-08-31",
        geography="US",
    )
    assert result["observations"] == 5
    observations = {
        row["metric"]: row
        for row in database.get_keyword_evidence("cat crochet pattern amigurumi")["observations"]
    }
    assert observations["current_period_searches"]["period_start"] == "2026-08-01"
    assert observations["monthly_searches"]["period_start"] is None
    assert observations["click_through_rate_upper_bound"]["value"] == 20
    assert observations["click_through_rate_upper_bound"]["unit"] == "percent_upper_bound"


def test_pinterest_trends_import_preserves_bounds_rank_and_series(database):
    from services.evidence_import_service import import_evidence

    text = '''"Pinterest Trends tool – https://trends.pinterest.com/search/?country=US&amp;trendsPreset=1"
Selected Filters
Trend Type,Top monthly trends
Date Range,30 days before 2026-09-19
Interests,"All"

,,,,,,Data in the date columns reflects the normalized search volume for this trend type
Rank,Trend,Normalized volume,Weekly change,Monthly change,Yearly change,2026-09-12,2026-09-19
1,fall nails,100,"10%","10,000%+","10%",88,100
'''
    result = import_evidence(source="pinterest_trends", text=text)
    assert result["keywords"] == 1
    assert result["observations"] == 7
    bundle = database.get_keyword_evidence("fall nails")
    observations = {row["metric"]: row for row in bundle["observations"]}
    assert observations["provider_rank"]["value"] == 1
    assert observations["normalized_volume"]["value"] == 100
    assert observations["growth_month_over_month_lower_bound"]["value"] == 10000
    assert observations["growth_month_over_month_lower_bound"]["unit"] == "percent_lower_bound"
    assert [point["value"] for point in bundle["trend_points"]] == [100, 88]
    assert {point["geography"] for point in bundle["trend_points"]} == {"US"}


def test_supabase_row_ids_are_stable_and_not_local_database_ids():
    from services.supabase_evidence_sync import _listing_row, _stable_bigint, _trend_row

    trend = {
        "id": 1, "keyword": "fall nails", "source": "pinterest_trends",
        "point_at": "2026-09-19", "value": 100, "unit": "relative_interest_index",
        "geography": "US", "timeframe": "30 days before 2026-09-19",
        "is_partial": None, "collected_at": "2026-09-22T14:00:00+00:00",
        "collection_run_id": "run-1", "metadata_json": None,
    }
    assert _trend_row(trend)["source_trend_point_id"] == _trend_row({**trend, "id": 999})["source_trend_point_id"]
    assert _trend_row(trend)["source_trend_point_id"] != 1

    listing = {
        "id": 1, "keyword": "fall nails", "source": "etsy_open_api",
        "observed_at": "2026-09-22T14:00:00+00:00", "listing_id": "123",
        "title": None, "shop_name": None, "url": None, "price": None,
        "currency_code": None, "favorites": None, "review_count": None,
        "is_star_seller": None, "is_bestseller": None, "position": 1,
        "collection_run_id": "run-1", "metadata_json": None,
    }
    assert _listing_row(listing)["source_listing_snapshot_id"] == _listing_row({**listing, "id": 42})["source_listing_snapshot_id"]
    assert _stable_bigint("trend", "a") != _stable_bigint("trend", "b")


def test_pinterest_trends_uses_documented_ranked_endpoint(monkeypatch):
    from adapters.research.pinterest_trends import PinterestTrendsAdapter, _CACHE

    monkeypatch.setenv("PINTEREST_ACCESS_TOKEN", "pina_test")
    monkeypatch.setenv("PINTEREST_TRENDS_REGION", "US")
    monkeypatch.setenv("PINTEREST_TREND_TYPE", "growing")
    _CACHE.clear()
    adapter = PinterestTrendsAdapter()
    response = Mock()
    response.status_code = 200
    response.raise_for_status = Mock()
    response.json.return_value = {
        "trends": [{
            "keyword": "Teacher Mug",
            "pct_growth_wow": 25,
            "pct_growth_mom": 80,
            "time_series": {"2026-09-01": 20, "2026-09-08": 40},
        }]
    }
    adapter._client.get = Mock(return_value=response)

    signal = adapter.search("teacher mug")[0]
    request_url = adapter._client.get.call_args.args[0]
    assert request_url.endswith("/trends/keywords/US/top/growing")
    assert signal.relative_interest == 30
    assert signal.metadata["series_normalization"] == "independent_0_100"
    assert signal.time_series[1]["date"] == "2026-09-08"


def test_google_daily_trends_preserves_traffic_as_lower_bound(database, monkeypatch):
    from adapters.research.google_daily_trends import GoogleDailyTrendsAdapter, _CACHE

    monkeypatch.setenv("GOOGLE_DAILY_TRENDS_GEO", "US")
    _CACHE.clear()
    adapter = GoogleDailyTrendsAdapter()
    response = Mock()
    response.content = b"""<?xml version="1.0" encoding="UTF-8"?>
    <rss xmlns:ht="https://trends.google.com/trending/rss" version="2.0">
      <channel><item>
        <title>Teacher Appreciation Gifts</title>
        <ht:approx_traffic>20K+</ht:approx_traffic>
        <link>https://trends.google.com/trending/rss?geo=US</link>
        <pubDate>Tue, 22 Sep 2026 05:10:00 -0700</pubDate>
        <ht:news_item>
          <ht:news_item_title>Teachers celebrated nationwide</ht:news_item_title>
          <ht:news_item_url>https://example.com/story</ht:news_item_url>
          <ht:news_item_source>Example News</ht:news_item_source>
        </ht:news_item>
      </item></channel>
    </rss>"""
    response.raise_for_status = Mock()
    adapter._client.get = Mock(return_value=response)

    signal = adapter.search("teacher appreciation gifts")[0]
    assert adapter._client.get.call_args.kwargs["params"] == {"geo": "US"}
    assert signal.monthly_searches is None
    assert signal.observed_at == "2026-09-22T12:10:00+00:00"
    assert signal.metadata["approx_traffic_display"] == "20K+"
    assert signal.metadata["traffic_is_lower_bound"] is True
    assert signal.metadata["observations"] == [{
        "metric": "approx_search_traffic_lower_bound",
        "value": 20000,
        "unit": "searches_lower_bound",
    }]
    assert signal.metadata["news_items"][0]["source"] == "Example News"

    database.save_scan(signal.keyword, {
        "report_id": "google-daily-test",
        "generated_at": signal.observed_at,
        "sources_used": [signal.source],
        "keyword_signals": [vars(signal)],
        "keyword_search_data": [],
    })
    observations = database.get_keyword_evidence(signal.keyword)["observations"]
    assert observations[0]["metric"] == "approx_search_traffic_lower_bound"
    assert observations[0]["value"] == 20000
    assert observations[0]["unit"] == "searches_lower_bound"


def test_google_daily_trends_returns_only_exact_feed_matches(monkeypatch):
    from adapters.research.google_daily_trends import GoogleDailyTrendsAdapter, _CACHE

    _CACHE.clear()
    adapter = GoogleDailyTrendsAdapter()
    response = Mock()
    response.content = b"""<rss xmlns:ht="https://trends.google.com/trending/rss">
      <channel><item><title>Teacher Mug</title><ht:approx_traffic>500+</ht:approx_traffic></item></channel>
    </rss>"""
    response.raise_for_status = Mock()
    adapter._client.get = Mock(return_value=response)

    assert adapter.search("teacher") == []
    assert adapter.search(" Teacher   Mug ")[0].keyword == "teacher mug"


def test_scan_preserves_suggestion_trend_and_listing_rows(database):
    report = {
        "report_id": "report-one",
        "generated_at": "2026-09-20T12:00:00Z",
        "sources_used": ["etsy_open_api", "google_suggest", "google_trends"],
        "keyword_signals": [
            {
                "keyword": "custom teacher mug",
                "source": "google_suggest",
                "query": "teacher mug",
                "position": 2,
                "observed_at": "2026-09-20T12:00:00Z",
                "geography": "US",
            },
            {
                "keyword": "teacher mug",
                "source": "google_trends",
                "relative_interest": 42,
                "relative_interest_period": "today 3-m",
                "observed_at": "2026-09-20T12:00:00Z",
                "geography": "US",
                "time_series": [{"date": "2026-09-01", "value": 38}],
            },
        ],
        "keyword_search_data": [{
            "keyword": "teacher mug",
            "total_listing_count": 1500,
            "sampled_listing_count": 1,
            "avg_price_usd": 24,
            "listing_samples": [{
                "listing_id": "listing-1", "title": "Teacher Mug", "price_usd": 24,
                "currency_code": "USD", "shop_name": "Test Shop", "position": 1,
            }],
        }],
    }
    database.save_scan("teacher mug", report)
    bundle = database.get_keyword_evidence("teacher mug")
    assert bundle["suggestions"][0]["suggestion"] == "custom teacher mug"
    assert bundle["trend_points"][0]["value"] == 38
    assert bundle["listing_snapshots"][0]["currency_code"] == "USD"
    assert bundle["collection_runs"][0]["status"] == "completed"


def test_reddit_adapter_records_exact_query_activity(monkeypatch):
    from adapters.integrations.reddit import RedditPost
    from adapters.research.reddit_etsy import RedditEtsyAdapter

    post = RedditPost(
        post_id="post-1", title="Teacher mug feedback", subreddit="Etsy",
        score=12, upvote_ratio=0.9, num_comments=4, created_utc=1.0,
        url="https://example.test", permalink="https://reddit.test/post-1",
        selftext="", flair="", is_self=True,
    )
    client = Mock()
    client.search_subreddit.side_effect = lambda **kwargs: [post] if kwargs["subreddit"] == "Etsy" else []
    adapter = RedditEtsyAdapter(subreddits=["Etsy", "EtsySellers"])
    monkeypatch.setattr(adapter, "is_configured", lambda: True)
    monkeypatch.setattr(adapter, "_get_client", lambda: client)

    signal = adapter.search("teacher mug")[0]
    assert signal.metadata["query"] == "teacher mug"
    assert signal.metadata["observations"][0] == {"metric": "posts_returned", "value": 1, "unit": "count"}
    assert signal.metadata["posts"][0]["post_id"] == "post-1"


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
