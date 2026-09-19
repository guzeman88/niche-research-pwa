"""Store concepts assembled only from verified, versioned keyword evidence.

This module deliberately does not invent profitability, pricing, confidence, or
quality scores. It groups already-ranked keyword rows into workable concepts and
passes through observations exactly. A calibrated model may add derived scores
later, under its own explicit score version.
"""
from __future__ import annotations

import json
import math
import re
from collections import OrderedDict
from typing import Any


PRODUCT_TERMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Wall art", ("wall art", "print", "poster", "canvas", "framed")),
    ("Apparel", ("shirt", "tshirt", "tee", "hoodie", "sweatshirt", "crewneck")),
    ("Mugs", ("mug", "coffee cup")),
    ("Stickers", ("sticker", "decal")),
    ("Digital downloads", ("digital download", "downloadable", "printable", "template", "pdf")),
    ("Planners", ("planner", "journal", "notebook", "tracker", "worksheet")),
    ("Craft files", ("svg", "sublimation", "cricut", "cut file")),
    ("Totes", ("tote", "canvas bag")),
    ("Tumblers", ("tumbler", "water bottle")),
    ("Invitations", ("invitation", "invite", "save the date")),
    ("Ornaments", ("ornament",)),
)


def generate_profitable_store_ideas(
    limit: int = 12,
    signal_limit: int = 800,
    domain: str | None = None,
) -> list[dict[str, Any]]:
    """Return evidence-backed concepts; the name is kept for API compatibility."""
    from pipeline import keyword_database as kdb

    rows = kdb.get_store_idea_signals(limit=signal_limit, domain=domain)
    return generate_store_ideas_from_rows(rows, limit)


def generate_store_ideas_from_rows(
    rows: list[dict[str, Any]],
    limit: int = 12,
) -> list[dict[str, Any]]:
    """Group verified model output without adding a second heuristic rank."""
    verified = [row for row in rows if _is_verified_versioned(row)]
    if not verified:
        return []

    groups: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    for row in verified:
        keyword = str(row.get("keyword") or "").strip()
        if not keyword:
            continue
        group_key = str(row.get("domain") or "uncategorized").strip() or "uncategorized"
        groups.setdefault(group_key, []).append(row)

    concepts = [_concept_from_group(group, group_rows) for group, group_rows in groups.items()]
    return [concept for concept in concepts if concept is not None][:limit]


def _is_verified_versioned(row: dict[str, Any]) -> bool:
    return row.get("evidence_status") == "verified" and bool(row.get("score_version"))


def _concept_from_group(group: str, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    keywords = [_keyword_payload(row) for row in rows if str(row.get("keyword") or "").strip()]
    if not keywords:
        return None

    focus = group.replace("_", " ").strip()
    display_focus = focus.title() if focus and focus != "uncategorized" else "Verified keyword collection"
    name = f"{display_focus} Store"
    products = _observed_product_types([item["keyword"] for item in keywords])
    observations = _observation_summary(rows)
    cluster_id = _slug(focus or name)
    listing_blueprints = [_listing_blueprint(item, products) for item in keywords]
    missing = _missing_evidence(rows)
    observed_price_range = _observed_price_range(rows)
    observed_price_band = _observed_price_band(rows)

    return {
        "id": _slug(name),
        "name": name,
        "focus": display_focus,
        "anchorType": "theme",
        "keywords": keywords,
        "productTypes": products,
        "avgOpportunity": _exact_average(row.get("opportunity_score") for row in rows),
        "avgGap": _exact_average(
            row.get("composite_gap_score") if row.get("composite_gap_score") is not None else row.get("gap_score")
            for row in rows
        ),
        "nicheScore": None,
        "storeQualityScore": None,
        "recommendationScore": None,
        "commercialPotentialScore": None,
        "qualityGrade": None,
        "specificityScore": None,
        "sourceDiversityScore": None,
        "productMixScore": None,
        "keywordDepthScore": None,
        "profitScore": None,
        "rawProfitScore": None,
        "profitGrade": None,
        "cohesion": None,
        "trendLift": None,
        "demandScore": _exact_average(row.get("demand_score") for row in rows),
        "marginScore": _exact_average(row.get("margin_score") for row in rows),
        "competitionEase": None,
        "buyerIntent": None,
        "confidenceScore": None,
        "avgPrice": _exact_average(row.get("avg_price_usd") for row in rows),
        "priceRange": observed_price_range,
        "priceBasis": "observed" if observed_price_range else None,
        "estimatedGrossMargin": None,
        "estimatedMonthlyRevenue": _exact_sum(row.get("monthly_revenue_usd") for row in rows),
        "profitabilityEvidence": {
            "evidenceScore": None,
            "evidenceLevel": "TBD — no calibrated profitability model",
            "observedPriceBand": observed_price_band,
            "priceBasis": "observed" if observed_price_band else None,
            "estimatedGrossMargin": None,
            "sampledMonthlyRevenue": _exact_sum(row.get("monthly_revenue_usd") for row in rows),
            "revenuePerListing": _exact_average(row.get("revenue_per_listing") for row in rows),
            "revenueDensityScore": None,
            "marketTractionScore": None,
            "sellerWeaknessScore": None,
            "avgListingCount": _exact_average(row.get("listing_count") for row in rows),
            "avgFavorites": _exact_average(row.get("avg_favorites") for row in rows),
            "signalsWithDeepMarketData": sum(1 for row in rows if _has_market_observations(row)),
            "missing": missing,
        },
        "scoreBreakdown": None,
        "rationale": f"Grouped from {len(keywords)} verified, versioned keyword record(s) in {display_focus}.",
        "evidence": observations,
        "evidenceDepth": {
            "score": None,
            "level": "TBD — evidence is counted, not heuristically scored",
            "keywordSignals": len(keywords),
            "scoredKeywords": sum(1 for row in rows if _primary_score(row) is not None),
            "pricedKeywords": sum(1 for row in rows if _number(row.get("avg_price_usd")) is not None),
            "revenueSignals": sum(1 for row in rows if _number(row.get("monthly_revenue_usd")) is not None),
            "revenueDensitySignals": sum(1 for row in rows if _number(row.get("revenue_per_listing")) is not None),
            "competitionSignals": sum(1 for row in rows if _number(row.get("competition_quality")) is not None),
            "buyerTractionSignals": sum(1 for row in rows if _number(row.get("avg_favorites")) is not None),
            "trendSignals": sum(1 for row in rows if _number(row.get("trend_score")) is not None),
            "productTypes": len(products),
            "missing": missing,
        },
        "keywordClusters": [{
            "id": cluster_id,
            "label": display_focus,
            "clusterType": "domain",
            "keywords": keywords,
            "primaryProducts": products,
            "avgOpportunity": _exact_average(row.get("opportunity_score") for row in rows),
            "avgGap": _exact_average(row.get("gap_score") for row in rows),
            "avgDemand": _exact_average(row.get("demand_score") for row in rows),
            "competitionEase": None,
            "buyerIntent": None,
            "clusterQualityScore": None,
            "specificityScore": None,
            "sourceDiversityScore": None,
            "productMixScore": None,
            "keywordDepthScore": None,
            "revenueDensityScore": None,
            "avgRevenuePerListing": _exact_average(row.get("revenue_per_listing") for row in rows),
            "marketEvidenceScore": None,
            "profitabilityScore": None,
        }],
        "listingBlueprints": listing_blueprints,
        "storeRecommendation": {
            "positioning": f"Use the verified {display_focus} keywords as a research collection, not a profit claim.",
            "targetCustomer": "TBD — validate with observed buyers and conversions",
            "recommendedCollections": [display_focus],
            "launchListingIdeas": [item["title"] for item in listing_blueprints],
            "listingGenerationInputs": [],
            "keywordStrategy": {
                "primaryKeywords": [item["keyword"] for item in keywords],
                "expansionKeywords": [],
                "clusterCount": 1,
                "listingBlueprintCount": len(listing_blueprints),
            },
            "storeQualityScore": None,
            "qualityGrade": None,
            "qualityInputs": None,
            "qualityPriority": "TBD — requires a calibrated outcome model",
            "qualityOptimizationPlan": ["Collect actual listing outcomes before assigning a quality score."],
            "profitPriority": "TBD — record exact unit economics and outcomes first",
            "profitOptimizationPlan": ["Record actual fees, production cost, ad spend, refunds, orders, and revenue."],
            "validationPriorities": [
                {"evidenceGap": item, "action": f"Collect {item}.", "keywords": [entry["keyword"] for entry in keywords]}
                for item in missing
            ],
            "nextValidationStep": "Record exact unit economics, then run controlled listings and capture outcomes.",
        },
        "feeModel": None,
        "listingIdeas": [item["title"] for item in listing_blueprints],
        "risks": missing or ["Profitability remains TBD until real outcomes are recorded."],
        "profitDrivers": observations,
        "validationChecklist": [f"Collect {item}." for item in missing],
    }


def _keyword_payload(row: dict[str, Any]) -> dict[str, Any]:
    keyword = str(row.get("keyword") or "").strip()
    products = _observed_product_types([keyword])
    return {
        "keyword": keyword,
        "opportunity": _number(row.get("opportunity_score")),
        "gap": _number(row.get("composite_gap_score") if row.get("composite_gap_score") is not None else row.get("gap_score")),
        "product": products[0] if products else "TBD",
        "demand": _number(row.get("demand_score")),
        "margin": _number(row.get("margin_score")),
        "estimatedRevenue": _number(row.get("monthly_revenue_usd")),
        "revenuePerListing": _number(row.get("revenue_per_listing")),
        "avgPrice": _number(row.get("avg_price_usd")),
        "competitionEase": None,
        "marketEvidenceScore": None,
        "profitabilityIndex": _number(row.get("profitability_index")),
        "avgFavorites": _number(row.get("avg_favorites")),
        "buyerIntent": None,
        "profitGap": _number(row.get("profit_gap_score")),
        "sourceStrength": None,
        "specificityScore": None,
        "priceRange": _row_price_range(row),
        "sources": _parse_sources(row.get("sources_used")),
        "scoreVersion": row.get("score_version"),
        "evidenceStatus": row.get("evidence_status"),
    }


def _listing_blueprint(keyword: dict[str, Any], products: list[str]) -> dict[str, Any]:
    product = keyword.get("product") if keyword.get("product") != "TBD" else (products[0] if products else "TBD")
    primary = str(keyword["keyword"])
    return {
        "id": _slug(primary),
        "title": primary.title(),
        "primaryKeyword": primary,
        "supportingKeywords": [],
        "sourceClusterId": None,
        "sourceClusterLabel": None,
        "productType": product,
        "buyerIntent": None,
        "priceBand": keyword.get("priceRange"),
        "tags": [primary],
        "profitabilityScore": None,
        "listingQualityScore": None,
        "profitInputs": None,
        "qualityInputs": None,
        "evidenceLevel": "verified keyword; profitability TBD",
        "profitRationale": "No profitability claim until exact economics and listing outcomes are recorded.",
    }


def _missing_evidence(rows: list[dict[str, Any]]) -> list[str]:
    checks = (
        ("observed price data", "avg_price_usd"),
        ("observed revenue data", "monthly_revenue_usd"),
        ("listing supply data", "listing_count"),
        ("buyer traction data", "avg_favorites"),
    )
    missing = [label for label, field in checks if not any(_number(row.get(field)) is not None for row in rows)]
    return [*missing, "exact product costs and fees", "actual listing outcomes"]


def _observation_summary(rows: list[dict[str, Any]]) -> list[str]:
    summary = [f"{len(rows)} verified keyword record(s) with an explicit score version"]
    priced = sum(1 for row in rows if _number(row.get("avg_price_usd")) is not None)
    supplied = sum(1 for row in rows if _number(row.get("listing_count")) is not None)
    if priced:
        summary.append(f"Observed price data exists for {priced} keyword record(s)")
    if supplied:
        summary.append(f"Observed listing supply exists for {supplied} keyword record(s)")
    return summary


def _has_market_observations(row: dict[str, Any]) -> bool:
    return all(_number(row.get(field)) is not None for field in ("avg_price_usd", "listing_count"))


def _primary_score(row: dict[str, Any]) -> float | None:
    for field in ("profitability_index", "opportunity_score", "gap_score", "composite_gap_score"):
        value = _number(row.get(field))
        if value is not None:
            return value
    return None


def _observed_product_types(keywords: list[str]) -> list[str]:
    normalized = " ".join(keyword.lower() for keyword in keywords)
    return [label for label, terms in PRODUCT_TERMS if any(term in normalized for term in terms)]


def _observed_price_band(rows: list[dict[str, Any]]) -> dict[str, float | None] | None:
    band = {
        "p25": _exact_average(row.get("price_p25_usd") for row in rows),
        "median": _exact_average(row.get("price_median_usd") for row in rows),
        "p75": _exact_average(row.get("price_p75_usd") for row in rows),
        "avg": _exact_average(row.get("avg_price_usd") for row in rows),
    }
    return band if any(value is not None for value in band.values()) else None


def _row_price_range(row: dict[str, Any]) -> dict[str, float] | None:
    low = _number(row.get("price_min_usd"))
    high = _number(row.get("price_max_usd"))
    return {"min": low, "max": high} if low is not None and high is not None else None


def _observed_price_range(rows: list[dict[str, Any]]) -> dict[str, float] | None:
    usable_lows = [value for value in (_number(row.get("price_min_usd")) for row in rows) if value is not None]
    usable_highs = [value for value in (_number(row.get("price_max_usd")) for row in rows) if value is not None]
    if not usable_lows or not usable_highs:
        return None
    return {"min": min(usable_lows), "max": max(usable_highs)}


def _exact_average(values) -> float | None:
    usable = [value for value in (_number(item) for item in values) if value is not None]
    return round(sum(usable) / len(usable), 2) if usable else None


def _exact_sum(values) -> float | None:
    usable = [value for value in (_number(item) for item in values) if value is not None]
    return round(sum(usable), 2) if usable else None


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _parse_sources(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return [part.strip() for part in stripped.split(",") if part.strip()]
        return _parse_sources(parsed)
    return []


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "verified-keyword-collection"
