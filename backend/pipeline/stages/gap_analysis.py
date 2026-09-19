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
    ages = [
        d.listing_age_months
        for d in valid_details
        if d.listing_age_months is not None and d.listing_age_months > 0
    ]
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
