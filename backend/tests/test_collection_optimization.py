from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

from adapters.base.research import NicheSignal
from adapters.research import etsy_open_api, google_trends
from adapters.research.etsy_search_scraper import EtsyListingData, EtsySearchResult
from pipeline import keyword_database as db
from pipeline.autonomous_scheduler import AutonomousScheduler, _remaining_interval_seconds
from pipeline.autonomous_scheduler import _signal_fingerprint
from pipeline.stages import niche_research
from services import collection_quality
from services import scheduler_service


@pytest.fixture
def database(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "keywords.sqlite")
    db.init_db()
    return db


def test_etsy_interval_bursts_until_eighty_percent_reserve(monkeypatch) -> None:
    monkeypatch.setenv("ETSY_DAILY_QUOTA_TARGET_PCT", "80")
    monkeypatch.setenv("ETSY_ACTIVE_BURST_INTERVAL_SECONDS", "1")
    etsy_open_api._clear_rate_limit_state()
    response = Mock(
        status_code=200,
        headers={
            "x-limit-per-second": "5",
            "x-remaining-this-second": "4",
            "x-limit-per-day": "5000",
            "x-remaining-today": "4999",
        },
    )

    etsy_open_api._capture_rate_limits(response)

    interval = etsy_open_api.recommended_request_interval_seconds()
    assert interval == pytest.approx(1.0)
    assert etsy_open_api.etsy_rate_limit_snapshot()["remaining_today"] == 4999


def test_etsy_interval_waits_at_eighty_percent_reserve(monkeypatch) -> None:
    monkeypatch.setenv("ETSY_DAILY_QUOTA_TARGET_PCT", "80")
    monkeypatch.setenv("ETSY_QUOTA_RECHECK_SECONDS", "600")
    etsy_open_api._clear_rate_limit_state()
    etsy_open_api._capture_rate_limits(Mock(
        status_code=200,
        headers={
            "x-limit-per-second": "5",
            "x-limit-per-day": "5000",
            "x-remaining-today": "1000",
        },
    ))

    assert etsy_open_api.recommended_request_interval_seconds() == pytest.approx(600.0)


def test_etsy_interval_uses_limit_only_until_remaining_is_observed(monkeypatch) -> None:
    monkeypatch.setenv("ETSY_DAILY_QUOTA_TARGET_PCT", "80")
    etsy_open_api._clear_rate_limit_state()
    etsy_open_api._capture_rate_limits(Mock(
        status_code=200,
        headers={"x-limit-per-second": "5", "x-limit-per-day": "5000"},
    ))

    assert etsy_open_api.recommended_request_interval_seconds() == pytest.approx(21.6)


def test_etsy_interval_rejects_invalid_quota_target(monkeypatch) -> None:
    monkeypatch.setenv("ETSY_DAILY_QUOTA_TARGET_PCT", "not-a-number")
    etsy_open_api._clear_rate_limit_state()
    etsy_open_api._capture_rate_limits(Mock(
        status_code=200,
        headers={"x-limit-per-second": "5", "x-limit-per-day": "5000"},
    ))

    with pytest.raises(ValueError, match="must be numeric"):
        etsy_open_api.recommended_request_interval_seconds()


def test_scheduler_does_not_double_count_processing_time_in_quota_interval() -> None:
    assert _remaining_interval_seconds(17.28, 12.0) == pytest.approx(5.28)
    assert _remaining_interval_seconds(17.28, 20.0) == 0.0


def test_valid_no_data_scan_does_not_stop_scheduler(database, monkeypatch) -> None:
    from pipeline.stages import niche_research

    monkeypatch.setattr(niche_research, "run", lambda **_kwargs: {
        "sources_used": [],
        "keyword_search_data": [],
        "keyword_signals": [],
        "scan_error": None,
    })
    monkeypatch.setattr(database, "save_scan", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(database, "get_expansion_depth", lambda _keyword: 99)

    worker = AutonomousScheduler.__new__(AutonomousScheduler)
    worker._store_slug = "__global__"
    worker._skip_scraper = False
    worker._log = lambda _message: None
    worker._queue_secondary_collection = lambda _keyword: None

    assert worker._scan_and_expand("valid sparse phrase") == 0


def test_continuous_collection_enforces_target_batch_size(monkeypatch) -> None:
    monkeypatch.setattr(scheduler_service, "MIN_CONTINUOUS_BATCH_SIZE", 30)

    assert scheduler_service.collection_batch_size("continuous", 5) == 30
    assert scheduler_service.collection_batch_size("continuous", 40) == 40
    assert scheduler_service.collection_batch_size("slow", 5) == 5


def test_etsy_research_uses_full_page_without_duplicate_adapter_call(monkeypatch) -> None:
    listing = EtsyListingData(
        listing_id="123",
        title="Observed listing",
        price_usd=25.0,
        review_count=None,
        is_star_seller=None,
        is_bestseller=None,
        shop_name="shop",
        url="https://www.etsy.com/listing/123/",
    )
    captured: list[int] = []

    class FakeClient:
        def search_listings(self, keyword: str, limit: int = 50):
            captured.append(limit)
            result = EtsySearchResult(keyword=keyword, total_listing_count=10)
            result.listings = [listing]
            result.compute_aggregates()
            return result

        def close(self):
            return None

    monkeypatch.setattr(etsy_open_api, "EtsyOpenAPIClient", FakeClient)
    monkeypatch.setattr(etsy_open_api, "is_etsy_open_api_configured", lambda: True)
    monkeypatch.setattr(niche_research.NicheReport, "save", lambda self: Path("report.json"))

    class DuplicateAdapter:
        name = "etsy_open_api"

        def is_configured(self):
            return True

        def bulk_search(self, _keywords):
            raise AssertionError("duplicate Etsy adapter call")

    monkeypatch.setattr(
        niche_research,
        "_build_adapters",
        lambda *_args, **_kwargs: [DuplicateAdapter()],
    )

    report = niche_research.run(
        ["teacher gift"],
        "__global__",
        include_seasonality=False,
        allow_llm_synthesis=False,
    )

    assert captured == [100]
    assert report.sources_used == ["etsy_open_api"]
    assert report.keyword_search_data[0]["sampled_listing_count"] == 1


def test_google_trends_prefetch_serves_individual_keyword_without_refetch(monkeypatch) -> None:
    with google_trends._PREFETCH_LOCK:
        google_trends._PREFETCHED.clear()
    calls: list[list[str]] = []

    def fake_fetch(self, keywords):
        calls.append(list(keywords))
        return [
            NicheSignal(
                keyword=keyword,
                monthly_searches=None,
                competition_score=None,
                avg_price_usd=None,
                trend_direction=None,
                source="google_trends",
            )
            for keyword in keywords
        ]

    monkeypatch.setattr(google_trends.GoogleTrendsAdapter, "_fetch", fake_fetch)
    google_trends.GoogleTrendsAdapter().prefetch(["teacher gift", "nurse gift"])
    result = google_trends.GoogleTrendsAdapter().bulk_search(["teacher gift"])

    assert [signal.keyword for signal in result] == ["teacher gift"]
    assert calls == [["teacher gift", "nurse gift"]]


def test_google_trends_prefetch_does_not_refetch_confirmed_no_data(monkeypatch) -> None:
    with google_trends._PREFETCH_LOCK:
        google_trends._PREFETCHED.clear()
    calls: list[list[str]] = []

    def fake_fetch(self, keywords):
        calls.append(list(keywords))
        return []

    monkeypatch.setattr(google_trends.GoogleTrendsAdapter, "_fetch", fake_fetch)
    adapter = google_trends.GoogleTrendsAdapter()
    adapter.prefetch(["no trend data"])

    assert adapter.bulk_search(["no trend data"]) == []
    assert calls == [["no trend data"]]


def test_durable_collection_state_survives_without_local_scan_rows(database) -> None:
    database.merge_remote_collection_state(
        [{
            "keyword": "durable keyword",
            "domain": "test",
            "source": "cloud_sync",
            "added_at": "2026-09-01T00:00:00Z",
        }],
        [{
            "keyword": "durable keyword",
            "last_collected_at": "2026-09-01T00:00:00Z",
            "evidence_status": "verified",
            "listing_count": 25,
            "sampled_listing_count": 25,
            "avg_price_usd": 20,
            "sources": ["etsy_open_api"],
            "last_run_id": "run-1",
            "updated_at": "2026-09-01T00:00:00Z",
        }],
    )

    assert database.get_stats()["evidence_backed"] == 1
    assert database.get_next_batch(count=1) == ["durable keyword"]


def test_database_contexts_release_the_sqlite_file(database) -> None:
    database.get_stats()

    database.DB_PATH.unlink()

    assert not database.DB_PATH.exists()


def test_provider_refresh_state_prevents_duplicate_work_inside_window(database) -> None:
    keywords = ["teacher gift", "nurse gift"]
    assert database.provider_keywords_due("google_trends", keywords, stale_days=30) == keywords

    database.record_provider_keyword_attempt(
        "google_trends",
        "teacher gift",
        status="no_data",
        row_count=0,
    )

    assert database.provider_keywords_due("google_trends", keywords, stale_days=30) == ["nurse gift"]


def test_feed_fingerprint_ignores_collector_timestamp() -> None:
    first = NicheSignal(
        keyword="teacher gifts",
        monthly_searches=None,
        competition_score=None,
        avg_price_usd=None,
        trend_direction=None,
        source="google_daily_trends",
        observed_at="2026-09-23T10:00:00Z",
        position=1,
        metadata={"rank": 1},
    )
    second = NicheSignal(**{**vars(first), "observed_at": "2026-09-23T11:00:00Z"})

    assert _signal_fingerprint("google_daily_trends", first) == _signal_fingerprint("google_daily_trends", second)


def test_feed_fingerprints_hydrate_from_durable_runtime_state(monkeypatch) -> None:
    from services import provider_telemetry

    monkeypatch.setattr(provider_telemetry, "get_provider_states", lambda: {
        "google_daily_trends": {"metadata": {"fingerprints": ["remote-a", "remote-b"]}},
    })
    worker = AutonomousScheduler.__new__(AutonomousScheduler)
    worker._external_discovery_fingerprints = {"google_daily_trends": ["local-a"]}
    worker._log = lambda _message: None

    worker._hydrate_external_discovery_fingerprints()

    assert worker._external_discovery_fingerprints["google_daily_trends"] == [
        "local-a", "remote-a", "remote-b",
    ]


def test_quality_rates_require_observed_denominators(database, monkeypatch) -> None:
    monkeypatch.setattr(collection_quality, "get_provider_states", lambda: {
        "etsy_open_api": {
            "configured": True,
            "status": "completed",
            "rate_limit": {"limit_per_day": 5000, "remaining_today": 1000},
        },
        "google_suggest": {"configured": True, "status": "completed"},
        "pinterest_trends": {"configured": False, "status": "not_configured"},
    })
    monkeypatch.setattr(collection_quality, "get_provider_events", lambda hours: [
        {
            "provider": "etsy_open_api",
            "metadata": {
                "eligible_keywords": 5000,
                "processed_keywords": 4000,
                "usable_keywords": 3900,
            },
        },
        {
            "provider": "google_suggest",
            "metadata": {
                "eligible_keywords": 10,
                "processed_keywords": 8,
                "usable_keywords": 6,
            },
        },
    ])

    result = collection_quality.get_collection_quality(hours=24)
    by_source = {row["source"]: row for row in result["sources"]}

    assert by_source["etsy_open_api"]["collection_rate_pct"] == 80.0
    assert by_source["google_suggest"]["collection_rate_pct"] == 80.0
    assert by_source["google_suggest"]["quality_yield_pct"] == 75.0
    assert by_source["pinterest_trends"]["collection_rate_pct"] is None
    assert by_source["pinterest_trends"]["target_status"] == "not_configured"
    assert by_source["erank"]["collection_rate_pct"] is None


def test_etsy_quality_prefers_provider_remaining_quota(database, monkeypatch) -> None:
    monkeypatch.setattr(collection_quality, "get_provider_states", lambda: {
        "etsy_open_api": {
            "configured": True,
            "status": "completed",
            "rate_limit": {"limit_per_day": 5000, "remaining_today": 1000},
        },
    })
    monkeypatch.setattr(collection_quality, "get_provider_events", lambda hours: [{
        "provider": "etsy_open_api",
        "metadata": {"processed_keywords": 12},
    }])

    result = collection_quality.get_collection_quality(hours=24)
    etsy = next(row for row in result["sources"] if row["source"] == "etsy_open_api")

    assert etsy["collection_rate_pct"] == 80.0
    assert etsy["collected"] == 4000
    assert etsy["eligible_or_available"] == 5000


def test_import_row_coverage_uses_observed_rows(database, monkeypatch) -> None:
    monkeypatch.setattr(collection_quality, "get_provider_states", lambda: {
        "erank": {"configured": True, "status": "completed"},
    })
    monkeypatch.setattr(collection_quality, "get_provider_events", lambda hours: [{
        "provider": "erank",
        "metadata": {"provider_rows": 10, "covered_rows": 8, "new_rows": 24},
    }])

    result = collection_quality.get_collection_quality(hours=24)
    erank = next(row for row in result["sources"] if row["source"] == "erank")

    assert erank["collection_rate_pct"] == 80.0
    assert erank["new_rows"] == 24
    assert erank["target_status"] == "on_target"
