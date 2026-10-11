"""Transparent test-store and product candidates from incomplete market evidence.

The portfolio produced here is deliberately a *test-priority* report. It can
rank evidence-backed experiments before demand volume exists, but it caps every
such score at 65/100 and never labels the result validated. Full opportunity
decisions continue to require exact demand, supply, unit economics, and listing
outcomes through ``opportunity_decision``.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from statistics import median
from typing import Any, Callable


MODEL_VERSION = "etgen-test-portfolio-v1.0.0"
PROVISIONAL_SCORE_CAP = 65
VALIDATION_THRESHOLDS = {
    "related_keywords": 10,
    "combined_monthly_searches": 1_500,
    "keywords_at_or_above_100_searches": 5,
    "maximum_median_etsy_listings": 10_000,
    "minimum_observed_price_usd": 18,
    "minimum_listing_samples_per_keyword": 10,
    "advance_score": 70,
}
TEST_PLAN = {
    "duration_days": 30,
    "listing_count": 6,
    "minimum_total_impressions": 1_000,
    "minimum_click_through_rate_pct": 1.5,
    "minimum_orders": 3,
    "requires_positive_contribution_profit": True,
}


BLOCKED_PHRASES: dict[str, tuple[str, ...]] = {
    "protected brand or entertainment property": (
        "amazon", "barbie", "disney", "dollar tree", "etsy", "fortnite",
        "harry potter", "hello kitty", "hobby lobby", "lego", "marvel",
        "minecraft", "nintendo", "nike", "playstation", "pokemon", "snoopy",
        "stanley", "star wars", "swiftie", "taylor swift", "tiktok", "xbox",
    ),
    "professional sports property": ("mlb", "nba", "nfl", "nhl"),
    "regulated or medical-risk term": (
        "affordable care act", "cannabis", "cbd", "kratom", "ozempic",
    ),
}
NOISE_PHRASES = ("near me", "score", "weather", "today", "live stream")
REVIEW_PHRASES = ("ideas", "inspired", "style of", "lookalike")


def _contains(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


SMALL_PETS = (
    "budgie", "bunny", "chinchilla", "cockatiel", "ferret", "guinea pig",
    "hamster", "hedgehog", "parrot", "rabbit", "snake", "fish tank",
)
ASTROLOGY_TERMS = (
    "aquarius", "aries", "birth chart", "birth month", "cancer", "capricorn",
    "gemini", "leo", "libra", "moon sign", "pisces", "rising sign",
    "sagittarius", "scorpio", "sun sign", "taurus", "virgo", "zodiac",
)
SEASONAL_TERMS = (
    "autumn", "christmas", "december", "fall", "harvest", "january", "november",
    "october", "pumpkin", "spring", "summer", "thanksgiving", "winter",
)
DECOR_TERMS = ("decor", "decoration", "door", "porch", "table", "wall", "yard")
PARENT_TERMS = ("mom", "mama", "mother", "dad", "daddy", "father")
HUMOR_TERMS = (
    "chaotic", "funny", "hot mess", "overthinker", "procrastinator", "sarcastic",
    "wordplay",
)
PROFESSION_TERMS = (
    "artist", "baker", "barber", "coder", "developer", "doctor", "engineer",
    "makeup artist", "massage therapist", "nail technician", "nurse",
    "photographer", "teacher", "therapist",
)
MUSICIAN_TERMS = ("guitar", "microphone", "musician", "singer")
MICRO_AESTHETIC_TERMS = ("angelcore", "devilcore", "regencycore", "royalcore", "skeletoncore")


THEMES: tuple[dict[str, Any], ...] = (
    {
        "id": "thanksgiving-november-decor",
        "name": "Thanksgiving & November Decor",
        "focus": "Thanksgiving and November door, porch, and table decor",
        "buyer": "holiday decorators planning a coordinated November home refresh",
        "match": lambda value: _contains(value, ("thanksgiving", "november", "harvest")) and _contains(value, DECOR_TERMS),
        "products": ("Door hanger", "Printable door sign", "Table decor set", "Porch sign", "Wall print set", "Ornament"),
    },
    {
        "id": "small-exotic-pet-owner-gifts",
        "name": "Small & Exotic Pet Owner Gifts",
        "focus": "small and exotic pet-owner identity gifts",
        "buyer": "owners of small and less-served companion animals",
        "match": lambda value: _contains(value, SMALL_PETS) and _contains(value, ("owner", "lover", "mom", "dad", "gift")),
        "products": ("Personalized mug", "Owner shirt", "Tote bag", "Pet ornament", "Portrait print", "Sticker set"),
    },
    {
        "id": "birth-chart-placement-gifts",
        "name": "Birth-Chart Placement Gifts",
        "focus": "sun, moon, rising, and birth-chart identity gifts",
        "buyer": "astrology shoppers looking beyond generic sun-sign products",
        "match": lambda value: _contains(value, ASTROLOGY_TERMS),
        "products": ("Personalized chart print", "Placement mug", "Tote bag", "Journal", "Shirt", "Ornament"),
    },
    {
        "id": "dark-romantic-micro-aesthetics",
        "name": "Dark Romantic Micro-Aesthetics",
        "focus": "distinctive core aesthetics with a dark-romantic visual system",
        "buyer": "aesthetic-led shoppers seeking a specific visual identity",
        "match": lambda value: _contains(value, MICRO_AESTHETIC_TERMS),
        "products": ("Art print", "Graphic shirt", "Sticker set", "Tote bag", "Mug", "Phone case"),
    },
    {
        "id": "plant-parent-humor",
        "name": "Plant-Parent Humor",
        "focus": "self-deprecating plant-parent humor",
        "buyer": "plant lovers who identify with imperfect plant care",
        "match": lambda value: "plant" in value and _contains(value, ("killer", "mom", "dad", "parent")),
        "products": ("Mug", "Plant marker set", "Graphic shirt", "Tote bag", "Sticker set", "Art print"),
    },
    {
        "id": "parent-humor-gifts",
        "name": "Parent Humor Gifts",
        "focus": "specific parent identities and relatable humor",
        "buyer": "parents and gift buyers looking for identity-led humor",
        "match": lambda value: _contains(value, PARENT_TERMS) and _contains(value, HUMOR_TERMS),
        "products": ("Tumbler", "Graphic shirt", "Mug", "Sweatshirt", "Tote bag", "Decal"),
    },
    {
        "id": "profession-humor-gifts",
        "name": "Profession Humor Gifts",
        "focus": "profession-specific humor and identity gifts",
        "buyer": "professionals, coworkers, and workplace gift buyers",
        "match": lambda value: _contains(value, PROFESSION_TERMS) and _contains(value, ("gift", "mug", "shirt", "tote", "humor", "funny", "wordplay")),
        "products": ("Mug", "Graphic shirt", "Tote bag", "Desk print", "Sticker set", "Notebook"),
    },
    {
        "id": "personalized-musician-gear",
        "name": "Personalized Musician Gear",
        "focus": "personalized and custom musician accessories",
        "buyer": "performers and gift buyers seeking named music gear",
        "match": lambda value: _contains(value, MUSICIAN_TERMS) and _contains(value, ("custom", "personalized", "tuning", "name")),
        "products": ("Personalized microphone", "Microphone name decal", "Custom tuning pegs", "Instrument case decal", "Gear tag", "Gift print"),
    },
)


def build_candidate_portfolio(
    rows: list[dict[str, Any]],
    *,
    store_limit: int = 8,
    product_limit: int = 6,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Return deterministic candidate stores without manufacturing validation."""
    normalized = [_normalize_row(row) for row in rows]
    usable = [row for row in normalized if row is not None]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    theme_by_id = {theme["id"]: theme for theme in THEMES}
    excluded = defaultdict(int)

    for row in usable:
        safety = screen_keyword(row)
        row["safety"] = safety
        if safety["status"] == "blocked":
            excluded[safety["category"] or "blocked"] += 1
            continue
        theme = _theme_for(row["keyword"])
        if theme:
            grouped[theme["id"]].append(row)

    stores = []
    for theme_id, theme_rows in grouped.items():
        theme = theme_by_id[theme_id]
        concept = _store_candidate(theme, theme_rows, product_limit=product_limit)
        if concept is not None:
            stores.append(concept)
    stores.sort(
        key=lambda row: (
            row["validation_state"] == "demand_screened",
            row["test_priority_score"],
            row["evidence"]["keyword_count"],
        ),
        reverse=True,
    )
    stores = stores[: max(1, min(store_limit, 24))]
    demand_ready = any(store["validation_state"] == "demand_screened" for store in stores)
    blockers = []
    if not demand_ready:
        blockers.append(
            "No candidate cluster meets the search-volume threshold; connect Google Ads Keyword Planner or import an approved volume export."
        )
    blockers.extend([
        "Record exact product costs and Etsy fees before approving a product.",
        "Run the 30-day listing test and import Etsy Shop Stats before treating a candidate as calibrated.",
    ])
    return {
        "schema_version": 1,
        "model_version": MODEL_VERSION,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "status": "demand_screened" if demand_ready else "provisional",
        "score_semantics": {
            "name": "test priority",
            "provisional_cap": PROVISIONAL_SCORE_CAP,
            "is_probability": False,
            "description": "Ranks which controlled experiment to run first; it is not a sales or profitability forecast.",
        },
        "thresholds": VALIDATION_THRESHOLDS,
        "test_plan": TEST_PLAN,
        "coverage": {
            "input_rows": len(rows),
            "marketplace_usable_rows": len(usable),
            "candidate_stores": len(stores),
            "excluded_rows": sum(excluded.values()),
            "excluded_by_reason": dict(sorted(excluded.items())),
        },
        "blockers": blockers,
        "stores": stores,
    }


def evaluate_candidate_test(candidate: dict[str, Any], outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    """Evaluate one store test against the published hard thresholds."""
    allowed = {str(row.get("primary_keyword") or "").strip().lower() for row in candidate.get("product_candidates") or []}
    usable = [
        row for row in outcomes
        if str(row.get("keyword") or "").strip().lower() in allowed
    ]
    # A listing period is one observation, even when tagged with several keywords
    # or imported from several sources. Conflicting/overlapping data blocks advance.
    fields = ("impressions", "clicks", "orders", "revenue_usd", "contribution_profit_usd")
    unique, periods, data_blockers = {}, defaultdict(list), []
    for row in usable:
        listing = str(row.get("listing_id") or "")
        start, end = _parse_day(row.get("period_start")), _parse_day(row.get("period_end"))
        if not listing or not start or not end or start > end:
            data_blockers.append("Correct missing listing identities or invalid reporting periods.")
            continue
        identity = (listing, start, end)
        if identity in unique:
            if any(_number(row.get(field)) != _number(unique[identity].get(field)) for field in fields):
                data_blockers.append("Resolve conflicting duplicate listing periods.")
            continue
        if any(start <= old_end and end >= old_start for old_start, old_end in periods[listing]):
            data_blockers.append("Resolve overlapping listing reporting periods.")
            continue
        unique[identity] = row
        periods[listing].append((start, end))
    usable = list(unique.values())
    def total(field):
        values = [_number(row.get(field)) for row in usable]
        return round(sum(values), 2) if values and all(value is not None for value in values) else None
    impressions, clicks, orders, revenue, contribution = (total(field) for field in fields)
    listing_count = len({str(row.get("listing_id") or "") for row in usable if row.get("listing_id")})
    durations = []
    for intervals in periods.values():
        ordered = sorted(intervals)
        if any((start - prior[1]).days != 1 for prior, (start, _end) in zip(ordered, ordered[1:])):
            data_blockers.append("Fill gaps in each listing's reporting coverage.")
        durations.append(sum((end - start).days + 1 for start, end in ordered))
    duration_days = min(durations, default=0)
    click_through_rate = round(clicks / impressions * 100, 2) if impressions and clicks is not None else None
    blockers = list(dict.fromkeys(data_blockers))
    if any(value is None for value in (impressions, clicks, orders, revenue, contribution)):
        blockers.append("Complete missing observed traffic, revenue and contribution metrics; missing values remain unknown.")
    if listing_count < TEST_PLAN["listing_count"]:
        blockers.append(f"Record outcomes for {TEST_PLAN['listing_count']} listings; {listing_count} are present.")
    if duration_days < TEST_PLAN["duration_days"]:
        blockers.append(f"Run the test for {TEST_PLAN['duration_days']} days; {duration_days} are recorded.")
    if impressions is None or impressions < TEST_PLAN["minimum_total_impressions"]:
        blockers.append(f"Reach {TEST_PLAN['minimum_total_impressions']:,} impressions; {impressions if impressions is not None else 'unknown'} are recorded.")
    if click_through_rate is None or click_through_rate < TEST_PLAN["minimum_click_through_rate_pct"]:
        blockers.append(f"Reach {TEST_PLAN['minimum_click_through_rate_pct']}% click-through rate.")
    if orders is None or orders < TEST_PLAN["minimum_orders"]:
        blockers.append(f"Reach {TEST_PLAN['minimum_orders']} orders; {orders} are recorded.")
    if contribution is None or contribution <= 0:
        blockers.append("Record positive contribution profit after fees, advertising, production, shipping, and refunds.")
    collection_incomplete = (
        listing_count < TEST_PLAN["listing_count"]
        or duration_days < TEST_PLAN["duration_days"]
        or impressions is None or impressions < TEST_PLAN["minimum_total_impressions"]
        or bool(data_blockers) or any(value is None for value in (clicks, orders, revenue, contribution))
    )
    status = "advance" if not blockers else "collecting" if collection_incomplete else "hold"
    return {
        "candidate_id": candidate.get("id"),
        "model_version": MODEL_VERSION,
        "status": status,
        "ready_to_advance": status == "advance",
        "metrics": {
            "listings": listing_count,
            "duration_days": duration_days,
            "impressions": impressions,
            "clicks": clicks,
            "click_through_rate_pct": click_through_rate,
            "orders": orders,
            "revenue_usd": revenue,
            "contribution_profit_usd": contribution,
        },
        "thresholds": TEST_PLAN,
        "blockers": blockers,
        "outcome_periods": len(usable),
    }


def screen_keyword(row: dict[str, Any]) -> dict[str, Any]:
    keyword = str(row.get("keyword") or "").lower()
    domain = str(row.get("domain") or "").lower()
    source = str(row.get("source") or "").lower()
    for category, phrases in BLOCKED_PHRASES.items():
        matched = next((phrase for phrase in phrases if phrase in keyword), None)
        if matched:
            return {"status": "blocked", "category": category, "reasons": [f"Contains '{matched}'."]}
    matched_noise = next((phrase for phrase in NOISE_PHRASES if phrase in keyword), None)
    if matched_noise:
        return {"status": "blocked", "category": "non-product search intent", "reasons": [f"Contains '{matched_noise}'."]}
    if domain == "daily_search_trends" or source == "google_daily_trends":
        return {
            "status": "blocked",
            "category": "volatile news or public-figure query",
            "reasons": ["Daily-search-trend phrases require manual identity and rights review."],
        }
    review = [phrase for phrase in REVIEW_PHRASES if phrase in keyword]
    return {
        "status": "review" if review else "pass",
        "category": "ambiguous product intent" if review else None,
        "reasons": [f"Review the intent implied by '{phrase}'." for phrase in review],
    }


def _normalize_row(row: dict[str, Any]) -> dict[str, Any] | None:
    keyword = " ".join(str(row.get("keyword") or "").lower().replace("_", " ").split())
    listing_count = _number(row.get("listing_count") or row.get("etsy_listing_count"))
    sample_count = _number(row.get("sampled_listing_count") or row.get("listing_samples"))
    average_price = _number(row.get("avg_price_usd"))
    if (
        not keyword
        or str(row.get("evidence_status") or "verified") not in {"verified", "partial"}
        or listing_count is None
        or listing_count <= 0
        or sample_count is None
        or sample_count < VALIDATION_THRESHOLDS["minimum_listing_samples_per_keyword"]
        or average_price is None
        or average_price <= 0
    ):
        return None
    volume = _number(row.get("observed_search_volume") or row.get("monthly_searches"))
    normalized = {
        "keyword": keyword,
        "domain": str(row.get("domain") or "discovered"),
        "source": str(row.get("source") or "unknown"),
        "evidence_status": str(row.get("evidence_status") or "verified"),
        "listing_count": int(listing_count),
        "sampled_listing_count": int(sample_count),
        "avg_price_usd": round(average_price, 2),
        "monthly_searches": int(volume) if volume is not None and volume >= 0 else None,
    }
    normalized["components"] = _priority_components(normalized)
    raw = sum(normalized["components"][name] * weight for name, weight in {
        "supply_fit": 0.30,
        "price_fit": 0.20,
        "sample_depth": 0.20,
        "specificity": 0.15,
        "source_strength": 0.15,
    }.items())
    normalized["raw_test_priority"] = round(raw, 1)
    normalized["test_priority_score"] = round(min(PROVISIONAL_SCORE_CAP, raw * PROVISIONAL_SCORE_CAP / 100), 1)
    return normalized


def _priority_components(row: dict[str, Any]) -> dict[str, float]:
    listings = row["listing_count"]
    if listings < 20:
        supply = 20
    elif listings < 200:
        supply = 70
    elif listings <= 5_000:
        supply = 100
    elif listings <= 25_000:
        supply = 80
    elif listings <= 100_000:
        supply = 50
    else:
        supply = 20
    price = row["avg_price_usd"]
    if price < 8:
        price_fit = 20
    elif price < 18:
        price_fit = 60
    elif price <= 60:
        price_fit = 100
    elif price <= 150:
        price_fit = 80
    else:
        price_fit = 50
    word_count = len(row["keyword"].split())
    specificity = 45 if word_count == 1 else 65 if word_count == 2 else 85 if word_count == 3 else 100 if word_count <= 6 else 70
    source = row["source"].lower()
    if "google_suggest" in source:
        source_strength = 100
    elif source.startswith("seasonal_"):
        source_strength = 90
    elif source == "library":
        source_strength = 65
    elif "compound" in source:
        source_strength = 55
    elif "llm" in source:
        source_strength = 40
    else:
        source_strength = 50
    return {
        "supply_fit": float(supply),
        "price_fit": float(price_fit),
        "sample_depth": min(100.0, float(row["sampled_listing_count"])),
        "specificity": float(specificity),
        "source_strength": float(source_strength),
    }


def _theme_for(keyword: str) -> dict[str, Any] | None:
    return next((theme for theme in THEMES if theme["match"](keyword)), None)


def _store_candidate(theme: dict[str, Any], rows: list[dict[str, Any]], *, product_limit: int) -> dict[str, Any] | None:
    deduped = {row["keyword"]: row for row in rows}
    ranked = sorted(deduped.values(), key=lambda row: (row["test_priority_score"], row["sampled_listing_count"]), reverse=True)
    if len(ranked) < 3:
        return None
    top = ranked[:12]
    volumes = [row["monthly_searches"] for row in top if row["monthly_searches"] is not None]
    combined_volume = int(sum(volumes)) if volumes else None
    volume_winners = sum(1 for value in volumes if value >= 100)
    median_listings = round(median(row["listing_count"] for row in top))
    median_price = round(median(row["avg_price_usd"] for row in top), 2)
    demand_screened = (
        len(top) >= VALIDATION_THRESHOLDS["related_keywords"]
        and combined_volume is not None
        and combined_volume >= VALIDATION_THRESHOLDS["combined_monthly_searches"]
        and volume_winners >= VALIDATION_THRESHOLDS["keywords_at_or_above_100_searches"]
        and median_listings <= VALIDATION_THRESHOLDS["maximum_median_etsy_listings"]
    )
    average_priority = sum(row["raw_test_priority"] for row in top[:6]) / min(6, len(top))
    depth = min(100.0, len(ranked) / VALIDATION_THRESHOLDS["related_keywords"] * 100)
    diversity = min(100.0, len({row["source"] for row in ranked}) * 25)
    product_fit = min(100.0, len(theme["products"]) / TEST_PLAN["listing_count"] * 100)
    raw_store_score = average_priority * 0.60 + depth * 0.20 + diversity * 0.10 + product_fit * 0.10
    test_priority = round(raw_store_score if demand_screened else min(PROVISIONAL_SCORE_CAP, raw_store_score * PROVISIONAL_SCORE_CAP / 100), 1)
    confidence = 0
    confidence += 20 if top else 0
    confidence += 20 if all(row["avg_price_usd"] > 0 for row in top) else 0
    confidence += 20 if all(row["sampled_listing_count"] >= 10 for row in top) else 0
    confidence += 15 if any("google_suggest" in row["source"] or row["source"].startswith("seasonal_") for row in top) else 0
    confidence += 25 if demand_screened else 0
    safety_status = "review" if any(row["safety"]["status"] == "review" for row in top) else "pass"
    blockers = []
    if not demand_screened:
        blockers.append("Collect exact monthly search volume for the leading keywords.")
    if len(ranked) < VALIDATION_THRESHOLDS["related_keywords"]:
        blockers.append(f"Expand the cluster from {len(ranked)} to {VALIDATION_THRESHOLDS['related_keywords']} related keywords.")
    if safety_status == "review":
        blockers.append("Resolve ambiguous-intent safety reviews before publishing.")
    blockers.extend([
        "Record exact unit economics for each selected product format.",
        "Import 30-day Etsy Shop Stats after the controlled listing test.",
    ])
    return {
        "id": theme["id"],
        "name": theme["name"],
        "focus": theme["focus"],
        "target_buyer": theme["buyer"],
        "validation_state": "demand_screened" if demand_screened else "provisional_marketplace",
        "test_priority_score": test_priority,
        "score_cap": None if demand_screened else PROVISIONAL_SCORE_CAP,
        "evidence_confidence_pct": confidence,
        "safety": {
            "status": safety_status,
            "reviewed_keywords": len(ranked),
            "note": "Automated screening reduces obvious risk; a final trademark search is still required before publishing.",
        },
        "evidence": {
            "keyword_count": len(ranked),
            "median_etsy_listings": median_listings,
            "listing_range": [min(row["listing_count"] for row in ranked), max(row["listing_count"] for row in ranked)],
            "median_observed_price_usd": median_price,
            "average_listing_sample": round(sum(row["sampled_listing_count"] for row in top) / len(top), 1),
            "combined_monthly_searches": combined_volume,
            "keywords_at_or_above_100_searches": volume_winners if volumes else None,
            "source_count": len({row["source"] for row in ranked}),
        },
        "keywords": [
            {
                "keyword": row["keyword"],
                "test_priority_score": row["test_priority_score"],
                "listing_count": row["listing_count"],
                "sampled_listing_count": row["sampled_listing_count"],
                "avg_price_usd": row["avg_price_usd"],
                "monthly_searches": row["monthly_searches"],
                "source": row["source"],
                "safety_status": row["safety"]["status"],
            }
            for row in top
        ],
        "product_candidates": _product_candidates(theme, top, product_limit),
        "blockers": blockers,
        "test_plan": TEST_PLAN,
    }


def _product_candidates(theme: dict[str, Any], rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    products = list(theme["products"])[: max(1, min(limit, TEST_PLAN["listing_count"]))]
    candidates = []
    used_keywords: set[str] = set()
    hints = {
        "door hanger": ("door",),
        "printable door sign": ("door", "print"),
        "table decor set": ("table",),
        "porch sign": ("porch", "outdoor", "yard"),
        "wall print set": ("wall", "print"),
        "ornament": ("ornament",),
    }
    for index, product_type in enumerate(products):
        preferred = [
            row for row in rows
            if row["keyword"] not in used_keywords
            and _contains(row["keyword"], hints.get(product_type.lower(), ()))
        ]
        fallback = [row for row in rows if row["keyword"] not in used_keywords]
        row = (preferred or fallback or rows)[0]
        used_keywords.add(row["keyword"])
        keyword = row["keyword"]
        title = keyword.title() if product_type.lower() in keyword else f"{keyword.title()} — {product_type}"
        support = [item["keyword"] for item in rows if item["keyword"] != keyword][:3]
        candidates.append({
            "id": f"{theme['id']}-{_slug(product_type)}-{index + 1}",
            "title": title,
            "product_type": product_type,
            "primary_keyword": keyword,
            "supporting_keywords": support,
            "validation_state": "test_only",
            "evidence": {
                "etsy_listing_count": row["listing_count"],
                "listing_samples": row["sampled_listing_count"],
                "observed_average_price_usd": row["avg_price_usd"],
                "monthly_searches": row["monthly_searches"],
            },
            "next_step": "Record supplier or production costs, then create one controlled listing variation.",
        })
    return candidates


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _parse_day(value: Any):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "candidate"
