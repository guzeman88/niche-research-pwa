from datetime import datetime, timezone

from services.opportunity_decision import MODEL_VERSION, evaluate_opportunity


NOW = datetime(2026, 9, 25, tzinfo=timezone.utc)


def evidence_bundle(*, profit=9.0, demand_source="etsy_marketplace_insights"):
    return {
        "keyword": "teacher mug",
        "observations": [
            {
                "source": demand_source,
                "metric": "searches",
                "value": 1200,
                "unit": "searches",
                "geography": "US",
                "period_start": "2026-08-01",
                "period_end": "2026-08-31",
                "observed_at": "2026-09-01T00:00:00+00:00",
            },
            {
                "source": "etsy_marketplace_insights",
                "metric": "listing_count",
                "value": 4500,
                "unit": "listings",
                "geography": "US",
                "period_start": "2026-08-01",
                "period_end": "2026-08-31",
                "observed_at": "2026-09-01T00:00:00+00:00",
            },
        ],
        "product_economics": [{
            "product_type": "digital download",
            "observed_at": "2026-09-02T00:00:00+00:00",
            "source": "cost worksheet",
            "sale_price_usd": 18,
            "production_cost_usd": 2,
            "shipping_cost_usd": 0,
            "marketplace_fees_usd": 3,
            "advertising_cost_usd": 3,
            "refund_allowance_usd": 1,
            "contribution_profit_usd": profit,
        }],
        "listing_snapshots": [{"listing_id": str(index)} for index in range(25)],
        "trend_points": [
            {"source": "google_trends", "point_at": "2026-08-01", "value": 40, "unit": "relative_interest"},
            {"source": "google_trends", "point_at": "2026-09-01", "value": 52, "unit": "relative_interest"},
        ],
        "outcomes": [],
        "latest_attempt": {"sampled_listing_count": 25},
    }


def test_complete_exact_evidence_produces_versioned_reproducible_decision():
    first = evaluate_opportunity(evidence_bundle(), "digital-download", evaluated_at=NOW)
    second = evaluate_opportunity(evidence_bundle(), "digital download", evaluated_at=NOW)

    assert first["model_version"] == MODEL_VERSION
    assert first["status"] in {"advance", "review", "hold"}
    assert first["score"] is not None
    assert first["components"]["contribution_margin"] > 0
    assert first["evidence"]["market_pair"]["source"] == "etsy_marketplace_insights"
    assert first["economics"]["contribution_profit_usd"] == 9
    assert first["input_fingerprint"] == second["input_fingerprint"]
    assert not first["blockers"]


def test_demand_and_supply_from_different_sources_are_not_combined():
    result = evaluate_opportunity(
        evidence_bundle(demand_source="google_keyword_planner"),
        "digital_download",
        evaluated_at=NOW,
    )

    assert result["status"] == "blocked"
    assert result["score"] is None
    assert any("same source" in blocker for blocker in result["blockers"])


def test_undated_periods_use_observation_day_and_do_not_mix_across_days():
    evidence = evidence_bundle()
    for row in evidence["observations"]:
        row["period_start"] = None
        row["period_end"] = None
    evidence["observations"][1]["observed_at"] = "2026-09-02T00:00:00+00:00"

    result = evaluate_opportunity(evidence, "digital_download", evaluated_at=NOW)

    assert result["status"] == "blocked"
    assert result["evidence"]["market_pair"] is None


def test_missing_inputs_are_named_instead_of_defaulted():
    result = evaluate_opportunity(
        {"keyword": "teacher mug", "observations": [], "product_economics": [], "listing_snapshots": []},
        "digital_download",
        evaluated_at=NOW,
    )

    assert result["score"] is None
    assert result["ready_to_advance"] is False
    assert len(result["blockers"]) == 3
    assert result["components"] == {
        "demand": None,
        "market_balance": None,
        "contribution_margin": None,
        "sample_depth": None,
    }


def test_non_positive_contribution_profit_blocks_advancement():
    result = evaluate_opportunity(evidence_bundle(profit=-1), "digital_download", evaluated_at=NOW)

    assert result["status"] == "blocked"
    assert result["ready_to_advance"] is False
    assert any("Contribution profit" in blocker for blocker in result["blockers"])
