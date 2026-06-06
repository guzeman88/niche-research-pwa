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
    volume_gap_score: float = 0.0      # supply/demand imbalance
    quality_gap_score: float = 0.0     # weak incumbent quality
    tag_gap_score: float = 0.0         # uncovered buyer search terms
    style_gap_score: float = 0.0       # style monopoly = opening for alternatives
    price_gap_score: float = 0.0       # underserved price range
    recency_gap_score: float = 0.0     # aging competition

    # ── Composite ─────────────────────────────────────────────────────────────
    composite_gap_score: float = 0.0

    # ── Entry point ───────────────────────────────────────────────────────────
    entry_angle: str = ""
    recommended_price_min: float = 0.0
    recommended_price_max: float = 0.0

    # ── Evidence ──────────────────────────────────────────────────────────────
    untagged_searches: list[str] = field(default_factory=list)
    dominant_competitor_tags: list[str] = field(default_factory=list)
    recommended_tags: list[str] = field(default_factory=list)
    listings_analyzed: int = 0
    avg_listing_age_months: float = 0.0

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

    # ── Step 2: Tag gap analysis ──────────────────────────────────────────────
    tag_gap_score = 50.0
    style_gap_score = 30.0
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
                tag_gap_score = tg.tag_gap_score
                style_gap_score = tg.style_gap_score
                untagged_searches = tg.untagged_searches
                recommended_tags = tg.recommended_tags
                # Top 10 most-used competitor tags
                dominant_tags = list(tg.tag_frequency.keys())[:10]
                _log(
                    f"[gap_analysis] tag_gap={tag_gap_score:.0f}  "
                    f"style_gap={style_gap_score:.0f}  "
                    f"untagged={len(untagged_searches)}"
                )
        except Exception as exc:
            _log(f"[gap_analysis] Tag gap analysis failed: {exc}")

    report.tag_gap_score = tag_gap_score
    report.style_gap_score = style_gap_score
    report.untagged_searches = untagged_searches
    report.dominant_competitor_tags = dominant_tags
    report.recommended_tags = recommended_tags

    # ── Step 3: Recency gap (average listing age) ─────────────────────────────
    ages = [d.listing_age_months for d in valid_details if d.listing_age_months > 0]
    avg_age = sum(ages) / len(ages) if ages else 18.0
    report.avg_listing_age_months = round(avg_age, 1)

    # Score: older average = more recency gap (stale competition)
    # 6 months avg  → score 10  (fresh competition, little recency gap)
    # 18 months avg → score 40  (typical)
    # 36 months avg → score 75  (stale competition, strong recency gap)
    # 60+ months    → score 95  (very stale)
    if avg_age <= 6:
        recency_gap = 10.0
    elif avg_age <= 12:
        recency_gap = 25.0
    elif avg_age <= 24:
        recency_gap = 45.0
    elif avg_age <= 36:
        recency_gap = 65.0
    elif avg_age <= 48:
        recency_gap = 80.0
    else:
        recency_gap = 92.0
    report.recency_gap_score = recency_gap

    # ── Step 4: Volume gap (supply/demand ratio) ──────────────────────────────
    ksd_list = niche_report_data.get("keyword_search_data", [])
    ksd = next((k for k in ksd_list if k.get("keyword") == keyword), None) or \
          (ksd_list[0] if ksd_list else {})

    listing_count = ksd.get("total_listing_count", 0) or 0
    trend_score = niche_report_data.get("trend_velocity_score", 50.0) or 50.0
    demand_score = niche_report_data.get("demand_score", 50.0) or 50.0
    avg_favorites = ksd.get("avg_favorites", 0) or 0

    # Volume gap = demand signal / log(supply)
    # High demand (trend, favorites) + lower listing count = high volume gap
    supply_pressure = math.log10(max(1, listing_count)) / math.log10(500_000) * 100
    demand_signal = (trend_score * 0.5 + demand_score * 0.3 + min(30, math.log10(max(1, avg_favorites)) / math.log10(5000) * 30) * 0.2)
    volume_gap = max(0.0, min(100.0, demand_signal - supply_pressure * 0.6 + 30))
    report.volume_gap_score = round(volume_gap, 1)

    # ── Step 5: Quality gap (weak incumbent listings) ─────────────────────────
    competition_quality = niche_report_data.get("avg_competition_quality") or \
                          ksd.get("competition_quality_score", 50.0) or 50.0
    # Quality gap = how low the bar is. Low quality incumbents = easy to rank above them.
    quality_gap = max(0.0, min(100.0, 100.0 - competition_quality))
    report.quality_gap_score = round(quality_gap, 1)

    # ── Step 6: Price gap (underserved price range) ───────────────────────────
    price_min = ksd.get("price_min", 0) or 0
    price_p25 = ksd.get("price_p25", 0) or 0
    price_p75 = ksd.get("price_p75", 0) or 0
    price_max = ksd.get("price_max", 0) or 0
    avg_price = ksd.get("avg_price_usd", 0) or 0

    # Price gap strategy: find range with least competition
    # If price_p25 is close to price_p75, the market is tightly clustered — easy to enter above or below
    price_gap = _score_price_gap(price_min, price_p25, price_p75, price_max, avg_price)
    report.price_gap_score = price_gap

    # Set recommended price range: slightly below the sweet spot p75 to undercut incumbents
    # Or above p75 if quality gap is high (low competition = can charge premium)
    if avg_price > 0:
        if quality_gap >= 50:
            # Weak incumbents — can charge premium
            report.recommended_price_min = round(price_p75 * 0.9, 2)
            report.recommended_price_max = round(min(price_max, price_p75 * 1.4), 2)
        else:
            # Strong incumbents — undercut to gain initial traction
            report.recommended_price_min = round(price_p25 * 0.85, 2)
            report.recommended_price_max = round(price_p75 * 0.95, 2)

    # ── Composite gap score ───────────────────────────────────────────────────
    # Weighted average of all 6 signals
    # Tag gap and volume gap are the most predictive → higher weights
    composite = (
        volume_gap   * 0.25 +
        quality_gap  * 0.15 +
        tag_gap_score * 0.25 +
        style_gap_score * 0.15 +
        price_gap    * 0.10 +
        recency_gap  * 0.10
    )
    report.composite_gap_score = round(min(100.0, max(0.0, composite)), 1)

    # ── Entry angle ───────────────────────────────────────────────────────────
    report.entry_angle = _build_entry_angle(report, keyword, avg_price)

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
            composite_gap=report.composite_gap_score,
            entry_angle=report.entry_angle,
            recommended_price_min=report.recommended_price_min,
            recommended_price_max=report.recommended_price_max,
            untagged_searches=untagged_searches,
            dominant_competitor_tags=dominant_tags,
            recommended_tags=recommended_tags,
            listings_analyzed=report.listings_analyzed,
            avg_listing_age_months=report.avg_listing_age_months,
        )
    except Exception as exc:
        _log(f"[gap_analysis] DB save failed: {exc}")

    # ── Save JSON report file ─────────────────────────────────────────────────
    try:
        report.save(store_slug)
    except Exception as exc:
        _log(f"[gap_analysis] File save failed: {exc}")

    _log(
        f"[gap_analysis] '{keyword}' done in {time.time()-t0:.1f}s  "
        f"composite={report.composite_gap_score:.0f}  "
        f"vol={report.volume_gap_score:.0f} qual={report.quality_gap_score:.0f} "
        f"tag={report.tag_gap_score:.0f} style={report.style_gap_score:.0f} "
        f"price={report.price_gap_score:.0f} recency={report.recency_gap_score:.0f}"
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


def _build_entry_angle(report: GapReport, keyword: str, avg_price: float) -> str:
    """Construct a one-paragraph entry angle based on which gaps are strongest."""
    scores = {
        "tag": report.tag_gap_score,
        "volume": report.volume_gap_score,
        "quality": report.quality_gap_score,
        "style": report.style_gap_score,
        "price": report.price_gap_score,
        "recency": report.recency_gap_score,
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

    if not parts:
        parts.append(f"Moderate opportunity in '{keyword}' — focus on long-tail variants.")

    return " ".join(parts)
