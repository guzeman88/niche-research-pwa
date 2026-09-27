from services.candidate_portfolio import (
    MODEL_VERSION,
    PROVISIONAL_SCORE_CAP,
    build_candidate_portfolio,
    evaluate_candidate_test,
)


def row(keyword, *, listings=1200, price=28, sample=100, source="library", volume=None):
    return {
        "keyword": keyword,
        "domain": "pets",
        "source": source,
        "evidence_status": "verified",
        "listing_count": listings,
        "sampled_listing_count": sample,
        "avg_price_usd": price,
        "observed_search_volume": volume,
    }


def test_marketplace_only_portfolio_is_ranked_but_capped_and_not_validated():
    keywords = [
        "chinchilla owner", "hedgehog owner", "budgie owner", "cockatiel owner",
        "ferret owner", "hamster owner", "snake owner", "guinea pig owner",
        "fish tank lover", "bunny owner", "parrot owner",
    ]
    portfolio = build_candidate_portfolio([row(keyword) for keyword in keywords])

    candidate = next(store for store in portfolio["stores"] if store["id"] == "small-exotic-pet-owner-gifts")
    assert portfolio["model_version"] == MODEL_VERSION
    assert portfolio["status"] == "provisional"
    assert candidate["validation_state"] == "provisional_marketplace"
    assert candidate["test_priority_score"] <= PROVISIONAL_SCORE_CAP
    assert candidate["score_cap"] == PROVISIONAL_SCORE_CAP
    assert len(candidate["product_candidates"]) == 6
    assert any("search volume" in blocker.lower() for blocker in candidate["blockers"])


def test_safety_screen_removes_retailer_and_non_product_queries():
    rows = [
        row("november door decorations", source="expand_google_suggest"),
        row("november yard decorations", source="expand_google_suggest"),
        row("thanksgiving decorations indoor", source="expand_google_suggest"),
        row("thanksgiving decorations amazon", source="expand_google_suggest"),
        row("thanksgiving decorations near me", source="expand_google_suggest"),
    ]
    portfolio = build_candidate_portfolio(rows)
    candidate = next(store for store in portfolio["stores"] if store["id"] == "thanksgiving-november-decor")

    returned = {item["keyword"] for item in candidate["keywords"]}
    assert "thanksgiving decorations amazon" not in returned
    assert "thanksgiving decorations near me" not in returned
    assert portfolio["coverage"]["excluded_rows"] == 2


def test_volume_threshold_changes_state_to_demand_screened():
    keywords = [
        "aries rising", "taurus rising", "gemini rising", "cancer rising",
        "leo rising", "virgo rising", "libra rising", "scorpio rising",
        "sagittarius rising", "capricorn rising",
    ]
    portfolio = build_candidate_portfolio([
        row(keyword, listings=1800, price=32, volume=200)
        for keyword in keywords
    ])
    candidate = next(store for store in portfolio["stores"] if store["id"] == "birth-chart-placement-gifts")

    assert portfolio["status"] == "demand_screened"
    assert candidate["validation_state"] == "demand_screened"
    assert candidate["score_cap"] is None
    assert candidate["evidence"]["combined_monthly_searches"] == 2000
    assert candidate["evidence"]["keywords_at_or_above_100_searches"] == 10


def test_candidate_test_requires_complete_observed_outcomes():
    portfolio = build_candidate_portfolio([
        row(keyword) for keyword in [
            "chinchilla owner", "hedgehog owner", "budgie owner", "cockatiel owner",
            "ferret owner", "hamster owner", "snake owner", "guinea pig owner",
            "fish tank lover", "bunny owner", "parrot owner",
        ]
    ])
    candidate = next(store for store in portfolio["stores"] if store["id"] == "small-exotic-pet-owner-gifts")
    result = evaluate_candidate_test(candidate, [])

    assert result["status"] == "collecting"
    assert result["ready_to_advance"] is False
    assert result["metrics"]["impressions"] == 0
    assert result["blockers"]


def test_candidate_test_advances_only_after_hard_thresholds_clear():
    portfolio = build_candidate_portfolio([
        row(keyword) for keyword in [
            "chinchilla owner", "hedgehog owner", "budgie owner", "cockatiel owner",
            "ferret owner", "hamster owner", "snake owner", "guinea pig owner",
            "fish tank lover", "bunny owner", "parrot owner",
        ]
    ])
    candidate = next(store for store in portfolio["stores"] if store["id"] == "small-exotic-pet-owner-gifts")
    outcomes = []
    for index, product in enumerate(candidate["product_candidates"]):
        outcomes.append({
            "keyword": product["primary_keyword"],
            "listing_id": f"listing-{index}",
            "period_start": "2026-09-01",
            "period_end": "2026-09-30",
            "impressions": 200,
            "clicks": 4,
            "orders": 1 if index < 3 else 0,
            "revenue_usd": 30 if index < 3 else 0,
            "contribution_profit_usd": 10 if index < 3 else 0,
        })
    result = evaluate_candidate_test(candidate, outcomes)

    assert result["status"] == "advance"
    assert result["ready_to_advance"] is True
    assert result["metrics"]["listings"] == 6
    assert result["metrics"]["duration_days"] == 30
    assert result["metrics"]["click_through_rate_pct"] == 2.0
    assert result["metrics"]["orders"] == 3
    assert result["metrics"]["contribution_profit_usd"] == 30
