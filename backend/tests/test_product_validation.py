import asyncio
from datetime import date, timedelta
import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services import product_validation as v
from scripts.restore_validation_ledger import restore


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("VALIDATION_DB_PATH", str(tmp_path / "ledger.sqlite"))
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    return v.create_project({"name": "Teacher totes", "product_type": "tote", "keywords": ["teacher tote"]})["id"]


def outcome(**changes):
    return {"shop_id": "123", "listing_id": "456", "period_start": "2026-09-01", "period_end": "2026-09-30", "source": "Shop Stats and payments", "currency": "USD",
        "visits": 200, "orders": 5, "revenue": 100, **{field: 0 for field in v.COST_FIELDS}, **changes}


def test_missing_costs_and_traffic_stay_unknown(project):
    v.save_outcome(project, outcome(visits=None, labor=None))
    result = v.summary(project)["outcomes"]
    assert result["visits"] is None and result["contribution"] is None
    assert result["status"] == "inconclusive"
    assert v.records(project, "outcome")[0]["payload"]["impressions"] is None


def test_revisions_duplicates_overlap_and_cross_project_attribution(project):
    assert not v.save_outcome(project, outcome())["duplicate"]
    assert v.save_outcome(project, outcome())["duplicate"]
    v.save_outcome(project, outcome(revenue=110))
    assert len(v.records(project, "outcome")) == 1
    assert v.summary(project)["outcomes"]["revenue"] == 110
    assert len(v.export_ledger()["payload"]["revisions"]) == 3  # project and two result revisions
    with pytest.raises(ValueError, match="overlaps"):
        v.save_outcome(project, outcome(period_start="2026-09-20", period_end="2026-10-01"))
    other = v.create_project({"name": "Other", "product_type": "tote", "keywords": ["teacher tote"]})["id"]
    with pytest.raises(ValueError, match="another concept"):
        v.save_outcome(other, outcome())


def test_import_preview_and_failure_are_atomic(project):
    header = "shop_id,listing_id,period_start,period_end,currency,visits,orders,revenue\n"
    valid = "123,456,2026-09-01,2026-09-30,USD,200,5,100\n"
    data = {"source": "reviewed worksheet", "text": header + valid}
    assert not v.import_outcomes_csv(project, data)["committed"]
    assert not v.records(project, "outcome")
    with pytest.raises(ValueError, match="[Oo]verlap"):
        v.import_outcomes_csv(project, {**data, "text": header + valid + "123,456,2026-09-20,2026-10-01,USD,100,2,50\n"}, commit=True)
    assert not v.records(project, "outcome")
    v.import_outcomes_csv(project, data, commit=True)
    v.import_outcomes_csv(project, data, commit=True)
    assert len(v.records(project, "outcome")) == 1


def test_same_source_dated_readiness_and_costs(project):
    today = date.today().isoformat()
    v.save_market(project, {"keyword": "teacher tote", "period_start": today, "period_end": today, "observed_at": today, "searches": 500, "listings": 1000, "source_note": "Marketplace Insights"})
    v.save_competitors(project, {"keyword": "teacher tote", "observed_at": today, "source": "manual reviewed samples", "relevance_reviewed": True, "listings": [{"listing_id": str(i), "shop_id": str(i % 5), "title": "Teacher tote", "price": 25, "currency": "USD"} for i in range(20)]})
    scenario = {"price": 25, **{field: 1 for field in v.COST_FIELDS}, "setup": 90, "fixed_monthly": 0}
    data = {"source": "provider quotes and fees", "observed_at": today, "currency": "USD", "scenarios": {name: scenario for name in ("conservative", "base", "optimistic")}}
    v.save_economics(project, data)
    result = v.summary(project)
    assert result["status"] == "ready_to_test"
    assert result["economics"]["conservative"]["contribution_per_order"] == 18
    assert result["economics"]["conservative"]["first_month_break_even_orders"] == 5
    assert result["outcomes"]["status"] == "not_started"
    data["scenarios"]["conservative"] = {**scenario, "labor": None}
    v.save_economics(project, data)
    assert v.summary(project)["status"] == "needs_evidence"


def test_mirror_failure_keeps_outbox_and_restore(project, monkeypatch, tmp_path):
    monkeypatch.setenv("SUPABASE_URL", "https://test.invalid")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "fixture-secret")
    monkeypatch.setattr(v.httpx, "post", lambda *args, **kwargs: httpx.Response(503, request=httpx.Request("POST", args[0])))
    assert v.retry_sync()["pending"] == 1
    assert len(v.records()) == 1
    package = v.export_ledger()
    assert restore(package, tmp_path / "restored.sqlite")["records"] == 1
    assert len(v.records()) == 1
    with pytest.raises(FileExistsError):
        restore(package, tmp_path / "restored.sqlite")
    package["payload"]["records"][0]["payload"]["name"] = "modified"
    with pytest.raises(ValueError, match="checksum"):
        restore(package, tmp_path / "tampered.sqlite")


def test_google_variants_are_one_observation(project):
    payload = {"schema_version": 1, "source": "google_ads_keyword_planner", "signals": [{"keyword": "teacher totes", "monthly_searches": 500, "metadata": {"close_variants": ["teacher tote"]}}]}
    package = {"payload": payload, "sha256": v.digest(payload)}
    v.import_google_package(project, {"package": package})
    v.import_google_package(project, {"package": package})
    assert len(v.records(project, "google")) == 1
    assert v.summary(project)["status"] == "needs_evidence"  # Google never substitutes for Etsy demand


def test_order_reconciliation_deduplicates_without_inflating_period_totals(project):
    data = {"shop_id": "123", "source": "Orders", "revenue_basis": "retained item revenue excluding tax",
        "columns": {key: key for key in ("order_id", "transaction_id", "listing_id", "date", "currency", "revenue")},
        "text": "order_id,transaction_id,listing_id,date,currency,revenue\n1,2,456,2026-09-15,USD,25\n"}
    assert v.import_orders_csv(project, data)["preview"][0]["listing_id"] == "456"
    assert not v.records(project, "order_item")
    v.import_orders_csv(project, data, commit=True)
    v.import_orders_csv(project, data, commit=True)
    assert len(v.records(project, "order_item")) == 1
    assert v.summary(project)["outcomes"]["revenue"] is None
    other = v.create_project({"name": "Other", "product_type": "tote", "keywords": ["teacher tote"]})["id"]
    with pytest.raises(ValueError, match="another concept"):
        v.import_orders_csv(other, data, commit=True)


def test_net_profit_and_mixed_currencies_remain_distinct(project):
    v.save_outcome(project, outcome(setup_expenses=20, fixed_expenses=10))
    assert v.summary(project)["outcomes"]["net_profit"] == 70
    v.save_outcome(project, outcome(listing_id="789", currency="EUR", setup_expenses=0, fixed_expenses=0))
    assert v.summary(project)["outcomes"]["contribution"] is None
    assert v.summary(project)["outcomes"]["net_profit"] is None


def test_review_requires_current_sample_revision(project):
    saved = v.save_competitors(project, {"keyword": "teacher tote", "observed_at": v.today().isoformat(), "source": "api",
        "listings": [{"listing_id": "1", "shop_id": "2", "title": "Teacher tote", "price": 25, "currency": "USD"}]})
    row = v.records(project, "competitors")[0]
    with pytest.raises(ValueError, match="changed"):
        v.review_competitors(project, {"record_id": saved["id"], "fingerprint": "stale", "review_note": "Comparable totes"})
    v.review_competitors(project, {"record_id": saved["id"], "fingerprint": row["fingerprint"], "review_note": "Comparable totes"})
    assert v.records(project, "competitors")[0]["payload"]["relevance_reviewed"]


def test_private_read_requires_operator_authorization(monkeypatch):
    from starlette.requests import Request
    import security
    request = Request({"type": "http", "method": "GET", "scheme": "https", "path": "/api/product-validation/export", "server": ("test.invalid", 443), "client": ("203.0.113.1", 123), "query_string": b"", "headers": []})
    monkeypatch.delenv("PIPELINE_API_TOKEN", raising=False)
    async def downstream(_request):
        raise AssertionError("Private ledger must not be exposed")
    assert asyncio.run(security.protect_operator_api(request, downstream)).status_code == 401


def test_named_etsy_operation_is_not_shadowed_by_evidence_kind_route(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers.product_validation import router
    app = FastAPI()
    app.include_router(router)
    monkeypatch.setattr(v, "collect_etsy", lambda project_id, keyword: {"sampled": 50, "keyword": keyword})
    response = TestClient(app).post('/api/product-validation/projects/test/collect-etsy', json={"keyword": "teacher tote"})
    assert response.status_code == 200
    assert response.json() == {"sampled": 50, "keyword": "teacher tote"}


@pytest.mark.parametrize("change", [{"revenue": float("nan")}, {"orders": 1.5}, {"period_start": "2026-10-31"}, {"period_end": "2026-08-01"}])
def test_invalid_observations_rejected(project, change):
    with pytest.raises(ValueError):
        v.save_outcome(project, outcome(**change))
