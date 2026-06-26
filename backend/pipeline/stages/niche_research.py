"""
Stage 0 — Niche Research
Multi-source Etsy niche intelligence pipeline:

  1. Etsy Search Scraper  — top-20 listing data: real prices, review counts,
                            Star Seller %, Bestseller %, competition quality score,
                            revenue estimates (reviews × 20 heuristic)
  2. Etsy Autocomplete    — keyword discovery (no key)
  3. Google Trends        — 90-day trend direction + 5-year seasonality
  4. Reddit               — community sentiment (REDDIT_CLIENT_* gated)
  5. eRank / Marmalead    — real Etsy search volumes (API key gated)
  6. Pinterest Trends     — visual trend signals (key gated)
  7. LLM synthesis        — clusters, underserved angles, pricing strategy

Usage:
    from pipeline.stages.niche_research import run
    report = run(seed_keywords=["cottagecore art"], store_slug="my-store")
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from adapters.base.research import NicheSignal
from adapters.registry import get_llm_with_fallback
from pipeline.store_config import StoreConfig

log = logging.getLogger(__name__)

ROOT      = Path(__file__).parent.parent.parent
WORKSPACE = ROOT / "workspace"


# ── Data models ───────────────────────────────────────────────────────────────

@dataclass
class KeywordSearchData:
    """Real Etsy listing data scraped for a single keyword."""
    keyword: str
    total_listing_count: int
    avg_price_usd: float
    price_min: float
    price_p25: float
    price_median: float
    price_p75: float
    price_max: float
    price_sweet_spot: str           # "$12–$28 (middle 50%)"
    avg_review_count: float
    pct_star_sellers: float
    pct_bestsellers: float
    competition_quality_score: float  # 0-100
    estimated_market_monthly_revenue_usd: float
    sampled_listing_count: int = 0
    top_listing_titles: list[str] = field(default_factory=list)
    avg_favorites: float = 0.0          # avg favorites across sampled listings
    max_favorites: int = 0              # peak single-listing favorites
    pct_high_favorites: float = 0.0     # % listings with ≥100 favorites

@dataclass
class SeasonalityPoint:
    month: int          # 1-12
    relative_interest: float  # 0-100 (Google Trends scale)


@dataclass
class NicheReport:
    store_slug: str
    generated_at: str
    seed_keywords: list[str]

    # ── Raw signals from all adapters ─────────────────────────────────────────
    keyword_signals: list[dict]     # NicheSignal dicts

    # ── Scraped Etsy listing data (the real meat) ──────────────────────────────
    keyword_search_data: list[dict] = field(default_factory=list)  # KeywordSearchData dicts

    # ── Aggregate scores (0–100) ───────────────────────────────────────────────
    demand_score: float = 0.0
    competition_score: float = 0.0   # 100 = easy, 0 = saturated
    margin_score: float = 0.0
    trend_velocity_score: float = 0.0
    opportunity_score: float = 0.0   # weighted composite

    # ── Market-level metrics ───────────────────────────────────────────────────
    avg_price_usd: float = 0.0
    price_sweet_spot: str = ""
    estimated_market_monthly_revenue_usd: float = 0.0
    avg_competition_quality: float = 0.0  # avg of per-keyword quality scores

    # ── Seasonality ───────────────────────────────────────────────────────────
    seasonality: list[dict] = field(default_factory=list)  # SeasonalityPoint dicts
    peak_months: list[int] = field(default_factory=list)   # e.g. [11, 12] for holiday

    # ── LLM synthesis ─────────────────────────────────────────────────────────
    keyword_clusters: list[dict] = field(default_factory=list)
    underserved_angles: list[str] = field(default_factory=list)
    winning_styles: list[str] = field(default_factory=list)
    recommended_product_types: list[str] = field(default_factory=list)
    competitor_gaps: list[str] = field(default_factory=list)
    pricing_insights: str = ""
    entry_strategy: str = ""         # concrete first-3-listings recommendation

    # ── Meta ──────────────────────────────────────────────────────────────────
    sources_used: list[str] = field(default_factory=list)
    report_id: str = ""

    def save(self) -> Path:
        out_dir = WORKSPACE / self.store_slug / "_niche_research"
        out_dir.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = out_dir / f"niche_report_{date_str}.json"
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        return path


# ── Main entry point ──────────────────────────────────────────────────────────

def run(
    seed_keywords: list[str],
    store_slug: str,
    store_config: StoreConfig | None = None,
    log_fn: Callable[[str], None] | None = None,
    adapter_names: list[str] | None = None,
    skip_scraper: bool = False,
) -> NicheReport:
    """
    Full niche research pipeline.
    skip_scraper=True skips the Etsy HTML scraper (useful for fast testing).
    """
    _log = log_fn or (lambda msg: log.info(msg))
    _log(f"[niche_research] Starting research for: {seed_keywords}")
    t0 = time.time()

    # ── Step 1: Etsy search scraper (real listing data) ───────────────────────
    keyword_search_data: list[KeywordSearchData] = []
    if not skip_scraper:
        keyword_search_data = _run_scraper(seed_keywords, _log)

    # ── Step 2: Signal adapters (autocomplete, trends, Reddit, eRank…) ────────
    adapters = _build_adapters(store_config, adapter_names, _log)
    all_signals: list[NicheSignal] = []
    sources_used: list[str] = []

    for adapter in adapters:
        if not adapter.is_configured():
            _log(f"[niche_research] Skipping {adapter.name} - not configured")
            continue
        _log(f"[niche_research] {adapter.name}...")
        try:
            sigs = adapter.bulk_search(seed_keywords)
            all_signals.extend(sigs)
            if sigs:
                sources_used.append(adapter.name)
            _log(f"[niche_research] {adapter.name}: {len(sigs)} signals")
        except Exception as exc:
            _log(f"[niche_research] {adapter.name} error: {exc}")

    if keyword_search_data:
        sources_used.append("etsy_search_scraper")

    # ── Step 3: Seasonality ───────────────────────────────────────────────────
    seasonality, peak_months = _get_seasonality(seed_keywords[:2], _log)

    # ── Step 4: Aggregate scores ──────────────────────────────────────────────
    demand, competition, margin, trend = _aggregate_scores(
        all_signals, keyword_search_data
    )
    opportunity = _opportunity_score(demand, competition, margin, trend, keyword_search_data)

    _log(
        f"[niche_research] demand:{demand:.0f} comp:{competition:.0f} "
        f"margin:{margin:.0f} trend:{trend:.0f} -> opportunity:{opportunity:.0f}"
    )

    # ── Step 5: Market-level metrics from scraper ─────────────────────────────
    avg_price = 0.0
    price_sweet = ""
    market_revenue = 0.0
    avg_comp_quality = 0.0
    if keyword_search_data:
        avg_price = sum(k.avg_price_usd for k in keyword_search_data if k.avg_price_usd) / max(
            sum(1 for k in keyword_search_data if k.avg_price_usd), 1
        )
        # Use the keyword with most data for sweet spot
        best = max(keyword_search_data, key=lambda k: k.total_listing_count, default=None)
        price_sweet = best.price_sweet_spot if best else ""
        market_revenue = sum(k.estimated_market_monthly_revenue_usd for k in keyword_search_data)
        avg_comp_quality = sum(k.competition_quality_score for k in keyword_search_data) / len(keyword_search_data)

    # ── Step 6: LLM synthesis ─────────────────────────────────────────────────
    synthesis = _llm_synthesis(
        seed_keywords, all_signals, keyword_search_data,
        seasonality, store_config, _log
    )

    report = NicheReport(
        store_slug=store_slug,
        generated_at=datetime.now(timezone.utc).isoformat(),
        seed_keywords=seed_keywords,
        keyword_signals=[_signal_to_dict(s) for s in all_signals],
        keyword_search_data=[asdict(k) for k in keyword_search_data],
        demand_score=demand,
        competition_score=competition,
        margin_score=margin,
        trend_velocity_score=trend,
        opportunity_score=opportunity,
        avg_price_usd=round(avg_price, 2),
        price_sweet_spot=price_sweet,
        estimated_market_monthly_revenue_usd=round(market_revenue, 2),
        avg_competition_quality=round(avg_comp_quality, 1),
        seasonality=[asdict(s) for s in seasonality],
        peak_months=peak_months,
        keyword_clusters=synthesis.get("keyword_clusters", []),
        underserved_angles=synthesis.get("underserved_angles", []),
        winning_styles=synthesis.get("winning_styles", []),
        recommended_product_types=synthesis.get("recommended_product_types", []),
        competitor_gaps=synthesis.get("competitor_gaps", []),
        pricing_insights=synthesis.get("pricing_insights", ""),
        entry_strategy=synthesis.get("entry_strategy", ""),
        sources_used=sources_used,
        report_id=f"rpt_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
    )

    path = report.save()
    _log(f"[niche_research] Done in {time.time()-t0:.1f}s - saved {path.name}")
    return report


# ── Etsy scraper step ─────────────────────────────────────────────────────────

def _run_scraper(
    keywords: list[str],
    log_fn: Callable,
) -> list[KeywordSearchData]:
    from adapters.research.etsy_search_scraper import EtsySearchScraper
    scraper = EtsySearchScraper()
    results: list[KeywordSearchData] = []
    # Scrape each seed keyword + top expanded keywords (max 8 total to stay polite)
    # search_paged fetches up to 3 pages (~60 listings) for a representative sample
    targets = keywords[:4]
    log_fn(f"[niche_research] Scraping Etsy listings (3 pages each) for: {targets}")
    for kw in targets:
        try:
            sr = scraper.search_paged(kw, max_pages=3, max_listings=60)
            if sr.error:
                log_fn(f"[niche_research] scraper '{kw}': {sr.error}")
                continue
            pd = sr.price_distribution
            ksd = KeywordSearchData(
                keyword=kw,
                total_listing_count=sr.total_listing_count,
                avg_price_usd=pd.mean,
                price_min=pd.min,
                price_p25=pd.p25,
                price_median=pd.median,
                price_p75=pd.p75,
                price_max=pd.max,
                price_sweet_spot=pd.sweet_spot,
                avg_review_count=sr.avg_review_count,
                pct_star_sellers=sr.pct_star_sellers,
                pct_bestsellers=sr.pct_bestsellers,
                competition_quality_score=sr.competition_quality_score,
                estimated_market_monthly_revenue_usd=sr.estimated_total_monthly_revenue_usd,
                sampled_listing_count=len(sr.listings),
                top_listing_titles=[l.title for l in sr.listings[:5] if l.title],
                avg_favorites=sr.avg_favorites,
                max_favorites=sr.max_favorites,
                pct_high_favorites=sr.pct_high_favorites,
            )
            results.append(ksd)
            log_fn(
                f"[niche_research] '{kw}': {sr.total_listing_count:,} listings  "
                f"{len(sr.listings)} sampled  avg ${pd.mean:.2f}  sweet spot {pd.sweet_spot}  "
                f"avg favs {sr.avg_favorites:.0f}  "
                f"comp quality {sr.competition_quality_score:.0f}/100  "
                f"est. market revenue ${sr.estimated_total_monthly_revenue_usd:,.0f}/mo"
            )
        except Exception as exc:
            log_fn(f"[niche_research] scraper error '{kw}': {exc}")
    return results


# ── Seasonality ───────────────────────────────────────────────────────────────

def _get_seasonality(
    keywords: list[str],
    log_fn: Callable,
) -> tuple[list[SeasonalityPoint], list[int]]:
    """Pull 5-year Google Trends data and extract monthly seasonality profile."""
    if not keywords:
        return [], []
    import random, time as _time
    max_retries = 3
    for attempt in range(max_retries):
        try:
            from pytrends.request import TrendReq
            pt = TrendReq(hl="en-US", tz=360, timeout=(10, 35))
            pt.build_payload(keywords[:1], timeframe="today 5-y", geo="US")
            df = pt.interest_over_time()
            if df.empty:
                return [], []

            kw = keywords[0]
            if kw not in df.columns:
                kw = df.columns[0]

            # Average by calendar month
            monthly: dict[int, list[float]] = {m: [] for m in range(1, 13)}
            for ts, row in df.iterrows():
                monthly[ts.month].append(float(row[kw]))

            points = [
                SeasonalityPoint(
                    month=m,
                    relative_interest=round(sum(monthly[m]) / len(monthly[m]), 1) if monthly[m] else 0.0,
                )
                for m in range(1, 13)
            ]

            # Peak months = months with interest ≥ 80% of max
            max_interest = max(p.relative_interest for p in points) or 1
            peak = [p.month for p in points if p.relative_interest >= max_interest * 0.8]

            log_fn(f"[niche_research] Seasonality peaks: months {peak}")
            return points, peak

        except Exception as exc:
            err_str = str(exc).lower()
            if "429" in err_str or "rate" in err_str or "too many" in err_str:
                if attempt < max_retries - 1:
                    backoff = 20.0 * (2 ** attempt) + random.uniform(0, 5)
                    log_fn(f"[niche_research] Seasonality rate-limited, retrying in {backoff:.0f}s...")
                    _time.sleep(backoff)
                    continue
            log_fn(f"[niche_research] Seasonality fetch failed: {exc}")
            return [], []
    return [], []


# ── Adapter setup ─────────────────────────────────────────────────────────────

def _build_adapters(
    store_config: StoreConfig | None,
    override: list[str] | None,
    log_fn: Callable,
) -> list:
    from adapters.research.etsy_autocomplete import EtsyAutocompleteAdapter
    from adapters.research.google_trends import GoogleTrendsAdapter
    from adapters.research.reddit_etsy import RedditEtsyAdapter
    from adapters.research.erank import ERankAdapter
    from adapters.research.marmalead import MarmaleadAdapter
    from adapters.research.pinterest_trends import PinterestTrendsAdapter

    factories = {
        "etsy_autocomplete": EtsyAutocompleteAdapter,
        "google_trends": GoogleTrendsAdapter,
        "reddit_etsy": RedditEtsyAdapter,
        "erank": ERankAdapter,
        "marmalead": MarmaleadAdapter,
        "pinterest_trends": PinterestTrendsAdapter,
    }
    names = override or list(factories.keys())
    result = []
    for name in names:
        if name not in factories:
            continue
        try:
            if name == "reddit_etsy" and store_config and store_config.niche.subreddits:
                from adapters.research.reddit_etsy import RedditEtsyAdapter
                result.append(RedditEtsyAdapter(subreddits=store_config.niche.subreddits))
            else:
                result.append(factories[name]())
        except Exception as exc:
            log_fn(f"[niche_research] Could not init {name}: {exc}")
    return result


# ── Score aggregation ─────────────────────────────────────────────────────────

def _aggregate_scores(
    signals: list[NicheSignal],
    scrape_data: list[KeywordSearchData],
) -> tuple[float, float, float, float]:
    """Returns (demand, competition, margin, trend) 0–100."""
    import math

    # ── Demand ────────────────────────────────────────────────────────────────
    searches = [s.monthly_searches for s in signals if s.monthly_searches > 0]
    if searches:
        mx = max(searches)
        demand = min(100.0, sum(searches) / len(searches) / max(mx, 1) * 100)
    else:
        demand = 30.0

    # Favorites-based demand boost: favorites = explicit save-for-later = buyer intent.
    # Log scale: avg 50 favs → +5, avg 500 → +13, avg 5000 → +20 (hard cap).
    # This is the single closest proxy to eRank's "engagement" metric without an API key.
    if scrape_data:
        fav_scores = [k.avg_favorites for k in scrape_data if k.avg_favorites > 0]
        if fav_scores:
            avg_fav = sum(fav_scores) / len(fav_scores)
            fav_boost = min(20.0, math.log10(max(1.0, avg_fav)) / math.log10(5000) * 20)
            demand = min(100.0, demand + fav_boost)

    # ── Competition ───────────────────────────────────────────────────────────
    # Use scraper's quality score (more accurate) if available; fall back to signal data
    if scrape_data:
        avg_quality = sum(k.competition_quality_score for k in scrape_data) / len(scrape_data)
        competition = round(avg_quality, 1)   # 0=easy, 100=saturated
    else:
        # Use autocomplete competition scores (based on real Etsy listing counts)
        comp_vals = [s.competition_score for s in signals if s.competition_score > 0]
        if comp_vals:
            # Weighted: lower-listing-count keywords = less competition (lower score)
            competition = sum(comp_vals) / len(comp_vals)
        else:
            competition = 50.0

    # ── Margin ────────────────────────────────────────────────────────────────
    # Use real scraped prices if available; estimate from competition if not
    if scrape_data:
        prices = [k.avg_price_usd for k in scrape_data if k.avg_price_usd > 0]
    else:
        prices = [s.avg_price_usd for s in signals if s.avg_price_usd > 0]

    if prices:
        avg_price = sum(prices) / len(prices)
        if avg_price >= 60:
            margin = 90.0
        elif avg_price >= 30:
            margin = 70.0 + (avg_price - 30) / 30 * 20
        elif avg_price >= 10:
            margin = 40.0 + (avg_price - 10) / 20 * 30
        else:
            margin = 20.0 + avg_price / 10 * 20
    else:
        # Estimate margin from competition: lower competition = better margin potential
        # Range: 25 (high comp) to 75 (low comp)
        margin = round(75.0 - competition * 0.5, 1)

    # ── Trend ─────────────────────────────────────────────────────────────────
    trend_map = {"rising": 85.0, "stable": 50.0, "declining": 20.0}
    trend_vals = [trend_map.get(s.trend_direction, 50.0) for s in signals]
    trend = sum(trend_vals) / len(trend_vals) if trend_vals else 50.0

    return round(demand, 1), round(competition, 1), round(margin, 1), round(trend, 1)


def _opportunity_score(demand: float, competition: float, margin: float, trend: float,
                       scrape_data: list | None = None) -> float:
    """
    demand×0.30 + (100-competition)×0.30 + margin×0.20 + trend×0.20

    Gap bonus (+5): Google Trends rising AND Etsy listing count still low (<50k).
    This is the textbook breakout signal: consumer interest outpacing seller supply.
    """
    base = demand * 0.30 + (100 - competition) * 0.30 + margin * 0.20 + trend * 0.20
    # Cross-signal gap bonus: trending + undersupplied
    if scrape_data and trend >= 70:
        avg_listings = sum(k.total_listing_count for k in scrape_data if k.total_listing_count > 0)
        n = sum(1 for k in scrape_data if k.total_listing_count > 0)
        if n > 0 and (avg_listings / n) < 50_000:
            base = min(100.0, base + 5.0)
    return round(base, 1)


# ── LLM synthesis ─────────────────────────────────────────────────────────────

def _llm_synthesis(
    seed_keywords: list[str],
    signals: list[NicheSignal],
    scrape_data: list[KeywordSearchData],
    seasonality: list[SeasonalityPoint],
    store_config: StoreConfig | None,
    log_fn: Callable,
) -> dict:
    try:
        # Keep prompt compact — large prompts time out on CPU inference
        top_signals = sorted(signals, key=lambda s: s.monthly_searches, reverse=True)[:8]
        signals_summary = [
            {"kw": s.keyword, "searches": s.monthly_searches,
             "comp": s.competition_score, "price": s.avg_price_usd, "trend": s.trend_direction}
            for s in top_signals
        ]

        scrape_summary = [
            {"kw": k.keyword, "listings": k.total_listing_count,
             "sweet_spot": k.price_sweet_spot, "avg_price": k.avg_price_usd,
             "comp_quality": k.competition_quality_score,
             "rev_mo": k.estimated_market_monthly_revenue_usd,
             "titles": k.top_listing_titles[:2]}
            for k in scrape_data[:4]
        ]

        season_str = ""
        if seasonality:
            month_names = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
            season_str = ", ".join(
                f"{month_names[p.month-1]}:{p.relative_interest:.0f}"
                for p in seasonality
            )

        brand_ctx = ""
        if store_config:
            brand_ctx = (f"Audience: {store_config.niche.target_audience}. "
                         f"Products: {', '.join(store_config.product_types)}.")

        prompt = f"""Etsy niche analyst. Keywords: {seed_keywords}. {brand_ctx}
Scrape: {json.dumps(scrape_summary)}
Signals: {json.dumps(signals_summary)}
Seasonality: {season_str or 'n/a'}

Return ONLY this JSON (no explanation, no markdown):
{{"keyword_clusters":[{{"cluster_name":"","keywords":[],"opportunity_score":0,"avg_competition_quality":0,"estimated_monthly_revenue_potential_usd":0,"rationale":""}}],"underserved_angles":[],"winning_styles":[],"recommended_product_types":[],"competitor_gaps":[],"pricing_insights":"","entry_strategy":""}}

Fill in real values. Return ONLY valid JSON."""

        llm = get_llm_with_fallback()
        if not llm.health_check():
            log_fn("[niche_research] LLM synthesis skipped: no configured healthy LLM")
            return _fallback_synthesis()
        resp = llm.complete(prompt, json_mode=True)
        content = resp.content.strip()

        # Try direct parse first
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            # Fallback: extract the outermost JSON object via regex
            import re
            m = re.search(r'\{[\s\S]*\}', content)
            if m:
                try:
                    data = json.loads(m.group(0))
                except json.JSONDecodeError:
                    raise
            else:
                raise ValueError("No JSON object found in LLM response")

        log_fn(f"[niche_research] LLM synthesis done (${resp.cost_usd:.4f})")
        return data
    except Exception as exc:
        log_fn(f"[niche_research] LLM synthesis failed: {exc}")
        return _fallback_synthesis()


def _fallback_synthesis() -> dict:
    return {
        "keyword_clusters": [],
        "underserved_angles": [],
        "winning_styles": [],
        "recommended_product_types": ["digital_download", "wall_art"],
        "competitor_gaps": [],
        "pricing_insights": "",
        "entry_strategy": "",
    }


# ── Utility ───────────────────────────────────────────────────────────────────

def _signal_to_dict(s: NicheSignal) -> dict:
    return {
        "keyword": s.keyword, "monthly_searches": s.monthly_searches,
        "competition_score": s.competition_score, "avg_price_usd": s.avg_price_usd,
        "trend_direction": s.trend_direction, "source": s.source,
    }


def _minimal_report(seed_keywords: list[str], store_slug: str, sources: list[str]) -> NicheReport:
    return NicheReport(
        store_slug=store_slug,
        generated_at=datetime.now(timezone.utc).isoformat(),
        seed_keywords=seed_keywords,
        keyword_signals=[],
        sources_used=sources,
        report_id=f"rpt_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
    )


def load_latest_report(store_slug: str) -> NicheReport | None:
    report_dir = WORKSPACE / store_slug / "_niche_research"
    if not report_dir.exists():
        return None
    files = sorted(report_dir.glob("niche_report_*.json"), reverse=True)
    if not files:
        return None
    data = json.loads(files[0].read_text(encoding="utf-8"))
    # Handle old reports missing new fields gracefully
    return NicheReport(**{k: data.get(k, v)
                          for k, v in NicheReport.__dataclass_fields__.items()
                          for data in [data]})


def list_reports(store_slug: str) -> list[Path]:
    report_dir = WORKSPACE / store_slug / "_niche_research"
    if not report_dir.exists():
        return []
    return sorted(report_dir.glob("niche_report_*.json"), reverse=True)
