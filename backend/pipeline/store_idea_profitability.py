"""Profit-ranked store idea generation from cached keyword intelligence."""
from __future__ import annotations

import math
import re
import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TaxonomyItem:
    id: str
    label: str
    terms: tuple[str, ...]


@dataclass
class KeywordSignal:
    keyword: str
    domain: str
    opportunity: float
    gap: float
    demand: float
    margin: float
    trend: float
    competition_quality: float
    avg_price: float
    revenue: float
    listing_count: int
    listing_efficiency: float
    revenue_per_listing: float
    price_p25: float
    price_median: float
    price_p75: float
    avg_favorites: float
    max_favorites: int
    pct_high_favorites: float
    pct_star_sellers: float
    pct_bestsellers: float
    market_evidence_score: float
    profitability_index: float
    buyer_intent_score: float
    profit_gap_score: float
    volume_gap_score: float
    quality_gap_score: float
    tag_gap_score: float
    style_gap_score: float
    price_gap_score: float
    recency_gap_score: float
    listings_analyzed: int
    trajectory: str
    breakout: bool
    products: list[str]
    audience: list[TaxonomyItem]
    theme: list[TaxonomyItem]
    style: list[TaxonomyItem]
    occasion: list[TaxonomyItem]
    intent: list[TaxonomyItem]
    price_min: float = 0.0
    price_max: float = 0.0
    entry_angle: str = ""
    scanned_at: str = ""
    sources: list[str] = field(default_factory=list)
    source_strength: float = 0.0


@dataclass
class ClusterSeed:
    primary: TaxonomyItem
    primary_type: str
    secondary: TaxonomyItem | None = None
    secondary_type: str | None = None
    signals: list[KeywordSignal] = field(default_factory=list)


PRODUCT_TERMS: tuple[TaxonomyItem, ...] = (
    TaxonomyItem("wall_art", "Wall art", ("wall art", "print", "prints", "poster", "posters", "canvas", "decor", "frame", "framed")),
    TaxonomyItem("apparel", "Apparel", ("shirt", "shirts", "tshirt", "tee", "tees", "hoodie", "sweatshirt", "crewneck", "apparel")),
    TaxonomyItem("mug", "Mugs", ("mug", "mugs", "cup", "coffee cup")),
    TaxonomyItem("sticker", "Stickers", ("sticker", "stickers", "decal", "decals")),
    TaxonomyItem("digital_download", "Digital downloads", ("digital download", "download", "downloadable", "printable", "template", "pdf")),
    TaxonomyItem("planner", "Planners", ("planner", "journal", "notebook", "tracker", "worksheet")),
    TaxonomyItem("svg", "Craft files", ("svg", "png", "sublimation", "cricut", "cut file")),
    TaxonomyItem("tote", "Totes", ("tote", "bag", "canvas bag")),
    TaxonomyItem("tumbler", "Tumblers", ("tumbler", "water bottle")),
    TaxonomyItem("invitation", "Invitations", ("invitation", "invite", "announcement", "save the date")),
    TaxonomyItem("ornament", "Ornaments", ("ornament", "ornaments")),
)

AUDIENCES: tuple[TaxonomyItem, ...] = (
    TaxonomyItem("nurse", "Nurses", ("nurse", "nurses", "rn", "nursing", "icu", "er nurse")),
    TaxonomyItem("teacher", "Teachers", ("teacher", "teachers", "teaching", "classroom", "educator")),
    TaxonomyItem("mom", "Moms", ("mom", "mama", "mother", "mommy", "new mom")),
    TaxonomyItem("dad", "Dads", ("dad", "daddy", "father", "papa")),
    TaxonomyItem("book_lover", "Book lovers", ("book lover", "bookish", "reader", "reading", "library", "book club")),
    TaxonomyItem("bride", "Brides", ("bride", "bridal", "bridesmaid", "maid of honor", "bachelorette")),
    TaxonomyItem("baby_family", "New families", ("baby", "newborn", "nursery", "pregnancy", "family")),
    TaxonomyItem("pet_parent", "Pet parents", ("dog mom", "cat mom", "pet", "dog lover", "cat lover")),
    TaxonomyItem("gamer", "Gamers", ("gamer", "gaming", "video game")),
    TaxonomyItem("faith_buyer", "Faith buyers", ("christian", "bible", "faith", "church", "jesus")),
    TaxonomyItem("small_business", "Small business owners", ("small business", "boutique", "salon", "realtor", "coach")),
)

THEMES: tuple[TaxonomyItem, ...] = (
    TaxonomyItem("botanical", "Botanical", ("flower", "floral", "botanical", "plant", "garden", "wildflower")),
    TaxonomyItem("celestial", "Celestial", ("moon", "sun", "stars", "zodiac", "astrology", "celestial")),
    TaxonomyItem("coffee", "Coffee", ("coffee", "latte", "espresso", "cafe")),
    TaxonomyItem("mental_health", "Mental health", ("mental health", "therapy", "self care", "anxiety", "affirmation")),
    TaxonomyItem("fitness", "Fitness", ("gym", "fitness", "workout", "pilates", "yoga", "running")),
    TaxonomyItem("travel", "Travel", ("travel", "vacation", "camping", "hiking", "adventure")),
    TaxonomyItem("western", "Western", ("western", "cowgirl", "cowboy", "rodeo", "country")),
    TaxonomyItem("pickleball", "Pickleball", ("pickleball",)),
    TaxonomyItem("sports", "Sports", ("baseball", "football", "soccer", "basketball", "softball")),
    TaxonomyItem("music", "Music", ("music", "band", "song", "album", "playlist")),
    TaxonomyItem("astrology", "Astrology", ("astrology", "zodiac", "horoscope", "birth chart", "moon sign", "rising sign", "aries", "taurus", "gemini", "cancer", "leo", "virgo", "libra", "scorpio", "sagittarius", "capricorn", "aquarius", "pisces")),
    TaxonomyItem("reading", "Reading culture", ("mystery reader", "horror lover", "audiobook", "manga reader", "playlist gift")),
    TaxonomyItem("internet_culture", "Internet culture", ("rizz", "delulu", "girl dinner", "villain era", "hot girl walk", "mob wife", "office siren")),
)

STYLES: tuple[TaxonomyItem, ...] = (
    TaxonomyItem("dark_academia", "Dark academia", ("dark academia", "academia", "gothic library")),
    TaxonomyItem("cottagecore", "Cottagecore", ("cottagecore", "cottage", "fairycore")),
    TaxonomyItem("boho", "Boho", ("boho", "bohemian")),
    TaxonomyItem("minimalist", "Minimalist", ("minimalist", "minimal", "simple", "clean")),
    TaxonomyItem("retro", "Retro", ("retro", "vintage", "70s", "80s", "90s", "groovy")),
    TaxonomyItem("coastal", "Coastal", ("coastal", "beach", "ocean", "seaside")),
    TaxonomyItem("goth", "Goth", ("goth", "gothic", "witchy", "spooky")),
    TaxonomyItem("kawaii", "Kawaii", ("kawaii", "cute", "chibi")),
    TaxonomyItem("y2k", "Y2K", ("y2k", "2000s")),
    TaxonomyItem("farmhouse", "Farmhouse", ("farmhouse", "rustic")),
)

OCCASIONS: tuple[TaxonomyItem, ...] = (
    TaxonomyItem("wedding", "Wedding", ("wedding", "bridal shower", "bachelorette", "engagement")),
    TaxonomyItem("birthday", "Birthday", ("birthday", "birth year")),
    TaxonomyItem("christmas", "Christmas", ("christmas", "xmas", "holiday", "santa")),
    TaxonomyItem("halloween", "Halloween", ("halloween", "spooky")),
    TaxonomyItem("valentine", "Valentine", ("valentine", "galentine")),
    TaxonomyItem("graduation", "Graduation", ("graduation", "graduate", "class of")),
    TaxonomyItem("baby_shower", "Baby shower", ("baby shower", "gender reveal")),
    TaxonomyItem("mothers_day", "Mother's Day", ("mothers day", "mother's day")),
    TaxonomyItem("fathers_day", "Father's Day", ("fathers day", "father's day")),
)

INTENTS: tuple[TaxonomyItem, ...] = (
    TaxonomyItem("funny", "Humor", ("funny", "humor", "sarcastic", "snarky", "meme")),
    TaxonomyItem("personalized", "Personalized", ("personalized", "custom", "name", "monogram", "initial")),
    TaxonomyItem("giftable", "Giftable", ("gift", "gifts", "present")),
    TaxonomyItem("motivational", "Motivational", ("motivational", "inspirational", "affirmation", "positive")),
    TaxonomyItem("matching", "Matching sets", ("matching", "couple", "family matching", "team")),
)

STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "best", "by", "for", "from", "gift",
    "gifts", "in", "is", "it", "of", "on", "or", "set", "the", "to", "with", "without",
}

GENERIC_DOMAINS = {
    "aesthetics", "hobbies", "trending micro niches", "pop culture themes",
    "identity values", "pod product types", "home decor themes", "occasions holidays",
}

PRODUCT_ECONOMICS = {
    "digital_download": {"cost": 0.30, "floor": 4.99, "ceiling": 18.0, "ease": 92},
    "svg": {"cost": 0.25, "floor": 3.99, "ceiling": 14.0, "ease": 90},
    "planner": {"cost": 0.50, "floor": 7.99, "ceiling": 24.0, "ease": 88},
    "invitation": {"cost": 0.45, "floor": 8.0, "ceiling": 28.0, "ease": 86},
    "wall_art": {"cost": 5.50, "floor": 16.0, "ceiling": 48.0, "ease": 75},
    "sticker": {"cost": 2.20, "floor": 5.0, "ceiling": 14.0, "ease": 78},
    "mug": {"cost": 8.00, "floor": 16.0, "ceiling": 28.0, "ease": 70},
    "tote": {"cost": 10.50, "floor": 22.0, "ceiling": 38.0, "ease": 68},
    "tumbler": {"cost": 14.00, "floor": 26.0, "ceiling": 46.0, "ease": 62},
    "apparel": {"cost": 13.50, "floor": 24.0, "ceiling": 44.0, "ease": 64},
    "ornament": {"cost": 6.00, "floor": 14.0, "ceiling": 28.0, "ease": 72},
}

ETSY_LISTING_FEE_USD = 0.20
ETSY_TRANSACTION_FEE_RATE = 0.065
ESTIMATED_US_PAYMENT_RATE = 0.03
ESTIMATED_US_PAYMENT_FIXED_USD = 0.25
OFFSITE_ADS_RATE_LOW = 0.12
OFFSITE_ADS_RATE_HIGH = 0.15

BUYER_INTENT_TERMS = {
    "gift", "gifts", "personalized", "custom", "name", "wedding", "birthday", "bride",
    "bridesmaid", "christmas", "holiday", "mothers", "fathers", "baby", "teacher",
    "nurse", "matching", "template", "printable", "svg",
}


def generate_profitable_store_ideas(limit: int = 12, signal_limit: int = 800, domain: str | None = None) -> list[dict[str, Any]]:
    from pipeline import keyword_database as kdb

    rows = kdb.get_store_idea_signals(limit=signal_limit, domain=domain)
    signals = [
        signal for signal in (_to_signal(row) for row in rows)
        if signal and signal.source_strength > 0
    ]
    signals.sort(key=_weighted_keyword_score, reverse=True)
    signals = signals[:320]
    if not signals:
        return []

    ideas = [
        idea for idea in (_to_store_idea(cluster) for cluster in _merge_small_clusters(_seed_clusters(signals)))
        if idea
    ]
    ideas.sort(key=lambda item: (item.get("profitScore") or 0, item["nicheScore"]), reverse=True)
    unique: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for idea in ideas:
        idea_id = str(idea.get("id") or "")
        if not idea_id or idea_id in seen_ids:
            continue
        seen_ids.add(idea_id)
        unique.append(idea)
    return unique[:limit]


def _to_signal(row: dict[str, Any]) -> KeywordSignal | None:
    keyword = str(row.get("keyword") or "").strip()
    if not keyword:
        return None

    normalized = _normalize(keyword)
    domain = str(row.get("domain") or "discovered").replace("_", " ")
    if _looks_like_default_scan(row):
        return None
    sources = _parse_sources(row.get("sources_used"))
    has_real_gap = _has_real_gap_evidence(row)
    gap = _score(row.get("composite_gap_score") or row.get("gap_score")) if has_real_gap else 0.0
    has_real_competition = _has_real_competition_evidence(row)
    return KeywordSignal(
        keyword=keyword,
        domain=domain,
        opportunity=_score(row.get("opportunity_score")),
        gap=gap,
        demand=_score(row.get("demand_score")),
        margin=_score(row.get("margin_score")),
        trend=_score(row.get("trend_score")),
        competition_quality=_score(row.get("competition_quality") or row.get("competition_score")) if has_real_competition else 0.0,
        avg_price=_number(row.get("avg_price_usd")),
        revenue=_number(row.get("monthly_revenue_usd")),
        listing_count=int(_number(row.get("listing_count"))),
        listing_efficiency=_score(row.get("listing_efficiency")),
        revenue_per_listing=_number(row.get("revenue_per_listing") or row.get("gap_revenue_per_listing")),
        price_p25=_number(row.get("price_p25_usd")),
        price_median=_number(row.get("price_median_usd")),
        price_p75=_number(row.get("price_p75_usd")),
        avg_favorites=_number(row.get("avg_favorites")),
        max_favorites=int(_number(row.get("max_favorites"))),
        pct_high_favorites=_number(row.get("pct_high_favorites")),
        pct_star_sellers=_number(row.get("pct_star_sellers")),
        pct_bestsellers=_number(row.get("pct_bestsellers")),
        market_evidence_score=_score(row.get("market_evidence_score") or row.get("gap_market_evidence_score")),
        profitability_index=_score(row.get("profitability_index")),
        buyer_intent_score=_score(row.get("buyer_intent_score")),
        profit_gap_score=_score(row.get("profit_gap_score")),
        volume_gap_score=_score(row.get("volume_gap_score")),
        quality_gap_score=_score(row.get("quality_gap_score")),
        tag_gap_score=_score(row.get("tag_gap_score")),
        style_gap_score=_score(row.get("style_gap_score")),
        price_gap_score=_score(row.get("price_gap_score")),
        recency_gap_score=_score(row.get("recency_gap_score")),
        listings_analyzed=int(_number(row.get("listings_analyzed"))),
        trajectory=str(row.get("trajectory") or ""),
        breakout=bool(row.get("breakout_flag")),
        products=_match_products(normalized, domain),
        audience=_match_taxonomy(normalized, AUDIENCES),
        theme=_match_taxonomy(normalized, THEMES),
        style=_match_taxonomy(normalized, STYLES),
        occasion=_match_taxonomy(normalized, OCCASIONS),
        intent=_match_taxonomy(normalized, INTENTS),
        price_min=_number(row.get("recommended_price_min")),
        price_max=_number(row.get("recommended_price_max")),
        entry_angle=str(row.get("entry_angle") or row.get("entry_strategy") or ""),
        scanned_at=str(row.get("scanned_at") or ""),
        sources=sources,
        source_strength=_source_strength(sources, row),
    )


def _looks_like_default_scan(row: dict[str, Any]) -> bool:
    """Drop underspecified scan rows that only contain the scanner's old defaults."""
    if _has_real_gap_evidence(row):
        return False
    if _source_strength(_parse_sources(row.get("sources_used")), row) > 0:
        return False
    market_evidence = _number(row.get("market_evidence_score") or row.get("gap_market_evidence_score"))
    if market_evidence < 20:
        return True

    has_market_evidence = any(
        _number(row.get(field)) > 0
        for field in (
            "avg_price_usd",
            "monthly_revenue_usd",
            "listing_count",
            "recommended_price_min",
            "recommended_price_max",
            "listings_analyzed",
            "revenue_per_listing",
            "avg_favorites",
        )
    )
    if has_market_evidence:
        return False

    return (
        math.isclose(_number(row.get("opportunity_score")), 65.0, abs_tol=0.01)
        and math.isclose(_number(row.get("demand_score")), 100.0, abs_tol=0.01)
        and math.isclose(_number(row.get("margin_score")), 50.0, abs_tol=0.01)
        and math.isclose(_number(row.get("competition_score")), 50.0, abs_tol=0.01)
        and math.isclose(_number(row.get("trend_score")), 50.0, abs_tol=0.01)
    )


def _parse_sources(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    except json.JSONDecodeError:
        pass
    return [item.strip() for item in re.split(r"[,|]", text) if item.strip()]


def _source_strength(sources: list[str], row: dict[str, Any]) -> float:
    normalized = {source.lower() for source in sources}
    if normalized and normalized <= {"estimated_from_domain"}:
        return 0.0
    score = 0.0
    if "etsy_autocomplete" in normalized:
        score += 42.0
    if "google_trends" in normalized:
        score += 36.0
    if "google_suggest" in normalized:
        score += 32.0
    if "etsy_search" in normalized or "etsy_open_api" in normalized:
        score += 50.0
    if _number(row.get("score_delta")) > 0:
        score += min(10.0, _number(row.get("score_delta")))
    if _number(row.get("breakout_flag")) > 0:
        score += 8.0
    return _clamp(score)


def _has_real_gap_evidence(row: dict[str, Any]) -> bool:
    if _number(row.get("listings_analyzed")) > 0:
        return _number(row.get("composite_gap_score")) > 0
    return _number(row.get("gap_score")) > 0 and (
        _number(row.get("listing_efficiency")) > 0
        or _number(row.get("listing_count")) > 0
        or _number(row.get("market_evidence_score")) > 0
    )


def _has_real_competition_evidence(row: dict[str, Any]) -> bool:
    return (
        _number(row.get("listing_count")) > 0
        or _number(row.get("listings_analyzed")) > 0
        or _number(row.get("market_evidence_score")) > 0
        or _number(row.get("gap_market_evidence_score")) > 0
    )


def _seed_clusters(signals: list[KeywordSignal]) -> list[ClusterSeed]:
    by_key: dict[str, ClusterSeed] = {}
    for signal in signals:
        primary = _choose_primary(signal)
        if not primary:
            continue
        primary_type, primary_item = primary
        secondary = _choose_secondary(signal, primary_item.id)
        if secondary:
            secondary_type, secondary_item = secondary
            key = f"{primary_type}:{primary_item.id}/{secondary_type}:{secondary_item.id}"
        else:
            secondary_type = None
            secondary_item = None
            key = f"{primary_type}:{primary_item.id}"

        if key not in by_key:
            by_key[key] = ClusterSeed(primary_item, primary_type, secondary_item, secondary_type, [])
        by_key[key].signals.append(signal)
    return list(by_key.values())


def _merge_small_clusters(clusters: list[ClusterSeed]) -> list[ClusterSeed]:
    result: list[ClusterSeed] = []
    by_primary: dict[str, ClusterSeed] = {}
    for cluster in clusters:
        strong = len(cluster.signals) >= 3 or any(_weighted_keyword_score(signal) >= 78 for signal in cluster.signals)
        if strong:
            result.append(cluster)
            continue
        key = f"{cluster.primary_type}:{cluster.primary.id}"
        if key not in by_primary:
            by_primary[key] = ClusterSeed(cluster.primary, cluster.primary_type, None, None, [])
        by_primary[key].signals.extend(cluster.signals)
    return result + list(by_primary.values())


def _to_store_idea(cluster: ClusterSeed) -> dict[str, Any] | None:
    signals = _unique_by_keyword(cluster.signals)
    signals.sort(key=_weighted_keyword_score, reverse=True)
    if len(signals) < 2:
        return None

    product_types = _rank_products(signals)
    focus = _format_focus(cluster)
    avg_opportunity = _average([signal.opportunity for signal in signals])
    avg_gap = _average([signal.gap for signal in signals])
    avg_demand = _average([signal.demand for signal in signals])
    avg_margin = _average([signal.margin for signal in signals])
    avg_price = _average([signal.avg_price for signal in signals if signal.avg_price > 0])
    revenue_signals = [signal.revenue for signal in signals if signal.revenue > 0]
    revenue = sum(revenue_signals)
    avg_revenue_per_listing = _average([signal.revenue_per_listing for signal in signals if signal.revenue_per_listing > 0])
    avg_listing_efficiency = _average([signal.listing_efficiency for signal in signals if signal.listing_efficiency > 0])
    avg_market_evidence = _average([signal.market_evidence_score for signal in signals if signal.market_evidence_score > 0])
    avg_profitability_index = _average([signal.profitability_index for signal in signals if signal.profitability_index > 0])
    avg_favorites = _average([signal.avg_favorites for signal in signals if signal.avg_favorites > 0])
    avg_pct_bestsellers = _average([signal.pct_bestsellers for signal in signals if signal.pct_bestsellers > 0])
    avg_pct_star_sellers = _average([signal.pct_star_sellers for signal in signals if signal.pct_star_sellers > 0])
    observed_price_band = _observed_price_band(signals)
    competition_ease = _calculate_competition_ease(signals)
    cohesion = _calculate_cohesion(signals, cluster)
    trend_score = _calculate_trend_score(signals)
    buyer_intent = _calculate_buyer_intent(signals)
    confidence = _calculate_confidence(signals)
    evidence_depth = _calculate_evidence_depth(signals, product_types)
    confidence = min(confidence, _number(evidence_depth.get("score")))
    has_observed_price_basis = (
        avg_price > 0
        or any(signal.price_p25 > 0 and signal.price_p75 > 0 for signal in signals)
        or any(signal.price_min > 0 and signal.price_max > 0 for signal in signals)
    )
    price_floor, price_ceiling = _price_range(signals, product_types, avg_price) if has_observed_price_basis else (0.0, 0.0)
    gross_margin = _estimated_gross_margin(product_types, price_floor, price_ceiling) if has_observed_price_basis else 0.0
    margin_signal = gross_margin if has_observed_price_basis else min(avg_margin, 45)
    price_power = _calculate_price_power(price_floor, price_ceiling, avg_price, gross_margin)
    revenue_density = _calculate_revenue_density(avg_revenue_per_listing, avg_listing_efficiency, revenue, signals)
    market_traction = _calculate_market_traction(avg_favorites, avg_pct_bestsellers)
    seller_weakness = _calculate_seller_weakness(avg_pct_star_sellers, avg_pct_bestsellers, competition_ease)
    fulfillment_ease = _average([PRODUCT_ECONOMICS.get(product, PRODUCT_ECONOMICS["digital_download"])["ease"] for product in product_types])
    has_profit_evidence = (
        has_observed_price_basis
        or bool(revenue_signals)
        or avg_revenue_per_listing > 0
        or avg_profitability_index > 0
    )

    keyword_lift = min(12, len(signals) * 1.8)
    diversity_lift = min(8, max(0, len(product_types) - 1) * 2.5)
    niche_score = _clamp(
        avg_opportunity * 0.42
        + avg_gap * 0.24
        + cohesion * 0.18
        + keyword_lift
        + diversity_lift
        + trend_score * 0.08
    )
    raw_profit_score = _clamp(
        margin_signal * 0.22
        + revenue_density * 0.18
        + competition_ease * 0.14
        + avg_gap * 0.12
        + price_power * 0.10
        + avg_demand * 0.09
        + buyer_intent * 0.07
        + seller_weakness * 0.03
        + market_traction * 0.02
        + fulfillment_ease * 0.02
        + evidence_depth["score"] * 0.01
    )
    if avg_profitability_index > 0:
        raw_profit_score = _clamp(raw_profit_score * 0.74 + avg_profitability_index * 0.26)
    profit_score = (
        _evidence_adjusted_profit_score(raw_profit_score, evidence_depth, has_observed_price_basis, bool(revenue_signals))
        if has_profit_evidence
        else None
    )
    name = _make_store_name(cluster, product_types)
    keyword_clusters = _make_keyword_clusters(signals, cluster, product_types)
    listing_blueprints = _make_listing_blueprints(signals, cluster, product_types, keyword_clusters, price_floor, price_ceiling)
    recommendation = _make_store_recommendation(
        signals,
        cluster,
        product_types,
        keyword_clusters,
        listing_blueprints,
        profit_score,
        evidence_depth,
    )

    return {
        "id": _slug(name),
        "name": name,
        "focus": focus,
        "anchorType": cluster.primary_type,
        "keywords": [
            {
                "keyword": signal.keyword,
                "opportunity": _score_or_none(signal.opportunity),
                "gap": _score_or_none(signal.gap),
                "demand": _score_or_none(signal.demand),
                "margin": _score_or_none(signal.margin),
                "product": _format_product(signal.products[0] if signal.products else product_types[0]),
                "estimatedRevenue": round(signal.revenue) if signal.revenue > 0 else None,
                "revenuePerListing": round(signal.revenue_per_listing, 2) if signal.revenue_per_listing > 0 else None,
                "avgPrice": round(signal.avg_price, 2) if signal.avg_price > 0 else None,
                "competitionEase": round(100 - signal.competition_quality) if signal.competition_quality > 0 else None,
                "marketEvidenceScore": round(signal.market_evidence_score) if signal.market_evidence_score > 0 else None,
                "profitabilityIndex": round(signal.profitability_index) if signal.profitability_index > 0 else None,
                "avgFavorites": round(signal.avg_favorites, 1) if signal.avg_favorites > 0 else None,
            }
            for signal in signals[:8]
        ],
        "productTypes": [_format_product(product) for product in product_types],
        "avgOpportunity": round(avg_opportunity),
        "avgGap": round(avg_gap) if avg_gap > 0 else None,
        "nicheScore": round(niche_score),
        "profitScore": round(profit_score) if profit_score is not None else None,
        "profitGrade": _profit_grade(profit_score) if profit_score is not None else None,
        "rawProfitScore": round(raw_profit_score) if has_profit_evidence else None,
        "cohesion": round(cohesion),
        "trendLift": round(min(10, trend_score / 10)),
        "demandScore": round(avg_demand) if avg_demand > 0 else None,
        "marginScore": round(gross_margin) if gross_margin > 0 else None,
        "competitionEase": round(competition_ease) if competition_ease > 0 else None,
        "buyerIntent": round(buyer_intent),
        "confidenceScore": round(confidence),
        "avgPrice": round(avg_price, 2) if avg_price > 0 else None,
        "priceRange": {"min": round(price_floor, 2), "max": round(price_ceiling, 2)} if price_floor > 0 and price_ceiling > 0 else None,
        "priceBasis": "observed" if has_observed_price_basis else None,
        "estimatedGrossMargin": round(gross_margin) if gross_margin > 0 else None,
        "estimatedMonthlyRevenue": round(revenue) if revenue_signals else None,
        "profitabilityEvidence": _make_profitability_evidence(
            signals,
            evidence_depth,
            observed_price_band,
            gross_margin,
            revenue,
            avg_revenue_per_listing,
            revenue_density,
            market_traction,
            seller_weakness if competition_ease > 0 or market_traction > 0 else 0.0,
        ),
        "scoreBreakdown": _score_breakdown(
            margin_signal if has_profit_evidence else 0,
            revenue_density,
            competition_ease,
            avg_gap,
            price_power,
            avg_demand,
            buyer_intent,
            market_traction,
            seller_weakness if competition_ease > 0 or market_traction > 0 else 0.0,
            evidence_depth,
            signals,
        ),
        "rationale": _make_rationale(signals, focus, product_types, profit_score, gross_margin),
        "evidence": _make_evidence(signals, cluster, product_types, revenue, competition_ease),
        "evidenceDepth": evidence_depth,
        "keywordClusters": keyword_clusters,
        "listingBlueprints": listing_blueprints,
        "storeRecommendation": recommendation,
        "feeModel": _fee_model(),
        "listingIdeas": [blueprint["title"] for blueprint in listing_blueprints[:4]] or _make_listing_ideas(cluster, product_types),
        "risks": _make_risks(signals, avg_gap, cohesion, product_types, gross_margin, confidence),
        "profitDrivers": _make_profit_drivers(gross_margin, revenue, competition_ease, buyer_intent, confidence),
        "validationChecklist": _make_validation_checklist(signals, product_types, price_floor, price_ceiling),
    }


def _choose_primary(signal: KeywordSignal) -> tuple[str, TaxonomyItem] | None:
    for type_name, matches in (
        ("audience", signal.audience),
        ("theme", signal.theme),
        ("style", signal.style),
        ("occasion", signal.occasion),
    ):
        if matches:
            return type_name, matches[0]
    keyword_item = _keyword_to_item(signal.keyword)
    if keyword_item:
        return "theme", keyword_item
    domain_item = _domain_to_item(signal.domain)
    return ("theme", domain_item) if domain_item else None


def _choose_secondary(signal: KeywordSignal, primary_id: str) -> tuple[str, TaxonomyItem] | None:
    for type_name, matches in (
        ("intent", signal.intent),
        ("style", signal.style),
        ("theme", signal.theme),
        ("occasion", signal.occasion),
        ("audience", signal.audience),
    ):
        match = next((item for item in matches if item.id != primary_id), None)
        if match:
            return type_name, match
    return None


def _match_taxonomy(text: str, taxonomy: tuple[TaxonomyItem, ...]) -> list[TaxonomyItem]:
    return [item for item in taxonomy if any(_contains_term(text, term) for term in item.terms)]


def _match_products(keyword: str, domain: str) -> list[str]:
    haystack = f"{keyword} {domain}".lower()
    products = [item.id for item in PRODUCT_TERMS if any(_contains_term(haystack, term) for term in item.terms)]
    if products:
        return list(dict.fromkeys(products))
    if re.search(r"decor|home|aesthetic|art|poster|print", haystack):
        return ["wall_art", "digital_download", "sticker"]
    if re.search(r"astrology|zodiac|moon sign|birth chart|celestial", haystack):
        return ["wall_art", "digital_download", "sticker", "mug"]
    if re.search(r"nurse|teacher|profession|career|job|biologist|electrician|dancer|musician", haystack):
        return ["mug", "apparel", "sticker", "digital_download"]
    if re.search(r"gift|gifts|anniversary|husband|girlfriend|boyfriend|friend|aunt|mom|dad", haystack):
        return ["mug", "wall_art", "digital_download", "apparel"]
    if re.search(r"funny|sarcastic|meme|snarky", haystack):
        return ["apparel", "mug", "sticker"]
    return ["digital_download"]


def _contains_term(text: str, term: str) -> bool:
    normalized = _normalize(term)
    if " " in normalized:
        return normalized in text
    return re.search(rf"(^|\s){re.escape(normalized)}(\s|$)", text) is not None


def _domain_to_item(domain: str) -> TaxonomyItem | None:
    normalized = _normalize(domain)
    if normalized in GENERIC_DOMAINS:
        return None
    cleaned = " ".join(part for part in normalized.split() if part not in STOP_WORDS)[:48].strip()
    if not cleaned:
        return None
    words = " ".join(cleaned.split()[:3])
    return TaxonomyItem(_slug(words), _title(words), (words,))


def _keyword_to_item(keyword: str) -> TaxonomyItem | None:
    product_terms = {term for product in PRODUCT_TERMS for term in product.terms}
    blocked = STOP_WORDS | BUYER_INTENT_TERMS | product_terms | {"aesthetic", "vibes", "lover"}
    parts = [part for part in _normalize(keyword).split() if part not in blocked and len(part) > 2]
    if len(parts) < 2:
        return None
    words = " ".join(parts[:3])
    return TaxonomyItem(_slug(words), _title(words), (words,))


def _rank_products(signals: list[KeywordSignal]) -> list[str]:
    scores: dict[str, float] = {}
    for signal in signals:
        for product in signal.products:
            economics = PRODUCT_ECONOMICS.get(product, PRODUCT_ECONOMICS["digital_download"])
            scores[product] = scores.get(product, 0) + _weighted_keyword_score(signal) + economics["ease"] * 0.08
    return [product for product, _ in sorted(scores.items(), key=lambda item: item[1], reverse=True)[:5]] or ["digital_download"]


def _calculate_cohesion(signals: list[KeywordSignal], cluster: ClusterSeed) -> float:
    covered = 0
    for signal in signals:
        dimensions = [
            *(item.id for item in signal.audience),
            *(item.id for item in signal.theme),
            *(item.id for item in signal.style),
            *(item.id for item in signal.occasion),
            *(item.id for item in signal.intent),
        ]
        if cluster.primary.id in dimensions or (cluster.secondary and cluster.secondary.id in dimensions):
            covered += 1
        elif cluster.primary.id.replace("_", " ") in _normalize(signal.domain):
            covered += 1
    return _clamp((covered / len(signals) * 78) + (min(1, len(signals) / 7) * 22))


def _calculate_trend_score(signals: list[KeywordSignal]) -> float:
    values = []
    for signal in signals:
        trajectory = signal.trajectory.lower()
        value = signal.trend
        if signal.breakout:
            value = max(value, 92)
        elif "rising" in trajectory or "up" in trajectory:
            value = max(value, 78)
        elif "stable" in trajectory:
            value = max(value, 55)
        values.append(value)
    return _average(values)


def _calculate_buyer_intent(signals: list[KeywordSignal]) -> float:
    scores = []
    for signal in signals:
        tokens = set(_normalize(signal.keyword).split())
        intent_bonus = 0
        if tokens & BUYER_INTENT_TERMS:
            intent_bonus += 25
        if signal.intent:
            intent_bonus += min(30, len(signal.intent) * 12)
        if signal.avg_price >= 18:
            intent_bonus += 12
        scores.append(_clamp(35 + intent_bonus + min(18, signal.revenue / 2500 if signal.revenue else 0)))
    return _average(scores)


def _calculate_confidence(signals: list[KeywordSignal]) -> float:
    data_points = 0
    for signal in signals:
        data_points += 1
        if signal.avg_price > 0:
            data_points += 1
        if signal.revenue > 0:
            data_points += 1
        if signal.gap > 0:
            data_points += 1
        if signal.listing_count > 0:
            data_points += 1
    return _clamp((min(len(signals), 8) / 8 * 42) + (min(data_points, 28) / 28 * 58))


def _calculate_competition_ease(signals: list[KeywordSignal]) -> float:
    values = []
    for signal in signals:
        components = []
        if signal.competition_quality > 0:
            components.append((100 - signal.competition_quality) * 0.72)
        if signal.listing_count > 0:
            components.append(_clamp(30 - math.log10(max(10, signal.listing_count)) * 5))
        if signal.gap > 0:
            components.append(signal.gap * 0.18)
        if components:
            values.append(_clamp(sum(components)))
    return _average(values)


def _price_range(signals: list[KeywordSignal], products: list[str], avg_price: float) -> tuple[float, float]:
    mins = [signal.price_min for signal in signals if signal.price_min > 0]
    maxes = [signal.price_max for signal in signals if signal.price_max > 0]
    if mins and maxes:
        return max(2.99, _average(mins)), max(_average(maxes), _average(mins) + 2)

    p25s = [signal.price_p25 for signal in signals if signal.price_p25 > 0]
    p75s = [signal.price_p75 for signal in signals if signal.price_p75 > 0]
    if p25s and p75s:
        floor = max(2.99, _average(p25s) * 0.92)
        ceiling = max(_average(p75s) * 1.08, floor + 2)
        return floor, ceiling

    economics = [PRODUCT_ECONOMICS.get(product, PRODUCT_ECONOMICS["digital_download"]) for product in products]
    floor = _average([item["floor"] for item in economics])
    ceiling = _average([item["ceiling"] for item in economics])
    if avg_price > 0:
        floor = max(floor, avg_price * 0.82)
        ceiling = max(ceiling, avg_price * 1.18)
    return floor, ceiling


def _estimated_gross_margin(products: list[str], price_floor: float, price_ceiling: float) -> float:
    target_price = (price_floor + price_ceiling) / 2
    economics = [PRODUCT_ECONOMICS.get(product, PRODUCT_ECONOMICS["digital_download"]) for product in products]
    product_cost = _average([item["cost"] for item in economics])
    fee_reserve = (
        ETSY_LISTING_FEE_USD
        + target_price * ETSY_TRANSACTION_FEE_RATE
        + target_price * ESTIMATED_US_PAYMENT_RATE
        + ESTIMATED_US_PAYMENT_FIXED_USD
    )
    gross_profit = max(0.0, target_price - product_cost - fee_reserve)
    if target_price <= 0:
        return 0
    return _clamp((gross_profit / target_price) * 100)


def _calculate_evidence_depth(signals: list[KeywordSignal], products: list[str]) -> dict[str, Any]:
    keyword_count = len(signals)
    sourced = [signal for signal in signals if signal.source_strength > 0]
    priced = [
        signal for signal in signals
        if signal.avg_price > 0
        or signal.price_p25 > 0
        or signal.price_p75 > 0
        or (signal.price_min > 0 and signal.price_max > 0)
    ]
    revenue = [signal for signal in signals if signal.revenue > 0]
    revenue_density = [signal for signal in signals if signal.revenue_per_listing > 0 or signal.listing_efficiency > 0]
    competition = [signal for signal in signals if signal.competition_quality > 0 or signal.listing_count > 0 or signal.gap > 0]
    trend = [signal for signal in signals if signal.trend > 0 or signal.trajectory or signal.breakout]
    traction = [signal for signal in signals if signal.avg_favorites > 0 or signal.max_favorites > 0 or signal.pct_bestsellers > 0]
    scored = [signal for signal in signals if signal.opportunity > 0 and signal.gap > 0 and signal.demand > 0]
    gap_scored = [signal for signal in signals if signal.gap > 0]
    missing = []
    if len(priced) < max(2, min(4, keyword_count // 2)):
        missing.append("price evidence")
    if not revenue:
        missing.append("monthly revenue evidence")
    if not revenue_density:
        missing.append("revenue density evidence")
    if len(competition) < max(2, min(4, keyword_count // 2)):
        missing.append("competition evidence")
    if not traction:
        missing.append("buyer traction evidence")
    if len(trend) < 2:
        missing.append("trend evidence")
    if len(sourced) < max(2, min(4, keyword_count // 2)):
        missing.append("keyword source evidence")

    score = _clamp(
        min(keyword_count, 10) / 10 * 24
        + min(len(sourced), 10) / 10 * 16
        + min(len(scored), 8) / 8 * 9
        + min(len(gap_scored), 8) / 8 * 5
        + min(len(priced), 6) / 6 * 17
        + min(len(revenue), 5) / 5 * 12
        + min(len(revenue_density), 5) / 5 * 10
        + min(len(competition), 8) / 8 * 11
        + min(len(traction), 5) / 5 * 8
        + min(len(trend), 6) / 6 * 4
        + min(len(products), 4) / 4 * 4
    )
    if score >= 78:
        level = "deep"
    elif score >= 62:
        level = "solid"
    elif score >= 45:
        level = "developing"
    else:
        level = "thin"

    return {
        "score": round(score),
        "level": level,
        "keywordSignals": keyword_count,
        "sourceBackedKeywords": len(sourced),
        "scoredKeywords": len(scored),
        "gapScoredKeywords": len(gap_scored),
        "pricedKeywords": len(priced),
        "revenueSignals": len(revenue),
        "revenueDensitySignals": len(revenue_density),
        "competitionSignals": len(competition),
        "buyerTractionSignals": len(traction),
        "trendSignals": len(trend),
        "productTypes": len(products),
        "missing": missing,
    }


def _observed_price_band(signals: list[KeywordSignal]) -> dict[str, float] | None:
    p25 = _average([signal.price_p25 for signal in signals if signal.price_p25 > 0])
    median = _average([signal.price_median for signal in signals if signal.price_median > 0])
    p75 = _average([signal.price_p75 for signal in signals if signal.price_p75 > 0])
    avg_price = _average([signal.avg_price for signal in signals if signal.avg_price > 0])
    if not any([p25, median, p75, avg_price]):
        return None
    return {
        "p25": round(p25, 2) if p25 > 0 else None,
        "median": round(median, 2) if median > 0 else None,
        "p75": round(p75, 2) if p75 > 0 else None,
        "avg": round(avg_price, 2) if avg_price > 0 else None,
    }


def _calculate_revenue_density(avg_revenue_per_listing: float, avg_listing_efficiency: float, revenue: float, signals: list[KeywordSignal]) -> float:
    components = []
    if avg_revenue_per_listing > 0:
        components.append(_clamp(math.log10(max(1.0, avg_revenue_per_listing)) / math.log10(350.0) * 100))
    if avg_listing_efficiency > 0:
        components.append(avg_listing_efficiency)
    if revenue > 0:
        components.append(_clamp(math.log10(max(1.0, revenue)) / math.log10(50_000.0) * 100))
    if not components:
        return 0.0
    keyword_depth = min(1.0, len([signal for signal in signals if signal.revenue > 0 or signal.revenue_per_listing > 0]) / 5)
    return _clamp(_average(components) * 0.86 + keyword_depth * 14)


def _calculate_market_traction(avg_favorites: float, pct_bestsellers: float) -> float:
    favorite_score = _clamp(math.log10(max(1.0, avg_favorites)) / math.log10(5000.0) * 100) if avg_favorites > 0 else 0.0
    bestseller_score = _clamp(pct_bestsellers * 1.4) if pct_bestsellers > 0 else 0.0
    return _clamp(favorite_score * 0.68 + bestseller_score * 0.32)


def _calculate_seller_weakness(pct_star_sellers: float, pct_bestsellers: float, competition_ease: float) -> float:
    maturity_pressure = _clamp((pct_star_sellers * 0.58) + (pct_bestsellers * 0.42))
    return _clamp(competition_ease * 0.62 + (100 - maturity_pressure) * 0.38)


def _make_profitability_evidence(
    signals: list[KeywordSignal],
    evidence_depth: dict[str, Any],
    observed_price_band: dict[str, float] | None,
    gross_margin: float,
    revenue: float,
    avg_revenue_per_listing: float,
    revenue_density: float,
    market_traction: float,
    seller_weakness: float,
) -> dict[str, Any]:
    listing_counts = [signal.listing_count for signal in signals if signal.listing_count > 0]
    return {
        "evidenceScore": evidence_depth["score"],
        "evidenceLevel": evidence_depth["level"],
        "observedPriceBand": observed_price_band,
        "priceBasis": "observed" if observed_price_band else "not_available",
        "estimatedGrossMargin": round(gross_margin) if gross_margin > 0 else None,
        "sampledMonthlyRevenue": round(revenue) if revenue > 0 else None,
        "revenuePerListing": round(avg_revenue_per_listing, 2) if avg_revenue_per_listing > 0 else None,
        "revenueDensityScore": round(revenue_density) if revenue_density > 0 else None,
        "marketTractionScore": round(market_traction) if market_traction > 0 else None,
        "sellerWeaknessScore": round(seller_weakness) if seller_weakness > 0 else None,
        "avgListingCount": round(_average(listing_counts)) if listing_counts else None,
        "avgFavorites": round(_average([signal.avg_favorites for signal in signals if signal.avg_favorites > 0]), 1) or None,
        "signalsWithDeepMarketData": len([signal for signal in signals if signal.market_evidence_score >= 70]),
        "missing": evidence_depth.get("missing", []),
    }


def _evidence_adjusted_profit_score(score: float, evidence_depth: dict[str, Any], has_price_basis: bool, has_revenue: bool) -> float:
    evidence_score = _number(evidence_depth.get("score"))
    cap = 100.0
    if not has_price_basis and not has_revenue:
        cap = min(cap, 64.0)
    elif not has_price_basis:
        cap = min(cap, 72.0)
    elif not has_revenue:
        cap = min(cap, 78.0)
    if evidence_score < 45:
        cap = min(cap, 62.0)
    elif evidence_score < 62:
        cap = min(cap, 78.0)
    return _clamp(min(score, cap) * 0.92 + evidence_score * 0.08)


def _make_keyword_clusters(
    signals: list[KeywordSignal],
    cluster: ClusterSeed,
    products: list[str],
) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}

    def add_group(group_id: str, label: str, cluster_type: str, signal: KeywordSignal) -> None:
        if group_id not in groups:
            groups[group_id] = {
                "id": group_id,
                "label": label,
                "clusterType": cluster_type,
                "signals": [],
            }
        groups[group_id]["signals"].append(signal)

    for signal in signals:
        for product in signal.products[:2]:
            add_group(f"product-{product}", f"{_format_focus(cluster)} {_format_product(product)}", "product", signal)
        for type_name, matches in (
            ("audience", signal.audience),
            ("theme", signal.theme),
            ("style", signal.style),
            ("occasion", signal.occasion),
            ("intent", signal.intent),
        ):
            for item in matches[:1]:
                if item.id in {cluster.primary.id, cluster.secondary.id if cluster.secondary else ""}:
                    add_group(f"{type_name}-{item.id}", item.label, type_name, signal)

    ranked = sorted(
        groups.values(),
        key=lambda item: (len(_unique_by_keyword(item["signals"])), _average([_weighted_keyword_score(signal) for signal in item["signals"]])),
        reverse=True,
    )
    result = []
    seen_labels: set[str] = set()
    for group in ranked:
        group_signals = _unique_by_keyword(group["signals"])
        group_signals.sort(key=_weighted_keyword_score, reverse=True)
        if len(group_signals) < 2 and len(result) >= 3:
            continue
        label_key = _normalize(group["label"])
        if label_key in seen_labels:
            continue
        seen_labels.add(label_key)
        primary_products = _rank_products(group_signals) or products
        avg_revenue_per_listing = _average([signal.revenue_per_listing for signal in group_signals if signal.revenue_per_listing > 0])
        revenue_density = _calculate_revenue_density(
            avg_revenue_per_listing,
            _average([signal.listing_efficiency for signal in group_signals if signal.listing_efficiency > 0]),
            sum(signal.revenue for signal in group_signals if signal.revenue > 0),
            group_signals,
        )
        market_evidence = _average([signal.market_evidence_score for signal in group_signals if signal.market_evidence_score > 0])
        avg_weighted_keyword = _average([_weighted_keyword_score(signal) for signal in group_signals])
        real_profitability_index = _average([signal.profitability_index for signal in group_signals if signal.profitability_index > 0])
        avg_profitability_index = real_profitability_index or 0.0
        profitability_score = _clamp(
            avg_profitability_index * 0.46
            + avg_weighted_keyword * 0.28
            + revenue_density * 0.16
            + market_evidence * 0.10
        )
        result.append({
            "id": group["id"],
            "label": group["label"],
            "clusterType": group["clusterType"],
            "keywords": [_keyword_payload(signal, primary_products[0]) for signal in group_signals[:6]],
            "primaryProducts": [_format_product(product) for product in primary_products[:3]],
            "avgOpportunity": _score_or_none(_average([signal.opportunity for signal in group_signals])),
            "avgGap": _score_or_none(_average([signal.gap for signal in group_signals])),
            "avgDemand": _score_or_none(_average([signal.demand for signal in group_signals])),
            "competitionEase": _score_or_none(_calculate_competition_ease(group_signals)),
            "buyerIntent": round(_calculate_buyer_intent(group_signals)),
            "revenueDensityScore": round(revenue_density) if revenue_density > 0 else None,
            "avgRevenuePerListing": round(avg_revenue_per_listing, 2) if avg_revenue_per_listing > 0 else None,
            "marketEvidenceScore": round(market_evidence) if market_evidence > 0 else None,
            "profitabilityScore": round(profitability_score) if real_profitability_index > 0 or revenue_density > 0 or market_evidence > 0 else None,
        })
        if len(result) >= 6:
            break

    return result


def _make_listing_blueprints(
    signals: list[KeywordSignal],
    cluster: ClusterSeed,
    products: list[str],
    keyword_clusters: list[dict[str, Any]],
    price_floor: float,
    price_ceiling: float,
) -> list[dict[str, Any]]:
    blueprints: list[dict[str, Any]] = []
    used_keywords: set[str] = set()
    cluster_lookup = {
        str(item["id"]): item
        for item in keyword_clusters
    }
    source_clusters = keyword_clusters[:4] or [{
        "id": "core",
        "label": _format_focus(cluster),
        "keywords": [_keyword_payload(signal, products[0]) for signal in signals[:6]],
        "primaryProducts": [_format_product(product) for product in products[:3]],
    }]

    for index, keyword_cluster in enumerate(source_clusters):
        cluster_keywords = keyword_cluster.get("keywords") or []
        primary = next(
            (item for item in cluster_keywords if _normalize(str(item.get("keyword") or "")) not in used_keywords),
            cluster_keywords[0] if cluster_keywords else None,
        )
        if not primary:
            continue
        primary_keyword = str(primary.get("keyword") or "").strip()
        if not primary_keyword:
            continue
        used_keywords.add(_normalize(primary_keyword))
        product = str((keyword_cluster.get("primaryProducts") or [_format_product(products[0])])[0])
        supporting = [
            str(item.get("keyword") or "")
            for item in cluster_keywords
            if str(item.get("keyword") or "") and str(item.get("keyword") or "") != primary_keyword
        ][:4]
        score = _clamp(
            (_number(primary.get("profitabilityIndex")) or _number(keyword_cluster.get("profitabilityScore"))) * 0.30
            + _number(primary.get("gap")) * 0.18
            + _number(primary.get("demand")) * 0.14
            + _number(primary.get("margin")) * 0.12
            + _number(keyword_cluster.get("revenueDensityScore")) * 0.12
            + _number(keyword_cluster.get("buyerIntent")) * 0.08
            + _number(keyword_cluster.get("competitionEase")) * 0.06
        )
        title = _listing_title(primary_keyword, product)
        blueprints.append({
            "id": _slug(f"{title}-{index}"),
            "title": title,
            "primaryKeyword": primary_keyword,
            "supportingKeywords": supporting,
            "sourceClusterId": keyword_cluster.get("id"),
            "sourceClusterLabel": keyword_cluster.get("label"),
            "productType": product,
            "buyerIntent": primary.get("buyerIntent") or keyword_cluster.get("buyerIntent"),
            "priceBand": {"min": round(price_floor, 2), "max": round(price_ceiling, 2)} if price_floor > 0 and price_ceiling > 0 else None,
            "tags": _make_tags_from_keywords([primary_keyword, *supporting]),
            "profitabilityScore": round(score) if _has_blueprint_profit_inputs(primary, keyword_cluster) else None,
            "profitInputs": {
                "opportunity": primary.get("opportunity"),
                "gap": primary.get("gap"),
                "demand": primary.get("demand"),
                "margin": primary.get("margin"),
                "avgPrice": primary.get("avgPrice"),
                "priceBand": {"min": round(price_floor, 2), "max": round(price_ceiling, 2)} if price_floor > 0 and price_ceiling > 0 else None,
                "estimatedRevenue": primary.get("estimatedRevenue"),
                "revenuePerListing": primary.get("revenuePerListing"),
                "marketEvidenceScore": primary.get("marketEvidenceScore"),
                "profitabilityIndex": primary.get("profitabilityIndex"),
            },
            "evidenceLevel": _blueprint_evidence_level(primary, cluster_lookup.get(str(keyword_cluster.get("id")))),
            "profitRationale": _blueprint_profit_rationale(primary_keyword, product, primary, keyword_cluster),
        })

    return sorted(blueprints, key=lambda item: item.get("profitabilityScore") or 0, reverse=True)[:6]


def _make_store_recommendation(
    signals: list[KeywordSignal],
    cluster: ClusterSeed,
    products: list[str],
    keyword_clusters: list[dict[str, Any]],
    listing_blueprints: list[dict[str, Any]],
    profit_score: float | None,
    evidence_depth: dict[str, Any],
) -> dict[str, Any]:
    top_keywords = [signal.keyword for signal in signals[:5]]
    collection_names = [str(item.get("label")) for item in keyword_clusters[:4] if item.get("label")]
    listing_titles = [str(item.get("title")) for item in listing_blueprints[:5] if item.get("title")]
    first_product = _format_product(products[0])
    focus = _format_focus(cluster)
    return {
        "positioning": f"Build a focused {focus} store around real keyword clusters, not a single product type.",
        "targetCustomer": _target_customer(cluster, first_product),
        "recommendedCollections": collection_names,
        "launchListingIdeas": listing_titles,
        "listingGenerationInputs": [
            {
                "title": item.get("title"),
                "primaryKeyword": item.get("primaryKeyword"),
                "supportingKeywords": item.get("supportingKeywords", []),
                "productType": item.get("productType"),
                "tags": item.get("tags", []),
                "profitInputs": item.get("profitInputs", {}),
            }
            for item in listing_blueprints[:8]
        ],
        "keywordStrategy": {
            "primaryKeywords": top_keywords[:3],
            "expansionKeywords": top_keywords[3:],
            "clusterCount": len(keyword_clusters),
            "listingBlueprintCount": len(listing_blueprints),
        },
        "profitPriority": _profit_priority(profit_score, evidence_depth),
        "profitOptimizationPlan": _profit_optimization_plan(evidence_depth, keyword_clusters, listing_blueprints),
        "validationPriorities": _validation_priorities(evidence_depth, keyword_clusters),
        "nextValidationStep": _next_validation_step(evidence_depth, top_keywords),
    }


def _keyword_payload(signal: KeywordSignal, default_product: str) -> dict[str, Any]:
    return {
        "keyword": signal.keyword,
        "opportunity": _score_or_none(signal.opportunity),
        "gap": _score_or_none(signal.gap),
        "demand": _score_or_none(signal.demand),
        "margin": _score_or_none(signal.margin),
        "product": _format_product(signal.products[0] if signal.products else default_product),
        "estimatedRevenue": round(signal.revenue) if signal.revenue > 0 else None,
        "revenuePerListing": round(signal.revenue_per_listing, 2) if signal.revenue_per_listing > 0 else None,
        "avgPrice": round(signal.avg_price, 2) if signal.avg_price > 0 else None,
        "competitionEase": round(100 - signal.competition_quality) if signal.competition_quality > 0 else None,
        "marketEvidenceScore": round(signal.market_evidence_score) if signal.market_evidence_score > 0 else None,
        "profitabilityIndex": round(signal.profitability_index) if signal.profitability_index > 0 else None,
        "avgFavorites": round(signal.avg_favorites, 1) if signal.avg_favorites > 0 else None,
        "buyerIntent": round(signal.buyer_intent_score) if signal.buyer_intent_score > 0 else None,
        "profitGap": round(signal.profit_gap_score) if signal.profit_gap_score > 0 else None,
        "priceRange": (
            {"min": round(signal.price_min, 2), "max": round(signal.price_max, 2)}
            if signal.price_min > 0 and signal.price_max > 0
            else None
        ),
    }


def _score_or_none(value: float) -> int | None:
    return round(value) if value > 0 else None


def _score_breakdown(
    margin: float,
    revenue_density: float,
    competition_ease: float,
    gap: float,
    price_power: float,
    demand: float,
    buyer_intent: float,
    market_traction: float,
    seller_weakness: float,
    evidence_depth: dict[str, Any],
    signals: list[KeywordSignal],
) -> dict[str, int]:
    values = {
        "margin": margin,
        "revenueDensity": revenue_density,
        "competitionEase": competition_ease,
        "gap": gap,
        "pricePower": price_power,
        "demand": demand,
        "buyerIntent": buyer_intent,
        "marketTraction": market_traction,
        "sellerWeakness": seller_weakness if competition_ease > 0 or market_traction > 0 else 0.0,
        "evidenceDepth": _number(evidence_depth.get("score")),
        "keywordSourceStrength": _average([signal.source_strength for signal in signals if signal.source_strength > 0]),
    }
    return {key: round(value) for key, value in values.items() if value > 0}


def _has_blueprint_profit_inputs(primary: dict[str, Any], keyword_cluster: dict[str, Any]) -> bool:
    return any(
        primary.get(field)
        for field in ("avgPrice", "priceRange", "estimatedRevenue", "revenuePerListing", "marketEvidenceScore", "profitabilityIndex")
    ) or any(
        keyword_cluster.get(field)
        for field in ("avgRevenuePerListing", "marketEvidenceScore", "revenueDensityScore", "profitabilityScore")
    )


def _fee_model() -> dict[str, Any]:
    return {
        "currency": "USD",
        "listingFee": ETSY_LISTING_FEE_USD,
        "transactionFeeRate": ETSY_TRANSACTION_FEE_RATE,
        "estimatedPaymentProcessingRate": ESTIMATED_US_PAYMENT_RATE,
        "estimatedPaymentProcessingFixed": ESTIMATED_US_PAYMENT_FIXED_USD,
        "offsiteAdsRateRange": {"min": OFFSITE_ADS_RATE_LOW, "max": OFFSITE_ADS_RATE_HIGH},
        "note": "Payment processing and offsite ads vary by country/account; gross margin uses a conservative US processing estimate and excludes ad spend.",
    }


def _calculate_price_power(price_floor: float, price_ceiling: float, avg_price: float, gross_margin: float) -> float:
    if price_floor <= 0 or price_ceiling <= 0:
        return 0.0
    spread = max(0.0, price_ceiling - price_floor)
    spread_score = _clamp(spread / max(price_ceiling, 1) * 140)
    premium_room = _clamp((price_ceiling - avg_price) / max(avg_price, 1) * 100 + 50) if avg_price > 0 else 0
    return _clamp(spread_score * 0.30 + premium_room * 0.30 + gross_margin * 0.40)


def _make_rationale(signals: list[KeywordSignal], focus: str, products: list[str], profit: float | None, margin: float) -> str:
    product_text = ", ".join(_format_product(product) for product in products[:3])
    margin_text = f"{round(margin)}% estimated gross margin" if margin > 0 else "no populated gross-margin data"
    profit_text = f"{round(profit)}/100 profit potential" if profit is not None else "profit score not available yet"
    return (
        f"{len(signals)} related keywords form a storeable {focus} niche with "
        f"{profit_text}, {margin_text}, "
        f"and a launchable mix across {product_text}."
    )


def _make_evidence(signals: list[KeywordSignal], cluster: ClusterSeed, products: list[str], revenue: float, competition_ease: float) -> list[str]:
    best = signals[0]
    product_text = ", ".join(_format_product(product) for product in products[:3])
    revenue_text = (
        f"Cached market data points to about ${round(revenue):,}/mo in sampled demand across the cluster."
        if revenue > 0
        else "Revenue data is not populated yet."
    )
    competition_text = (
        f"{round(competition_ease)}/100 competition ease from page-one evidence."
        if competition_ease > 0
        else "Competition ease is not populated yet because listing evidence is missing."
    )
    return [
        f"{best.keyword} is the strongest source-backed keyword in this cluster.",
        f"Keyword source strength comes from {', '.join(best.sources) or 'recorded keyword data'}.",
        revenue_text,
        f"{cluster.secondary.label + ' plus ' if cluster.secondary else ''}{cluster.primary.label} can support {product_text}. {competition_text}",
    ]


def _make_listing_ideas(cluster: ClusterSeed, products: list[str]) -> list[str]:
    focus = cluster.secondary.label + " " + cluster.primary.label if cluster.secondary else cluster.primary.label
    return [f"{focus} {_format_product(product)}" for product in products[:4]]


def _listing_title(primary_keyword: str, product: str) -> str:
    keyword = _title(_normalize(primary_keyword))
    normalized_product = _normalize(product)
    if normalized_product and normalized_product not in _normalize(keyword):
        return f"{keyword} {product}".strip()
    return keyword


def _make_tags_from_keywords(keywords: list[str]) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    for keyword in keywords:
        normalized = _normalize(keyword)
        if not normalized:
            continue
        candidates = [normalized]
        words = [word for word in normalized.split() if word not in STOP_WORDS]
        if len(words) >= 3:
            candidates.append(" ".join(words[:3]))
            candidates.append(" ".join(words[-3:]))
        if len(words) >= 2:
            candidates.append(" ".join(words[:2]))
            candidates.append(" ".join(words[-2:]))
        for candidate in candidates:
            tag = candidate[:20].strip()
            if len(tag) < 3 or tag in seen:
                continue
            seen.add(tag)
            tags.append(tag)
            if len(tags) >= 13:
                return tags
    return tags


def _blueprint_evidence_level(primary: dict[str, Any], keyword_cluster: dict[str, Any] | None) -> str:
    supporting_count = len(keyword_cluster.get("keywords", [])) if keyword_cluster else 0
    has_price = bool(primary.get("avgPrice") or primary.get("priceRange"))
    has_revenue = bool(primary.get("estimatedRevenue"))
    if supporting_count >= 5 and has_price and has_revenue:
        return "deep"
    if supporting_count >= 4 and (has_price or has_revenue):
        return "solid"
    if supporting_count >= 2:
        return "developing"
    return "thin"


def _blueprint_profit_rationale(
    primary_keyword: str,
    product: str,
    primary: dict[str, Any],
    keyword_cluster: dict[str, Any],
) -> str:
    parts = [
        f"Uses real keyword '{primary_keyword}' as the primary listing anchor.",
        f"{product} fits the cluster built from the current keyword source data.",
    ]
    if primary.get("avgPrice"):
        parts.append(f"Observed average price is ${_number(primary.get('avgPrice')):.2f}.")
    elif keyword_cluster.get("avgDemand"):
        parts.append("Price evidence is missing, so validate pricing before scaling.")
    if primary.get("estimatedRevenue"):
        parts.append(f"Sampled revenue signal is about ${round(_number(primary.get('estimatedRevenue'))):,}/mo.")
    return " ".join(parts)


def _target_customer(cluster: ClusterSeed, first_product: str) -> str:
    focus = _format_focus(cluster)
    if cluster.primary_type == "audience":
        return f"{cluster.primary.label} shopping for focused {first_product} and giftable products."
    if cluster.primary_type == "occasion":
        return f"Buyers preparing for {cluster.primary.label.lower()} who need searchable, giftable {first_product}."
    return f"Etsy buyers searching for {focus.lower()} ideas across cohesive, keyword-led products."


def _profit_priority(profit_score: float | None, evidence_depth: dict[str, Any]) -> str:
    missing = evidence_depth.get("missing") or []
    if profit_score is None:
        return "Profitability is not scored yet because price, revenue, and profitability evidence are not populated."
    if profit_score >= 78 and not missing:
        return "Scale only after the first collection proves conversion; this is a strong profit candidate."
    if "price evidence" in missing or "monthly revenue evidence" in missing:
        return "Collect price and revenue evidence before treating this as a high-confidence profit niche."
    if profit_score >= 70:
        return "Launch a small test collection and expand into the highest scoring cluster first."
    return "Use this as an exploration niche until stronger margin, revenue, and competition evidence is available."


def _profit_optimization_plan(
    evidence_depth: dict[str, Any],
    keyword_clusters: list[dict[str, Any]],
    listing_blueprints: list[dict[str, Any]],
) -> list[str]:
    plan = []
    missing = set(evidence_depth.get("missing") or [])
    if "price evidence" in missing:
        plan.append("Collect page-one price distributions before assigning premium or penetration pricing.")
    if "monthly revenue evidence" in missing or "revenue density evidence" in missing:
        plan.append("Estimate revenue per listing for the top cluster before scaling beyond the first collection.")
    if "buyer traction evidence" in missing:
        plan.append("Capture favorites, bestseller, and review velocity signals to confirm buyer pull.")
    if keyword_clusters:
        plan.append(f"Prioritize the '{keyword_clusters[0].get('label')}' cluster for the first listings.")
    if listing_blueprints:
        plan.append(f"Start listing generation with '{listing_blueprints[0].get('primaryKeyword')}' as the primary keyword anchor.")
    return plan or ["Evidence is strong enough to prototype the first collection and measure conversion."]


def _validation_priorities(evidence_depth: dict[str, Any], keyword_clusters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    missing = evidence_depth.get("missing") or []
    top_cluster = keyword_clusters[0] if keyword_clusters else {}
    keywords = [
        item.get("keyword")
        for item in (top_cluster.get("keywords") or [])[:3]
        if item.get("keyword")
    ]
    priorities = []
    for item in missing[:5]:
        if item == "price evidence":
            action = "Scrape or record p25/median/p75 prices for the top keywords."
        elif item == "monthly revenue evidence":
            action = "Estimate monthly revenue from reviews, sales velocity, and price."
        elif item == "revenue density evidence":
            action = "Calculate revenue per listing so broad markets do not outrank dense niches."
        elif item == "buyer traction evidence":
            action = "Capture favorites, bestseller flags, and review velocity from page-one listings."
        elif item == "competition evidence":
            action = "Score page-one title, tag, photo, star-seller, and bestseller strength."
        else:
            action = f"Collect {item}."
        priorities.append({
            "evidenceGap": item,
            "action": action,
            "keywords": keywords,
        })
    return priorities


def _next_validation_step(evidence_depth: dict[str, Any], keywords: list[str]) -> str:
    keyword_text = ", ".join(keywords[:3]) or "the top keywords"
    missing = evidence_depth.get("missing") or []
    if "price evidence" in missing:
        return f"Capture page-one prices for {keyword_text} and rerun the gap scanner."
    if "monthly revenue evidence" in missing:
        return f"Estimate monthly sales/revenue for page-one listings around {keyword_text}."
    if "revenue density evidence" in missing:
        return f"Calculate revenue per listing for {keyword_text} so scale decisions favor dense niches."
    if "buyer traction evidence" in missing:
        return f"Capture favorites, bestseller flags, and review velocity for {keyword_text}."
    if "competition evidence" in missing:
        return f"Score incumbent listing quality for {keyword_text} before building listings."
    return f"Prototype the first listings around {keyword_text} and track conversion signals."


def _make_profit_drivers(margin: float, revenue: float, competition_ease: float, buyer_intent: float, confidence: float) -> list[str]:
    margin_driver = (
        f"{round(margin)}% estimated gross margin after product cost and fee reserve."
        if margin > 0
        else "Gross-margin data is not populated yet."
    )
    revenue_driver = (
        f"${round(revenue):,}/mo sampled revenue signal across supporting keywords."
        if revenue > 0
        else "Revenue signal is not populated yet."
    )
    competition_driver = (
        f"{round(competition_ease)}/100 competition ease from page-one listing evidence."
        if competition_ease > 0
        else "Competition ease is not populated yet because page-one listing evidence is missing."
    )
    return [
        margin_driver,
        revenue_driver,
        competition_driver,
        f"{round(buyer_intent)}/100 keyword intent from gift, custom, and event terms in the real keyword set.",
        f"{round(confidence)}/100 confidence based on keyword count and available market data.",
    ]


def _make_risks(signals: list[KeywordSignal], avg_gap: float, cohesion: float, products: list[str], margin: float, confidence: float) -> list[str]:
    risks = []
    if len(signals) < 4:
        risks.append("Thin cluster: validate with more keyword scans before building a full store.")
    if avg_gap < 45:
        risks.append("Competition gap is modest, so the offer needs a sharper angle.")
    if cohesion < 65:
        risks.append("Theme is loose; keep the first collection tightly edited.")
    if len(products) < 2:
        risks.append("Product mix is narrow; test one adjacent product type before scaling.")
    if margin > 0 and margin < 38:
        risks.append("Estimated margin is tight; use digital or higher-price products first.")
    elif margin <= 0:
        risks.append("Margin evidence is missing; validate price and product cost before scaling.")
    if confidence < 55:
        risks.append("Confidence is limited because some revenue, price, or listing data is missing.")
    return risks or ["No major profitability warning from the current keyword set."]


def _make_validation_checklist(signals: list[KeywordSignal], products: list[str], price_floor: float, price_ceiling: float) -> list[str]:
    keywords = ", ".join(signal.keyword for signal in signals[:3])
    product = _format_product(products[0])
    price_text = (
        f"in the ${round(price_floor)}-${round(price_ceiling)} range"
        if price_floor > 0 and price_ceiling > 0
        else "after collecting price data"
    )
    return [
        f"Check page-one Etsy results for {keywords}.",
        f"Prototype 5 {product} listings {price_text}.",
        "Confirm top competitors have weak titles, tags, photos, or stale listings.",
        "Run a second scan after the first collection keywords are selected.",
    ]


def _profit_grade(score: float) -> str:
    if score >= 82:
        return "A"
    if score >= 72:
        return "B"
    if score >= 62:
        return "C"
    return "D"


def _format_focus(cluster: ClusterSeed) -> str:
    return f"{cluster.primary.label} / {cluster.secondary.label}" if cluster.secondary else cluster.primary.label


def _make_store_name(cluster: ClusterSeed, products: list[str]) -> str:
    primary = cluster.primary.label
    secondary = cluster.secondary.label if cluster.secondary else ""
    product_hint = "Print Studio"
    if cluster.secondary and cluster.secondary.id == "giftable":
        product_hint = "Gift Studio"
    elif "mug" in products:
        product_hint = "Gift Studio"
    elif "apparel" in products:
        product_hint = "Goods Co."
    elif "sticker" in products:
        product_hint = "Sticker Shop"
    elif "digital_download" in products or "planner" in products or "svg" in products:
        product_hint = "Supply Studio"
    return f"{secondary} {primary} {product_hint}".strip() if secondary else f"{primary} {product_hint}"


def _unique_by_keyword(signals: list[KeywordSignal]) -> list[KeywordSignal]:
    seen = set()
    unique = []
    for signal in signals:
        key = _normalize(signal.keyword)
        if key in seen:
            continue
        seen.add(key)
        unique.append(signal)
    return unique


def _weighted_keyword_score(signal: KeywordSignal) -> float:
    competition_component = (100 - signal.competition_quality) if signal.competition_quality > 0 else 0.0
    fallback_gap_component = signal.gap * 0.22 if signal.opportunity <= 0 and signal.demand <= 0 else 0.0
    metric_score = (
        signal.opportunity * 0.34
        + signal.demand * 0.18
        + signal.gap * 0.18
        + signal.margin * 0.14
        + competition_component * 0.10
        + signal.trend * 0.06
        + fallback_gap_component
        + (6 if signal.breakout else 0)
    )
    if metric_score <= 0:
        return signal.source_strength
    return metric_score + min(8.0, signal.source_strength * 0.08)


def _average(values: list[float]) -> float:
    usable = [float(value) for value in values if isinstance(value, (int, float)) and math.isfinite(float(value))]
    return sum(usable) / len(usable) if usable else 0.0


def _score(value: Any) -> float:
    return _clamp(_number(value))


def _number(value: Any) -> float:
    try:
        numeric = float(value)
        return numeric if math.isfinite(numeric) else 0.0
    except (TypeError, ValueError):
        return 0.0


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, value))


def _normalize(value: str) -> str:
    value = value.lower().replace("&", " and ")
    value = re.sub(r"[^a-z0-9\s']", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _format_product(product: str) -> str:
    return _title(product.replace("_", " "))


def _title(value: str) -> str:
    return re.sub(r"\b\w", lambda match: match.group(0).upper(), value)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _normalize(value)).strip("-") or "store-idea"
