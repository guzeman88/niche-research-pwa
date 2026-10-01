from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

import httpx
import pytest

from adapters.base.research import NicheSignal
from adapters.research import google_ads_keyword_planner as planner
from adapters.research.google_ads_keyword_planner import GoogleAdsKeywordPlannerAdapter
from pipeline import keyword_database as db
from services import keyword_validation_pipeline as validation
from services import supabase_evidence_sync as durable_sync


@pytest.fixture
def database(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "keywords.sqlite")
    monkeypatch.setattr(validation, "REPORT_PATH", tmp_path / "validation_report.json")
    monkeypatch.setattr(validation, "STATE_PATH", tmp_path / "validation_state.json")
    db.init_db()
    return db


def google_signal(keyword: str = "teacher mug") -> NicheSignal:
    return NicheSignal(
        keyword=keyword,
        monthly_searches=2400,
        competition_score=72,
        avg_price_usd=None,
        trend_direction="rising",
        source=validation.PROVIDER,
        observed_at="2026-09-01T00:00:00+00:00",
        geography="US",
        relative_interest_period="rolling_12_months",
        time_series=[
            {"date": "2026-01-01", "value": 1000, "unit": "searches"},
            {"date": "2026-08-01", "value": 1600, "unit": "searches"},
        ],
        metadata={
            "period_start": "2025-09-01",
            "period_end": "2026-08-31",
            "observations": [
                {"metric": "google_ads_competition_index", "value": 72, "unit": "index_0_100"},
                {"metric": "average_cpc", "value": 1.8, "unit": "usd"},
            ],
        },
    )


def test_adapter_maps_google_response_to_auditable_signal(monkeypatch):
    monkeypatch.setenv("GOOGLE_ADS_GEO_TARGET_IDS", "2840")
    adapter = GoogleAdsKeywordPlannerAdapter()
    signal = adapter._signal_from_result({
        "text": "Teacher Mug",
        "keywordMetrics": {
            "avgMonthlySearches": "2400",
            "competition": "HIGH",
            "competitionIndex": "72",
            "averageCpcMicros": "1800000",
            "lowTopOfPageBidMicros": "900000",
            "highTopOfPageBidMicros": "3200000",
            "monthlySearchVolumes": [
                {"year": "2026", "month": "JANUARY", "monthlySearches": "1000"},
                {"year": "2026", "month": "AUGUST", "monthlySearches": "1600"},
            ],
        },
    })

    assert signal.keyword == "teacher mug"
    assert signal.monthly_searches == 2400
    assert signal.competition_score == 72
    assert signal.metadata["average_cpc_usd"] == 1.8
    assert signal.time_series[-1]["date"] == "2026-08-01"
    assert signal.trend_direction == "rising"


def test_bulk_persistence_records_metrics_series_and_attempt_state(database):
    result = database.save_provider_signal_batch(
        validation.PROVIDER,
        [google_signal()],
        requested_keywords=["teacher mug", "missing keyword"],
    )

    evidence = database.get_keyword_evidence("teacher mug")
    metrics = {row["metric"] for row in evidence["observations"]}
    assert result["returned_keywords"] == 1
    assert {"monthly_searches", "provider_competition", "average_cpc"} <= metrics
    assert len(evidence["trend_points"]) == 2
    assert database.provider_keywords_due(
        validation.PROVIDER,
        ["teacher mug", "missing keyword"],
        stale_days=30,
    ) == []


def test_google_batch_fails_when_durable_sync_fails(database, monkeypatch):
    monkeypatch.setattr(
        durable_sync, "sync_collection_run",
        lambda _run_id: {"configured": True, "status": "failed", "error": "upload failed"},
    )

    with pytest.raises(durable_sync.DurableEvidenceSyncError, match="upload failed"):
        database.save_provider_signal_batch(validation.PROVIDER, [google_signal()])


def test_supabase_upsert_chunks_large_batches_and_retries_transient_errors(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")
    monkeypatch.setattr(durable_sync.time, "sleep", lambda _seconds: None)
    calls = []

    def fake_post(url, **kwargs):
        calls.append(json.loads(kwargs["content"]))
        request = httpx.Request("POST", url)
        return httpx.Response(503 if len(calls) == 1 else 204, request=request)

    monkeypatch.setattr(durable_sync.httpx, "post", fake_post)
    durable_sync._upsert("keyword_observations", "keyword,source,observed_at,metric", [
        {"keyword": str(index)} for index in range(1001)
    ])

    assert [len(batch) for batch in calls] == [500, 500, 500, 1]
    assert calls[0] == calls[1]


def test_validation_report_uses_exact_five_component_weights(database):
    database.save_provider_signal_batch(validation.PROVIDER, [google_signal()])
    database.record_keyword_observation(
        keyword="teacher mug",
        source="etsy_open_api",
        metric="listing_count",
        value=3000,
        unit="count",
        observed_at="2026-09-01T00:00:00+00:00",
        geography="US",
    )
    database.record_keyword_listing_snapshots(
        "teacher mug",
        "etsy_open_api",
        [{"listing_id": str(index), "title": f"Teacher mug {index}"} for index in range(10)],
        observed_at="2026-09-01T00:00:00+00:00",
    )
    database.record_product_economics(
        "teacher mug",
        "mug",
        sale_price_usd=24,
        production_cost_usd=8,
        shipping_cost_usd=4,
        marketplace_fees_usd=3,
        advertising_cost_usd=2,
        refund_allowance_usd=1,
        source="provider quote",
        observed_at="2026-09-01T00:00:00+00:00",
    )

    report = validation.build_validation_report(
        keyword_limit=200,
        niche_limit=25,
        finalist_limit=5,
        candidate_limit=2000,
    )
    row = report["keywords"][0]

    assert report["weights"] == {
        "demand": 35,
        "competition": 25,
        "trend": 20,
        "buyer_intent": 10,
        "profit": 10,
    }
    assert row["evidence_coverage_pct"] == 100
    assert row["score"] is not None
    assert row["listing_samples"] == 10
    assert validation.REPORT_PATH.exists()


def test_unconfigured_pipeline_exits_without_network_or_fake_data(database, monkeypatch):
    for name in (
        "GOOGLE_ADS_CUSTOMER_ID", "GOOGLE_ADS_SERVICE_ACCOUNT_JSON",
        "GOOGLE_ADS_JSON_KEY_FILE_PATH", "GOOGLE_APPLICATION_CREDENTIALS",
        "GOOGLE_ADS_CLIENT_ID", "GOOGLE_ADS_CLIENT_SECRET", "GOOGLE_ADS_REFRESH_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)
    result = validation.KeywordValidationPipeline(log_fn=lambda _message: None).run()

    assert result["status"] == "not_configured"
    assert database.get_keywords_by_observation(validation.PROVIDER, "monthly_searches") == []


def test_service_account_json_is_a_complete_configuration(monkeypatch):
    monkeypatch.setenv("GOOGLE_ADS_CUSTOMER_ID", "936-559-0258")
    monkeypatch.setenv("GOOGLE_ADS_SERVICE_ACCOUNT_JSON", '{"type":"service_account"}')
    for name in ("GOOGLE_ADS_CLIENT_ID", "GOOGLE_ADS_CLIENT_SECRET", "GOOGLE_ADS_REFRESH_TOKEN"):
        monkeypatch.delenv(name, raising=False)

    assert planner.is_google_ads_configured() is True


def test_developer_token_header_is_optional_after_sunset(monkeypatch):
    monkeypatch.setenv("GOOGLE_ADS_CUSTOMER_ID", "936-559-0258")
    monkeypatch.setenv("GOOGLE_ADS_SERVICE_ACCOUNT_JSON", '{"type":"service_account"}')
    monkeypatch.delenv("GOOGLE_ADS_DEVELOPER_TOKEN", raising=False)
    monkeypatch.setattr(planner, "_access_token", lambda _timeout: "access-token")
    captured = {}

    class Response:
        status_code = 200
        headers = {}

        @staticmethod
        def json():
            return {"results": []}

    def fake_post(url, *, headers, json, timeout):
        captured.update({"url": url, "headers": headers, "body": json, "timeout": timeout})
        return Response()

    monkeypatch.setattr(planner.httpx, "post", fake_post)
    GoogleAdsKeywordPlannerAdapter().bulk_search(["teacher mug"])

    assert captured["headers"]["authorization"] == "Bearer access-token"
    assert "developer-token" not in captured["headers"]


def test_service_account_expiry_accepts_google_naive_utc_datetime():
    naive_expiry = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=5)
    aware_expiry = datetime.now(timezone.utc) + timedelta(minutes=5)

    assert 250 <= planner._credential_lifetime_seconds(naive_expiry) <= 300
    assert 250 <= planner._credential_lifetime_seconds(aware_expiry) <= 300
    assert planner._credential_lifetime_seconds(None) == 3600
