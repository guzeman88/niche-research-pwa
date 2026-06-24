"""Profit-ranked store idea generation from cached keyword intelligence."""
from __future__ import annotations

import math
import re
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
        if signal and (signal.opportunity > 0 or signal.gap > 0 or signal.demand > 0)
    ]
    signals.sort(key=_weighted_keyword_score, reverse=True)
    signals = signals[:320]
    if not signals:
        return []

    ideas = [
        idea for idea in (_to_store_idea(cluster) for cluster in _merge_small_clusters(_seed_clusters(signals)))
        if idea
    ]
    ideas.sort(key=lambda item: (item["profitScore"], item["nicheScore"]), reverse=True)
    return ideas[:limit]


def _to_signal(row: dict[str, Any]) -> KeywordSignal | None:
    keyword = str(row.get("keyword") or "").strip()
    if not keyword:
        return None

    normalized = _normalize(keyword)
    domain = str(row.get("domain") or "discovered").replace("_", " ")
    gap = _score(row.get("composite_gap_score") or row.get("gap_score"))
    return KeywordSignal(
        keyword=keyword,
        domain=domain,
        opportunity=_score(row.get("opportunity_score")),
        gap=gap,
        demand=_score(row.get("demand_score") or row.get("opportunity_score")),
        margin=_score(row.get("margin_score")),
        trend=_score(row.get("trend_score")),
        competition_quality=_score(row.get("competition_quality") or row.get("competition_score") or 50),
        avg_price=_number(row.get("avg_price_usd")),
        revenue=_number(row.get("monthly_revenue_usd")),
        listing_count=int(_number(row.get("listing_count"))),
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
    revenue = sum(signal.revenue for signal in signals if signal.revenue > 0)
    competition_ease = _calculate_competition_ease(signals)
    cohesion = _calculate_cohesion(signals, cluster)
    trend_score = _calculate_trend_score(signals)
    buyer_intent = _calculate_buyer_intent(signals)
    confidence = _calculate_confidence(signals)
    price_floor, price_ceiling = _price_range(signals, product_types, avg_price)
    gross_margin = _estimated_gross_margin(product_types, price_floor, price_ceiling)
    price_power = _calculate_price_power(price_floor, price_ceiling, avg_price, gross_margin)
    fulfillment_ease = _average([PRODUCT_ECONOMICS.get(product, PRODUCT_ECONOMICS["digital_download"])["ease"] for product in product_types])

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
    profit_score = _clamp(
        avg_demand * 0.20
        + gross_margin * 0.18
        + competition_ease * 0.17
        + avg_gap * 0.13
        + price_power * 0.10
        + buyer_intent * 0.08
        + cohesion * 0.06
        + trend_score * 0.04
        + fulfillment_ease * 0.02
        + confidence * 0.02
    )
    name = _make_store_name(cluster, product_types)

    return {
        "id": _slug(name),
        "name": name,
        "focus": focus,
        "anchorType": cluster.primary_type,
        "keywords": [
            {
                "keyword": signal.keyword,
                "opportunity": round(signal.opportunity),
                "gap": round(signal.gap),
                "demand": round(signal.demand),
                "margin": round(signal.margin),
                "product": _format_product(signal.products[0] if signal.products else product_types[0]),
                "estimatedRevenue": round(signal.revenue),
                "avgPrice": round(signal.avg_price, 2),
                "competitionEase": round(100 - signal.competition_quality),
            }
            for signal in signals[:8]
        ],
        "productTypes": [_format_product(product) for product in product_types],
        "avgOpportunity": round(avg_opportunity),
        "avgGap": round(avg_gap),
        "nicheScore": round(niche_score),
        "profitScore": round(profit_score),
        "profitGrade": _profit_grade(profit_score),
        "cohesion": round(cohesion),
        "trendLift": round(min(10, trend_score / 10)),
        "demandScore": round(avg_demand),
        "marginScore": round(gross_margin),
        "competitionEase": round(competition_ease),
        "buyerIntent": round(buyer_intent),
        "confidenceScore": round(confidence),
        "avgPrice": round(avg_price, 2),
        "priceRange": {"min": round(price_floor, 2), "max": round(price_ceiling, 2)},
        "estimatedGrossMargin": round(gross_margin),
        "estimatedMonthlyRevenue": round(revenue),
        "rationale": _make_rationale(signals, focus, product_types, profit_score, gross_margin),
        "evidence": _make_evidence(signals, cluster, product_types, revenue, competition_ease),
        "listingIdeas": _make_listing_ideas(cluster, product_types),
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
        ("intent", [item for item in signal.intent if item.id != "giftable"]),
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
    if re.search(r"decor|home|aesthetic|art|poster|print", domain):
        return ["wall_art", "digital_download"]
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
        value = signal.trend or 50
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
        quality_ease = 100 - signal.competition_quality
        listing_bonus = 0
        if signal.listing_count > 0:
            listing_bonus = _clamp(30 - math.log10(max(10, signal.listing_count)) * 5)
        values.append(_clamp(quality_ease * 0.72 + signal.gap * 0.18 + listing_bonus))
    return _average(values)


def _price_range(signals: list[KeywordSignal], products: list[str], avg_price: float) -> tuple[float, float]:
    mins = [signal.price_min for signal in signals if signal.price_min > 0]
    maxes = [signal.price_max for signal in signals if signal.price_max > 0]
    if mins and maxes:
        return max(2.99, _average(mins)), max(_average(maxes), _average(mins) + 2)

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
    fee_reserve = target_price * 0.12 + 0.45
    gross_profit = max(0.0, target_price - product_cost - fee_reserve)
    if target_price <= 0:
        return 0
    return _clamp((gross_profit / target_price) * 100)


def _calculate_price_power(price_floor: float, price_ceiling: float, avg_price: float, gross_margin: float) -> float:
    spread = max(0.0, price_ceiling - price_floor)
    spread_score = _clamp(spread / max(price_ceiling, 1) * 140)
    premium_room = _clamp((price_ceiling - avg_price) / max(avg_price, 1) * 100 + 50) if avg_price > 0 else 55
    return _clamp(spread_score * 0.30 + premium_room * 0.30 + gross_margin * 0.40)


def _make_rationale(signals: list[KeywordSignal], focus: str, products: list[str], profit: float, margin: float) -> str:
    product_text = ", ".join(_format_product(product) for product in products[:3])
    return (
        f"{len(signals)} related keywords form a storeable {focus} niche with "
        f"{round(profit)}/100 profit potential, {round(margin)}% estimated gross margin, "
        f"and a launchable mix across {product_text}."
    )


def _make_evidence(signals: list[KeywordSignal], cluster: ClusterSeed, products: list[str], revenue: float, competition_ease: float) -> list[str]:
    best = signals[0]
    strongest_gap = max(signals, key=lambda signal: signal.gap)
    product_text = ", ".join(_format_product(product) for product in products[:3])
    return [
        f"{best.keyword} is the strongest combined keyword at {round(_weighted_keyword_score(best))}/100.",
        f"{strongest_gap.keyword} has the clearest market opening with {round(strongest_gap.gap)} gap score.",
        f"Cached market data points to about ${round(revenue):,}/mo in sampled demand across the cluster.",
        f"{cluster.secondary.label + ' plus ' if cluster.secondary else ''}{cluster.primary.label} can support {product_text} with {round(competition_ease)}/100 competition ease.",
    ]


def _make_listing_ideas(cluster: ClusterSeed, products: list[str]) -> list[str]:
    focus = cluster.secondary.label + " " + cluster.primary.label if cluster.secondary else cluster.primary.label
    return [f"{focus} {_format_product(product)}" for product in products[:4]]


def _make_profit_drivers(margin: float, revenue: float, competition_ease: float, buyer_intent: float, confidence: float) -> list[str]:
    return [
        f"{round(margin)}% estimated gross margin after product cost and fee reserve.",
        f"${round(revenue):,}/mo sampled revenue signal across supporting keywords.",
        f"{round(competition_ease)}/100 competition ease from gap and incumbent quality signals.",
        f"{round(buyer_intent)}/100 buyer intent from gift, custom, event, and price cues.",
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
    if margin < 38:
        risks.append("Estimated margin is tight; use digital or higher-price products first.")
    if confidence < 55:
        risks.append("Confidence is limited because some revenue, price, or listing data is missing.")
    return risks or ["No major profitability warning from the current keyword set."]


def _make_validation_checklist(signals: list[KeywordSignal], products: list[str], price_floor: float, price_ceiling: float) -> list[str]:
    keywords = ", ".join(signal.keyword for signal in signals[:3])
    product = _format_product(products[0])
    return [
        f"Check page-one Etsy results for {keywords}.",
        f"Prototype 5 {product} listings in the ${round(price_floor)}-${round(price_ceiling)} range.",
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
    if "apparel" in products:
        product_hint = "Goods Co."
    elif "mug" in products:
        product_hint = "Gift Studio"
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
    return (
        signal.opportunity * 0.34
        + signal.demand * 0.18
        + signal.gap * 0.18
        + signal.margin * 0.14
        + (100 - signal.competition_quality) * 0.10
        + signal.trend * 0.06
        + (6 if signal.breakout else 0)
    )


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
