"""
Gap Analysis Stage — full 6-signal market gap detection.

Takes a keyword + the listing IDs found during niche research, then:
  1. Fetches individual listing pages (tags, exact dates, favorites)
  2. Runs tag gap analysis (buyer terms vs. seller tags)
  3. Scores all 6 gap types independently
  4. Produces a composite GapReport with a specific entry angle
  5. Persists to the gap_reports table in the keyword database

The 6 gap signals:
  volume_gap    — high search demand, relatively few listings (supply/demand imbalance)
  quality_gap   — top listings have low reviews/star-seller status (weak incumbents)
  tag_gap       — buyer autocomplete terms not used as tags by any top seller
  style_gap     — one visual style monopolizes results (opening for alternatives)
  price_gap     — underserved price range within the niche distribution
  recency_gap   — top listings are old (buyers want fresh designs, aging competition)

This stage is called automatically by the scheduler after every niche_research scan.
No user action required.
"""

from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from pipeline import keyword_database as kdb

log = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent.parent
WORKSPACE = ROOT / "workspace"

# Max listing pages to fetch per keyword (each takes ~1.5s + delay)
MAX_LISTING_PAGES = 12

# Min listings needed to produce a meaningful gap score
MIN_LISTINGS_FOR_ANALYSIS = 5


@dataclass
class GapReport:
    keyword: str
    analyzed_at: str

    # ── Individual gap scores (0-100; higher = more opportunity) ─────────────
    volume_gap_score: float | None = None
    quality_gap_score: float | None = None
    tag_gap_score: float | None = None
    style_gap_score: float | None = None
    price_gap_score: float | None = None
    recency_gap_score: float | None = None
    buyer_intent_score: float | None = None
    profit_gap_score: float | None = None

    # ── Composite ─────────────────────────────────────────────────────────────
    composite_gap_score: float | None = None

    # ── Entry point ───────────────────────────────────────────────────────────
    entry_angle: str = ""
    recommended_price_min: float | None = None
    recommended_price_max: float | None = None

    # ── Evidence ──────────────────────────────────────────────────────────────
    untagged_searches: list[str] = field(default_factory=list)
    dominant_competitor_tags: list[str] = field(default_factory=list)
    recommended_tags: list[str] = field(default_factory=list)
    listings_analyzed: int = 0
    avg_listing_age_months: float | None = None
    price_p25_usd: float | None = None
    price_median_usd: float | None = None
    price_p75_usd: float | None = None
    avg_favorites: float | None = None
    pct_high_favorites: float | None = None
    pct_star_sellers: float | None = None
    pct_bestsellers: float | None = None
    revenue_per_listing: float | None = None
    market_evidence_score: float | None = None

    def save(self, store_slug: str) -> Path:
        out_dir = WORKSPACE / store_slug / "_gap_reports"
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        kw_slug = self.keyword.replace(" ", "_").replace("/", "-")[:40]
        path = out_dir / f"gap_{kw_slug}_{ts}.json"
        path.write_text(json.dumps(asdict(self), indent=2, default=str), encoding="utf-8")
        return path


def run(
    keyword: str,
    listing_ids: list[str],
    autocomplete_terms: list[str],
    niche_report_data: dict,
    store_slug: str = "__global__",
    log_fn: Optional[Callable] = None,
) -> GapReport:
    """
    Full gap analysis for one keyword.

    Args:
        keyword: The keyword being analyzed.
        listing_ids: Listing IDs from the niche_research scrape (up to MAX_LISTING_PAGES).
        autocomplete_terms: Suggestions from Etsy autocomplete for this keyword.
        niche_report_data: The NicheReport as a dict (for scores already computed).
        store_slug: Workspace folder slug for saving the report.
        log_fn: Optional logging callback.

    Returns:
        GapReport with all 6 gap scores and entry angle.
    """
    _log = log_fn or (lambda msg: log.info(msg))
    _log(f"[gap_analysis] Analyzing '{keyword}' ({len(listing_ids)} listing IDs)")
    t0 = time.time()

    report = GapReport(
        keyword=keyword,
        analyzed_at=datetime.now(timezone.utc).isoformat(),
    )

    # ── Step 1: Fetch listing pages for tag/date data ─────────────────────────
    listing_details = []
    if listing_ids:
        try:
            from adapters.research.etsy_listing_scraper import EtsyListingScraper
            scraper = EtsyListingScraper()
            ids_to_fetch = listing_ids[:MAX_LISTING_PAGES]
            _log(f"[gap_analysis] Fetching {len(ids_to_fetch)} listing pages for tags/dates")
            listing_details = scraper.fetch_listings_bulk(ids_to_fetch, max_listings=MAX_LISTING_PAGES)
            scraper.close()
            successes = [d for d in listing_details if not d.error]
            _log(f"[gap_analysis] Got {len(successes)}/{len(ids_to_fetch)} listing pages OK")
        except Exception as exc:
            _log(f"[gap_analysis] Listing fetch failed: {exc}")

    valid_details = [d for d in listing_details if not d.error]
    report.listings_analyzed = len(valid_details)

    # ── Step 2: Tag observations ──────────────────────────────────────────────
    # Do not score missing tag data. A score can only be produced by a separately
    # versioned model after its inputs and outcomes have been validated.
    tag_gap_score: float | None = None
    style_gap_score: float | None = None
    untagged_searches: list[str] = []
    dominant_tags: list[str] = []
    recommended_tags: list[str] = []

    if valid_details and autocomplete_terms:
        try:
            from adapters.research.tag_gap_analyzer import analyze_tags
            tag_sets = [d.tags for d in valid_details if d.tags]
            if tag_sets:
                tg = analyze_tags(
                    keyword=keyword,
                    autocomplete_terms=autocomplete_terms,
                    listing_tag_sets=tag_sets,
                )
                untagged_searches = tg.untagged_searches
                recommended_tags = tg.recommended_tags
                # Top 10 most-used competitor tags
                dominant_tags = list(tg.tag_frequency.keys())[:10]
                _log(f"[gap_analysis] observed {len(untagged_searches)} uncovered search terms")
        except Exception as exc:
            _log(f"[gap_analysis] Tag gap analysis failed: {exc}")

    report.tag_gap_score = tag_gap_score
    report.style_gap_score = style_gap_score
    report.untagged_searches = untagged_searches
    report.dominant_competitor_tags = dominant_tags
    report.recommended_tags = recommended_tags

    # ── Step 3: Recency gap (average listing age) ─────────────────────────────
    ages = [d.listing_age_months for d in valid_details if d.listing_age_months > 0]
    report.avg_listing_age_months = round(sum(ages) / len(ages), 1) if ages else None

    # ── Step 4: Volume gap (supply/demand ratio) ──────────────────────────────
    ksd_list = niche_report_data.get("keyword_search_data", [])
    ksd = next((k for k in ksd_list if k.get("keyword") == keyword), None) or {}

    def observed_number(name: str) -> float | None:
        value = ksd.get(name)
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if math.isfinite(parsed) else None

    listing_count = observed_number("total_listing_count")
    avg_favorites = observed_number("avg_favorites")
    report.avg_favorites = round(avg_favorites, 1) if avg_favorites is not None else None
    for source_name, target_name in (
        ("pct_high_favorites", "pct_high_favorites"),
        ("pct_star_sellers", "pct_star_sellers"),
        ("pct_bestsellers", "pct_bestsellers"),
    ):
        value = observed_number(source_name)
        setattr(report, target_name, round(value, 1) if value is not None else None)

    # ── Step 6: Price gap (underserved price range) ───────────────────────────
    price_p25 = observed_number("price_p25")
    price_median = observed_number("price_median")
    price_p75 = observed_number("price_p75")
    report.price_p25_usd = round(price_p25, 2) if price_p25 is not None else None
    report.price_median_usd = round(price_median, 2) if price_median is not None else None
    report.price_p75_usd = round(price_p75, 2) if price_p75 is not None else None

    # These remain TBD until a documented, versioned model is calibrated against
    # observed sales and product costs. Raw listing observations are still saved.
    report.composite_gap_score = None
    report.entry_angle = ""

    # ── Persist to database ───────────────────────────────────────────────────
    try:
        kdb.save_gap_report(
            keyword=keyword,
            volume_gap=report.volume_gap_score,
            quality_gap=report.quality_gap_score,
            tag_gap=report.tag_gap_score,
            style_gap=report.style_gap_score,
            price_gap=report.price_gap_score,
            recency_gap=report.recency_gap_score,
            buyer_intent=report.buyer_intent_score,
            profit_gap=report.profit_gap_score,
            composite_gap=report.composite_gap_score,
            entry_angle=report.entry_angle,
            recommended_price_min=report.recommended_price_min,
            recommended_price_max=report.recommended_price_max,
            untagged_searches=untagged_searches,
            dominant_competitor_tags=dominant_tags,
            recommended_tags=recommended_tags,
            listings_analyzed=report.listings_analyzed,
            avg_listing_age_months=report.avg_listing_age_months,
            price_p25_usd=report.price_p25_usd,
            price_median_usd=report.price_median_usd,
            price_p75_usd=report.price_p75_usd,
            avg_favorites=report.avg_favorites,
            pct_high_favorites=report.pct_high_favorites,
            pct_star_sellers=report.pct_star_sellers,
            pct_bestsellers=report.pct_bestsellers,
            revenue_per_listing=report.revenue_per_listing,
            market_evidence_score=report.market_evidence_score,
        )
    except Exception as exc:
        _log(f"[gap_analysis] DB save failed: {exc}")

    # ── Save JSON report file ─────────────────────────────────────────────────
    try:
        report.save(store_slug)
    except Exception as exc:
        _log(f"[gap_analysis] File save failed: {exc}")

    _log(
        f"[gap_analysis] '{keyword}' done in {time.time()-t0:.1f}s; "
        f"listings={report.listings_analyzed}; score=TBD pending validated model"
    )
    return report


# ── Scoring helpers ───────────────────────────────────────────────────────────

def _score_price_gap(
    price_min: float,
    price_p25: float,
    price_p75: float,
    price_max: float,
    avg_price: float,
) -> float:
    """
    Score how exploitable the price distribution gap is (0-100).

    A tightly clustered market (all sellers at same price) has two openings:
      1. Below p25: undercut for volume
      2. Above p75: premium positioning

    A wide spread means less cohesion and more ways to differentiate.
    """
    if avg_price <= 0:
        return 30.0  # unknown, neutral

    spread = price_p75 - price_p25
    if spread <= 0:
        return 20.0

    # Normalized spread relative to average price
    relative_spread = spread / avg_price

    # Tight cluster (all competitors at same price) = easy to differentiate by price
    if relative_spread < 0.2:
        return 80.0   # very tight cluster — obvious above/below angle
    elif relative_spread < 0.4:
        return 60.0
    elif relative_spread < 0.7:
        return 40.0
    elif relative_spread < 1.2:
        return 25.0
    else:
        return 15.0   # very wide spread — price is not a differentiator


def _score_profit_gap(
    avg_price: float,
    margin_score: float,
    monthly_revenue: float,
    listing_count: int,
    demand_score: float,
) -> float:
    """Score whether the gap can plausibly support profitable listings."""
    price_band = 30.0
    if 10 <= avg_price <= 45:
        price_band = 82.0
    elif 6 <= avg_price < 10 or 45 < avg_price <= 70:
        price_band = 62.0
    elif avg_price > 70:
        price_band = 45.0

    revenue_density = 0.0
    if monthly_revenue > 0 and listing_count > 0:
        revenue_per_listing = monthly_revenue / listing_count
        revenue_density = min(100.0, math.log10(max(1.0, revenue_per_listing)) / math.log10(250.0) * 100)

    score = (
        (margin_score or 0) * 0.34
        + price_band * 0.20
        + revenue_density * 0.28
        + (demand_score or 0) * 0.18
    )
    return round(max(0.0, min(100.0, score)), 1)


def _score_market_evidence(
    listings_analyzed: int,
    listing_count: int,
    avg_price: float,
    monthly_revenue: float,
    competition_quality: float,
    avg_favorites: float,
    price_p25: float,
    price_p75: float,
) -> float:
    score = (
        min(listings_analyzed, MAX_LISTING_PAGES) / MAX_LISTING_PAGES * 22
        + (14 if listing_count > 0 else 0)
        + (18 if avg_price > 0 else 0)
        + (16 if monthly_revenue > 0 else 0)
        + (12 if competition_quality > 0 else 0)
        + (10 if avg_favorites > 0 else 0)
        + (8 if price_p25 > 0 and price_p75 > 0 else 0)
    )
    return round(max(0.0, min(100.0, score)), 1)


def _build_entry_angle(report: GapReport, keyword: str, avg_price: float) -> str:
    """Construct a one-paragraph entry angle based on which gaps are strongest."""
    scores = {
        "tag": report.tag_gap_score,
        "volume": report.volume_gap_score,
        "quality": report.quality_gap_score,
        "style": report.style_gap_score,
        "price": report.price_gap_score,
        "recency": report.recency_gap_score,
        "intent": report.buyer_intent_score,
        "profit": report.profit_gap_score,
    }
    # Find the top 2 signals
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top1, top2 = ranked[0][0], ranked[1][0]

    parts = []

    if top1 == "tag" or top2 == "tag":
        if report.untagged_searches:
            parts.append(
                f"Tag opportunity: buyers search '{report.untagged_searches[0]}' "
                f"but no top seller uses it as a tag — immediate ranking window."
            )
        else:
            parts.append(f"Tag gap: top sellers are under-tagging for buyer search variations.")

    if top1 == "volume" or top2 == "volume":
        parts.append(
            f"Volume gap: strong buyer demand relative to listing supply — "
            f"new listings can gain visibility faster than in saturated niches."
        )

    if top1 == "quality" or top2 == "quality":
        parts.append(
            f"Quality gap: incumbent listings have low reviews and few star-sellers — "
            f"a well-photographed listing with strong copy will rank above most competitors."
        )

    if top1 == "recency" or top2 == "recency":
        parts.append(
            f"Recency gap: top listings average {report.avg_listing_age_months:.0f} months old — "
            f"fresh designs with current trends will outperform aging stock photos."
        )

    if top1 == "style" or top2 == "style":
        if report.dominant_competitor_tags:
            dominant = report.dominant_competitor_tags[0]
            parts.append(
                f"Style gap: '{dominant}' style dominates — "
                f"an alternative aesthetic serves the segment of buyers who scroll past the current results."
            )

    if top1 == "price" or top2 == "price":
        if report.recommended_price_min > 0:
            parts.append(
                f"Price gap: most competitors cluster together — "
                f"enter at ${report.recommended_price_min:.0f}–${report.recommended_price_max:.0f} "
                f"to stand out in the price filter."
            )

    if top1 == "intent" or top2 == "intent":
        parts.append(
            f"Buyer intent gap: '{keyword}' reads like a purchase-ready Etsy query, "
            f"so winning the first-page angle matters more than broad traffic."
        )

    if top1 == "profit" or top2 == "profit":
        parts.append(
            f"Profit gap: demand, margin, and revenue density line up well enough "
            f"to validate a focused collection instead of a single test listing."
        )

    if not parts:
        parts.append(f"Moderate opportunity in '{keyword}' — focus on long-tail variants.")

    return " ".join(parts)
