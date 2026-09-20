"""
Stage 0 — Niche Research
Multi-source Etsy niche intelligence pipeline:

  1. Etsy Search Scraper  — sampled listing counts, prices, reviews, favorites,
                            Star Seller %, and Bestseller %
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
import os
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
    total_listing_count: int | None
    avg_price_usd: float | None
    price_min: float | None
    price_p25: float | None
    price_median: float | None
    price_p75: float | None
    price_max: float | None
    price_sweet_spot: str | None
    avg_review_count: float | None
    pct_star_sellers: float | None
    pct_bestsellers: float | None
    competition_quality_score: float | None
    estimated_market_monthly_revenue_usd: float | None
    sampled_listing_count: int = 0
    top_listing_titles: list[str] = field(default_factory=list)
    avg_favorites: float | None = None
    max_favorites: int | None = None
    pct_high_favorites: float | None = None
    listing_samples: list[dict] = field(default_factory=list)

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
    demand_score: float | None = None
    competition_score: float | None = None
    margin_score: float | None = None
    trend_velocity_score: float | None = None
    opportunity_score: float | None = None

    # ── Market-level metrics ───────────────────────────────────────────────────
    avg_price_usd: float | None = None
    price_sweet_spot: str = ""
    estimated_market_monthly_revenue_usd: float | None = None
    avg_competition_quality: float | None = None

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
    include_seasonality: bool = True,
    allow_llm_synthesis: bool = True,
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
    if include_seasonality:
        seasonality, peak_months = _get_seasonality(seed_keywords[:2], _log)
    else:
        seasonality, peak_months = [], []

    # ── Step 4: Aggregate scores ──────────────────────────────────────────────
    demand, competition, margin, trend = _aggregate_scores(
        all_signals, keyword_search_data
    )
    opportunity = _opportunity_score(demand, competition, margin, trend, keyword_search_data)

    _log("[niche_research] Aggregate ranking is TBD pending a validated score model")

    # ── Step 5: Market-level metrics from scraper ─────────────────────────────
    avg_price: float | None = None
    price_sweet = ""
    market_revenue: float | None = None
    avg_comp_quality: float | None = None
    if keyword_search_data:
        observed_prices = [
            k.avg_price_usd
            for k in keyword_search_data
            if k.avg_price_usd is not None and k.avg_price_usd > 0
        ]
        avg_price = sum(observed_prices) / len(observed_prices) if observed_prices else None
        # Use the keyword with most data for sweet spot
        best = max(
            keyword_search_data,
            key=lambda k: k.total_listing_count if k.total_listing_count is not None else -1,
            default=None,
        )
        price_sweet = best.price_sweet_spot if best and best.price_sweet_spot else ""
        # Historical revenue and competition-quality fields are heuristic, not
        # observations. Keep them out of the report-level evidence contract.

    # ── Step 6: LLM synthesis ─────────────────────────────────────────────────
    if allow_llm_synthesis:
        synthesis = _llm_synthesis(
            seed_keywords, all_signals, keyword_search_data,
            seasonality, store_config, _log
        )
    else:
        _log("[niche_research] LLM synthesis skipped for background scanner")
        synthesis = _fallback_synthesis()

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
        avg_price_usd=round(avg_price, 2) if avg_price is not None else None,
        price_sweet_spot=price_sweet,
        estimated_market_monthly_revenue_usd=None,
        avg_competition_quality=None,
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
        report_id=f"rpt_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
    )

    path = report.save()
    _log(f"[niche_research] Done in {time.time()-t0:.1f}s - saved {path.name}")
    return report


# ── Etsy scraper step ─────────────────────────────────────────────────────────

def _run_scraper(
    keywords: list[str],
    log_fn: Callable,
) -> list[KeywordSearchData]:
    api_results = _run_etsy_open_api_search(keywords, log_fn)
    if api_results:
        return api_results

    from adapters.research.etsy_search_scraper import (
        EtsyHtmlBlockedError,
        EtsySearchScraper,
        get_etsy_html_block_reason,
        is_etsy_html_blocked,
    )
    html_enabled = os.environ.get("ETSY_HTML_SCRAPER_ENABLED", "0").strip().lower() in {"1", "true", "yes"}
    if not html_enabled:
        log_fn("[niche_research] Etsy listing evidence unavailable: set Etsy Open API credentials, or opt into blocked-prone HTML scraping with ETSY_HTML_SCRAPER_ENABLED=1")
        return []
    if is_etsy_html_blocked():
        log_fn(f"[niche_research] Etsy HTML scraper skipped: {get_etsy_html_block_reason()}")
        return []

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
                log_fn(f"[niche_research] Etsy HTML scraper unavailable for '{kw}': {sr.error}")
                if is_etsy_html_blocked():
                    break
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
                competition_quality_score=None,
                estimated_market_monthly_revenue_usd=None,
                sampled_listing_count=len(sr.listings),
                top_listing_titles=[l.title for l in sr.listings[:5] if l.title],
                avg_favorites=sr.avg_favorites,
                max_favorites=sr.max_favorites,
                pct_high_favorites=sr.pct_high_favorites,
                listing_samples=[asdict(listing) for listing in sr.listings],
            )
            results.append(ksd)
            log_fn(
                f"[niche_research] '{kw}': {_format_count(sr.total_listing_count)} listings  "
                f"{len(sr.listings)} sampled  avg {_format_usd(pd.mean)}  "
                f"sweet spot {pd.sweet_spot or 'TBD'}  avg favs {_format_count(sr.avg_favorites)}"
            )
        except Exception as exc:
            log_fn(f"[niche_research] scraper error '{kw}': {exc}")
            if isinstance(exc, EtsyHtmlBlockedError) or is_etsy_html_blocked():
                break
    scraper.close()
    return results


def _run_etsy_open_api_search(
    keywords: list[str],
    log_fn: Callable,
) -> list[KeywordSearchData]:
    try:
        from adapters.research.etsy_open_api import EtsyOpenAPIClient, is_etsy_open_api_configured
    except Exception as exc:
        log_fn(f"[niche_research] Etsy Open API unavailable: {exc}")
        return []

    if not is_etsy_open_api_configured():
        log_fn("[niche_research] Etsy Open API skipped: missing ETSY_X_API_KEY or ETSY_API_KEYSTRING + ETSY_SHARED_SECRET")
        return []

    client = EtsyOpenAPIClient()
    results: list[KeywordSearchData] = []
    targets = keywords[:4]
    log_fn(f"[niche_research] Fetching Etsy Open API listing evidence for: {targets}")
    try:
        for kw in targets:
            try:
                sr = client.search_listings(kw, limit=60)
            except Exception as exc:
                log_fn(f"[niche_research] Etsy Open API error for '{kw}': {exc}")
                continue
            if not sr.listings:
                log_fn(f"[niche_research] Etsy Open API returned no listings for '{kw}'")
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
                competition_quality_score=None,
                estimated_market_monthly_revenue_usd=None,
                sampled_listing_count=len(sr.listings),
                top_listing_titles=[l.title for l in sr.listings[:5] if l.title],
                avg_favorites=sr.avg_favorites,
                max_favorites=sr.max_favorites,
                pct_high_favorites=sr.pct_high_favorites,
                listing_samples=[asdict(listing) for listing in sr.listings],
            )
            results.append(ksd)
            log_fn(
                f"[niche_research] '{kw}': Etsy API {_format_count(sr.total_listing_count)} listings  "
                f"{len(sr.listings)} sampled  avg {_format_usd(pd.mean)}  "
                f"sweet spot {pd.sweet_spot or 'TBD'}  avg favs {_format_count(sr.avg_favorites)}"
            )
    finally:
        client.close()
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
    max_retries = max(1, int(os.environ.get("SEASONALITY_MAX_RETRIES", "1") or "1"))
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

            # Preserve the provider's observations without inventing a cutoff for
            # what qualifies as a "peak" month. A validated model can populate
            # peak_months later; until then the value remains explicitly unknown.
            log_fn("[niche_research] Seasonality observations collected; peak months TBD")
            return points, []

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
    from adapters.research.etsy_open_api import EtsyOpenAPIAdapter
    from adapters.research.google_trends import GoogleTrendsAdapter
    from adapters.research.google_suggest import GoogleSuggestAdapter
    from adapters.research.reddit_etsy import RedditEtsyAdapter
    from adapters.research.erank import ERankAdapter
    from adapters.research.marmalead import MarmaleadAdapter
    from adapters.research.pinterest_trends import PinterestTrendsAdapter

    factories = {
        "etsy_open_api": EtsyOpenAPIAdapter,
        "etsy_autocomplete": EtsyAutocompleteAdapter,
        "google_trends": GoogleTrendsAdapter,
        "google_suggest": GoogleSuggestAdapter,
        "reddit_etsy": RedditEtsyAdapter,
        "erank": ERankAdapter,
        "marmalead": MarmaleadAdapter,
        "pinterest_trends": PinterestTrendsAdapter,
    }
    names = override or list(factories.keys())
    result = []
    for name in names:
        if name not in factories:
            log_fn(f"[niche_research] Unknown adapter: {name}")
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
) -> tuple[None, None, None, None]:
    """Scores stay unknown until a versioned model is calibrated on outcomes."""
    return None, None, None, None


def _opportunity_score(*_args, **_kwargs) -> None:
    """No ranking is emitted without a validated, versioned model."""
    return None


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
        top_signals = sorted(signals, key=lambda s: s.monthly_searches or -1, reverse=True)[:8]
        signals_summary = [
            {"kw": s.keyword, "searches": s.monthly_searches,
             "comp": s.competition_score, "price": s.avg_price_usd,
             "trend": s.trend_direction, "relative_interest": s.relative_interest,
             "relative_interest_period": s.relative_interest_period}
            for s in top_signals
        ]

        scrape_summary = [
            {"kw": k.keyword, "listings": k.total_listing_count,
             "sweet_spot": k.price_sweet_spot, "avg_price": k.avg_price_usd,
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
{{"keyword_clusters":[{{"cluster_name":"","keywords":[],"rationale":""}}],"underserved_angles":[],"winning_styles":[],"recommended_product_types":[],"competitor_gaps":[],"pricing_insights":"","entry_strategy":""}}

Use only the observations supplied above. Do not estimate scores, demand, sales, revenue, or profitability. Return ONLY valid JSON."""

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

        cost_label = f"${resp.cost_usd:.4f}" if resp.cost_usd is not None else "TBD"
        log_fn(f"[niche_research] LLM synthesis done (cost: {cost_label})")
        return data
    except Exception as exc:
        log_fn(f"[niche_research] LLM synthesis failed: {exc}")
        return _fallback_synthesis()


def _fallback_synthesis() -> dict:
    return {
        "keyword_clusters": [],
        "underserved_angles": [],
        "winning_styles": [],
        "recommended_product_types": [],
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
        "relative_interest": s.relative_interest,
        "relative_interest_period": s.relative_interest_period,
        "observed_at": s.observed_at,
        "geography": s.geography,
        "query": s.query,
        "position": s.position,
        "time_series": s.time_series,
        "metadata": s.metadata,
    }


def _format_count(value: int | float | None) -> str:
    return f"{value:,.0f}" if value is not None else "TBD"


def _format_usd(value: float | None) -> str:
    return f"${value:.2f}" if value is not None else "TBD"


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
