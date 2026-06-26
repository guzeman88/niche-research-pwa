"""
Keyword batch scanner and seed discovery engine.

Two main classes:
  SeedDiscovery  — finds new seed keywords from 4 sources (seasonal, LLM, autocomplete, Etsy trending)
  KeywordScanner — pulls batches from the DB and runs niche_research on each, saving results

Designed for continuous background operation: run scan_batch() repeatedly to build up
the keyword database over time without any manual keyword selection.
"""

import json
import os
import re
import time
from calendar import month_name
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx

from pipeline import keyword_database as kdb
from pipeline.keyword_database import add_seeds_bulk, get_next_batch, save_scan, SEED_PATH


# ---------------------------------------------------------------------------
# Seasonal calendar — events by month (month 1-12)
# ---------------------------------------------------------------------------

_SEASONAL_EVENTS: dict[int, list[str]] = {
    1:  ["new year gift", "winter cozy", "resolution gift", "january birthday"],
    2:  ["valentine's day", "galentine's day", "love gift", "february birthday", "groundhog day"],
    3:  ["st patrick's day", "spring decor", "march birthday", "easter early", "women's day gift"],
    4:  ["easter gifts", "spring gift", "april birthday", "earth day gift", "tax season humor"],
    5:  ["mother's day gifts", "teacher appreciation", "graduation gifts", "may birthday",
        "cinco de mayo", "memorial day"],
    6:  ["father's day gifts", "pride gift", "lgbtq pride", "june birthday", "graduation party",
        "summer gift", "beach gift"],
    7:  ["4th of july", "summer decor", "july birthday", "patriotic gift", "camping gift summer"],
    8:  ["back to school", "teacher gift", "august birthday", "end of summer", "dorm decor"],
    9:  ["fall decor", "autumn gift", "september birthday", "apple picking aesthetic",
        "pumpkin spice", "harvest decor"],
    10: ["halloween", "halloween decor", "spooky gift", "october birthday", "fall gift",
        "day of the dead", "pumpkin decor"],
    11: ["thanksgiving decor", "friendsgiving", "november birthday", "gratitude gift",
        "christmas early", "holiday gift guide", "black friday gift"],
    12: ["christmas gifts", "hanukkah gift", "kwanzaa gift", "holiday decor", "december birthday",
        "new year eve", "secret santa", "ugly sweater", "stocking stuffer"],
}

# Upcoming N months always get priority boost
_LOOKAHEAD_MONTHS = 3


def get_seasonal_seeds() -> list[dict]:
    """
    Return keyword seeds for the current and next 3 months.
    Returns list of dicts: {keyword, domain, source, priority}
    """
    now = datetime.now()
    seeds = []
    for offset in range(_LOOKAHEAD_MONTHS + 1):
        month = ((now.month - 1 + offset) % 12) + 1
        priority = 9 - offset  # current month = priority 9, lookahead gets 8, 7, 6
        label = month_name[month]
        for kw in _SEASONAL_EVENTS.get(month, []):
            seeds.append({
                "keyword": kw,
                "domain": "occasions_holidays",
                "source": f"seasonal_{label.lower()}",
                "priority": priority,
            })
    return seeds


# ---------------------------------------------------------------------------
# LLM brainstorm discovery
# ---------------------------------------------------------------------------

_LLM_SYSTEM = (
    "You are an expert Etsy and print-on-demand niche analyst. "
    "You know what sells on Etsy and what has low competition."
)

_LLM_PROMPT_TEMPLATE = """
Today is {today}. Generate {count} high-opportunity Etsy print-on-demand niche keywords.

Requirements:
- Each keyword should be 2-5 words, the kind someone types into Etsy search
- Prefer niches with passionate buyers, gift-giving occasions, or strong identity/aesthetic angles
- Mix product types: apparel, wall art, mugs, digital downloads, tote bags, stickers
- Avoid oversaturated niches (e.g. "dog mom" alone is oversaturated — be more specific)
- Think about: micro-identities, specific pet breeds, specific professions, trending aesthetics,
  specific humor styles, specific life stages, specific hobbies

Current season / upcoming: {season_hint}

Return ONLY a JSON object with this exact structure:
{{
  "keywords": [
    {{"keyword": "string", "domain": "string", "reason": "string"}}
  ]
}}

Domain must be one of: occasions_holidays, relationships, professions, hobbies, pets, aesthetics,
identity_values, nature_themes, funny_sarcastic, pod_product_types, trending_micro_niches,
pop_culture_themes, life_stages, home_decor_themes
"""


def get_llm_seeds(count: int = 30, log_fn=None) -> list[dict]:
    """
    Use local LLM to brainstorm new seed keywords not already in the library.
    Returns list of dicts: {keyword, domain, source, priority}
    """
    _log = log_fn or print

    try:
        from adapters.registry import get_llm_with_fallback
        llm = get_llm_with_fallback()
    except Exception as e:
        _log(f"[seed_discovery] LLM unavailable: {e}")
        return []

    now = datetime.now()
    month = month_name[now.month]
    upcoming = [month_name[((now.month - 1 + i) % 12) + 1] for i in range(1, 4)]
    season_hint = f"{month} currently; {', '.join(upcoming)} coming up"

    prompt = _LLM_PROMPT_TEMPLATE.format(
        today=now.strftime("%Y-%m-%d"),
        count=count,
        season_hint=season_hint,
    )

    try:
        resp = llm.complete(prompt, system=_LLM_SYSTEM, json_mode=True)
        data = json.loads(resp.content)
        raw = data.get("keywords", [])
        seeds = []
        for item in raw:
            kw = item.get("keyword", "").strip().lower()
            if len(kw) > 3:
                seeds.append({
                    "keyword": kw,
                    "domain": item.get("domain", "trending_micro_niches"),
                    "source": "llm_brainstorm",
                    "priority": 7,
                })
        _log(f"[seed_discovery] LLM brainstorm: {len(seeds)} new keyword ideas")
        return seeds
    except Exception as e:
        _log(f"[seed_discovery] LLM brainstorm failed: {e}")
        return []


# ---------------------------------------------------------------------------
# Bootstrap autocomplete expansion
# ---------------------------------------------------------------------------

# Broad "seed seeds" — intentionally generic so autocomplete produces specific suggestions
_BOOTSTRAP_TERMS = [
    "gift for", "funny", "custom", "personalized", "cute", "vintage",
    "aesthetic", "cottagecore", "minimalist", "plant", "cat", "dog",
    "mom", "teacher", "nurse", "reader", "book", "coffee", "wine",
    "fall", "halloween", "christmas", "wedding", "baby", "birthday",
    "mental health", "self care", "feminist", "pride", "nature",
    "mushroom", "frog", "celestial", "zodiac", "astrology", "witch",
    "gaming", "anime", "retro", "y2k", "boho", "beach", "mountain",
    "hiking", "yoga", "running", "cycling", "fishing", "gardening",
]


def get_autocomplete_seeds(log_fn=None) -> list[dict]:
    """
    Feed broad bootstrap terms through Etsy autocomplete to discover specific niche keywords.
    Returns list of dicts: {keyword, domain, source, priority}
    """
    _log = log_fn or print

    try:
        from adapters.research.etsy_autocomplete import EtsyAutocompleteAdapter
        adapter = EtsyAutocompleteAdapter()
    except Exception as e:
        _log(f"[seed_discovery] Autocomplete adapter unavailable: {e}")
        return []

    discovered: dict[str, dict] = {}

    for term in _BOOTSTRAP_TERMS:
        try:
            signals = adapter.search(term)
            for sig in signals:
                kw = sig.keyword.strip().lower()
                if len(kw) > 5 and kw != term and kw not in discovered:
                    discovered[kw] = {
                        "keyword": kw,
                        "domain": "discovered",
                        "source": "etsy_autocomplete_bootstrap",
                        "priority": 6,
                    }
            time.sleep(0.3)  # polite delay between autocomplete calls
        except Exception:
            continue

    _log(f"[seed_discovery] Autocomplete expansion: {len(discovered)} new seeds")
    return list(discovered.values())


# ---------------------------------------------------------------------------
# Etsy trending page scraper
# ---------------------------------------------------------------------------

_ETSY_TRENDING_URL = "https://www.etsy.com/trending"
_ETSY_CATEGORY_URLS = [
    "https://www.etsy.com/c/gifts-for-her",
    "https://www.etsy.com/c/gifts-for-him",
    "https://www.etsy.com/c/home-and-living",
    "https://www.etsy.com/c/clothing",
    "https://www.etsy.com/c/jewelry",
]

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}


def _extract_trend_labels(html: str) -> list[str]:
    """Pull category/trend text labels from Etsy HTML."""
    found = []

    # JSON-LD / preloaded state keywords
    m = re.search(r'"trending_queries"\s*:\s*(\[.*?\])', html, re.DOTALL)
    if m:
        try:
            queries = json.loads(m.group(1))
            found.extend([q.strip().lower() for q in queries if isinstance(q, str)])
        except Exception:
            pass

    # Category link text patterns
    category_hits = re.findall(r'<a[^>]+class="[^"]*wt-text[^"]*"[^>]*>([^<]{4,60})</a>', html)
    found.extend([h.strip().lower() for h in category_hits if len(h.strip()) > 4])

    # Listing title snippet — frequently repeated short phrases signal trending topics
    titles = re.findall(r'"title"\s*:\s*"([^"]{8,80})"', html)
    # Extract 2-4 word phrases from titles
    phrase_counts: dict[str, int] = {}
    for title in titles[:200]:
        words = title.lower().split()
        for n in (2, 3):
            for i in range(len(words) - n + 1):
                phrase = " ".join(words[i:i+n])
                if all(len(w) > 2 for w in phrase.split()):
                    phrase_counts[phrase] = phrase_counts.get(phrase, 0) + 1
    # Only keep phrases that appeared 3+ times (trending signals)
    for phrase, count in phrase_counts.items():
        if count >= 3:
            found.append(phrase)

    # Deduplicate and filter junk
    seen = set()
    clean = []
    for kw in found:
        kw = re.sub(r'\s+', ' ', kw).strip()
        if len(kw) > 4 and kw not in seen and not kw.startswith("http"):
            seen.add(kw)
            clean.append(kw)
    return clean[:100]


def get_etsy_trending_seeds(log_fn=None) -> list[dict]:
    """
    Scrape etsy.com/trending and category pages for trending search terms.
    No API key required.
    Returns list of dicts: {keyword, domain, source, priority}
    """
    _log = log_fn or print
    html_enabled = os.environ.get("ETSY_HTML_SCRAPER_ENABLED", "0").strip().lower() in {"1", "true", "yes"}
    if not html_enabled:
        _log("[seed_discovery] Etsy trending pages skipped: HTML scraping disabled; set ETSY_HTML_SCRAPER_ENABLED=1 to opt in")
        return []
    try:
        from adapters.research.etsy_search_scraper import get_etsy_html_block_reason, is_etsy_html_blocked, mark_etsy_html_blocked
    except Exception:
        get_etsy_html_block_reason = lambda: ""
        is_etsy_html_blocked = lambda: False
        mark_etsy_html_blocked = lambda reason: None

    if is_etsy_html_blocked():
        _log(f"[seed_discovery] Etsy trending skipped: {get_etsy_html_block_reason()}")
        return []

    collected: dict[str, dict] = {}

    urls = [_ETSY_TRENDING_URL] + _ETSY_CATEGORY_URLS
    for url in urls:
        try:
            resp = httpx.get(url, headers=_HEADERS, timeout=15, follow_redirects=True)
            if resp.status_code != 200:
                if resp.status_code in (403, 429):
                    mark_etsy_html_blocked(f"Etsy trending page returned HTTP {resp.status_code} for {url}")
                    _log(f"[seed_discovery] Etsy trending skipped: {get_etsy_html_block_reason()}")
                    break
                continue
            labels = _extract_trend_labels(resp.text)
            for kw in labels:
                if kw not in collected:
                    collected[kw] = {
                        "keyword": kw,
                        "domain": "trending_micro_niches",
                        "source": "etsy_trending_page",
                        "priority": 8,  # high priority — Etsy itself signals these
                    }
            time.sleep(1.0)
        except Exception as e:
            _log(f"[seed_discovery] Etsy trending scrape failed for {url}: {e}")
            continue

    _log(f"[seed_discovery] Etsy trending pages: {len(collected)} candidate seeds")
    return list(collected.values())


# ---------------------------------------------------------------------------
# SeedDiscovery orchestrator
# ---------------------------------------------------------------------------

class SeedDiscovery:
    """
    Runs all 4 seed discovery methods and bulk-inserts new finds into the DB.
    Each method is independently togglable.
    """

    def __init__(self, log_fn=None):
        self._log = log_fn or print

    def run_all(
        self,
        seasonal: bool = True,
        llm: bool = True,
        autocomplete: bool = True,
        etsy_trending: bool = True,
        llm_count: int = 30,
    ) -> dict:
        """
        Run all enabled discovery methods, persist new seeds to DB.
        Returns summary dict.
        """
        kdb.init_db()
        kdb.load_seeds_from_library()  # ensure base library is loaded

        total_added = 0
        sources_run = []

        if seasonal:
            self._log("[seed_discovery] Running seasonal calendar...")
            seeds = get_seasonal_seeds()
            added = self._persist(seeds)
            self._log(f"[seed_discovery] Seasonal: +{added} new seeds")
            total_added += added
            sources_run.append("seasonal")

        if llm:
            self._log("[seed_discovery] Running LLM brainstorm...")
            seeds = get_llm_seeds(count=llm_count, log_fn=self._log)
            added = self._persist(seeds)
            self._log(f"[seed_discovery] LLM brainstorm: +{added} new seeds")
            total_added += added
            sources_run.append("llm_brainstorm")

        if autocomplete:
            self._log("[seed_discovery] Running Etsy autocomplete expansion...")
            seeds = get_autocomplete_seeds(log_fn=self._log)
            added = self._persist(seeds)
            self._log(f"[seed_discovery] Autocomplete: +{added} new seeds")
            total_added += added
            sources_run.append("etsy_autocomplete")

        if etsy_trending:
            self._log("[seed_discovery] Scraping Etsy trending pages...")
            seeds = get_etsy_trending_seeds(log_fn=self._log)
            added = self._persist(seeds)
            self._log(f"[seed_discovery] Etsy trending: +{added} new seeds")
            total_added += added
            sources_run.append("etsy_trending")

        stats = kdb.get_stats()
        self._log(f"[seed_discovery] Done. Total new seeds added: {total_added}. DB: {stats['total_seeds']} seeds, {stats['scanned']} scanned.")
        return {"total_added": total_added, "sources_run": sources_run, "db_stats": stats}

    def _persist(self, seeds: list[dict]) -> int:
        if not seeds:
            return 0
        added = 0
        for s in seeds:
            ok = kdb.add_seed(
                keyword=s["keyword"],
                domain=s.get("domain", "discovered"),
                source=s.get("source", "auto"),
                priority=s.get("priority", 5),
            )
            if ok:
                added += 1
        return added


# ---------------------------------------------------------------------------
# KeywordScanner — batch research runner
# ---------------------------------------------------------------------------

class KeywordScanner:
    """
    Pulls batches from the keyword DB, runs niche_research on each,
    and saves results back. Designed for continuous / scheduled operation.
    """

    def __init__(self, store_slug: str = "__global__", log_fn=None, skip_scraper: bool = False):
        self._store_slug = store_slug
        self._log = log_fn or print
        self._skip_scraper = skip_scraper
        kdb.init_db()
        kdb.load_seeds_from_library()

    def scan_batch(self, count: int = 10, stale_days: int = 30) -> list:
        """
        Scan the next `count` keywords (unscanned first, then stale).
        Returns list of completed NicheReport objects.
        """
        keywords = get_next_batch(count=count, stale_days=stale_days)
        if not keywords:
            self._log("[scanner] No keywords to scan — DB fully covered (run seed discovery to add more)")
            return []

        self._log(f"[scanner] Scanning {len(keywords)} keywords: {', '.join(keywords)}")
        results = []
        for i, kw in enumerate(keywords, 1):
            self._log(f"[scanner] [{i}/{len(keywords)}] Researching: {kw}")
            try:
                report = self._scan_one(kw)
                results.append(report)
            except Exception as e:
                self._log(f"[scanner] Failed on '{kw}': {e}")
                continue

        self._log(f"[scanner] Batch complete. {len(results)}/{len(keywords)} succeeded.")
        return results

    def scan_single(self, keyword: str):
        """Scan a single keyword and return its NicheReport."""
        kdb.add_seed(keyword, source="manual")
        return self._scan_one(keyword)

    def _scan_one(self, keyword: str):
        from pipeline.stages.niche_research import run as research_run
        report = research_run(
            seed_keywords=[keyword],
            store_slug=self._store_slug,
            log_fn=self._log,
            skip_scraper=self._skip_scraper,
        )
        save_scan(keyword, report)
        return report

    def get_coverage_summary(self) -> dict:
        return kdb.get_stats()

    def get_top_opportunities(self, limit: int = 50) -> list[dict]:
        return kdb.get_top_opportunities(limit=limit)

    def get_top_gaps(self, limit: int = 50) -> list[dict]:
        return kdb.get_top_gaps(limit=limit)


# ---------------------------------------------------------------------------
# Expansion helpers — called by AutonomousScheduler after each scan
# ---------------------------------------------------------------------------

def _extract_competitor_tags(report_dict: dict) -> list[str]:
    """
    Pull unique tags/phrases from competitor listing data embedded in a NicheReport.
    Uses actual listing tags from the gap_reports DB if available (populated by
    gap_analysis stage), otherwise falls back to extracting n-gram phrases from
    listing titles. These become new seed keywords for recursive expansion.
    """
    tags: set[str] = set()

    # Prefer real tags from the most recent gap report for any keyword in this report
    try:
        from pipeline import keyword_database as kdb
        seeds = [ksd.get("keyword", "") for ksd in report_dict.get("keyword_search_data", [])]
        for kw in seeds:
            if kw:
                gr = kdb.get_gap_report(kw)
                if gr:
                    for tag in gr.get("dominant_competitor_tags_json", []):
                        if tag and len(tag) > 3:
                            tags.add(tag.strip().lower())
                    for tag in gr.get("recommended_tags_json", []):
                        if tag and len(tag) > 3:
                            tags.add(tag.strip().lower())
    except Exception:
        pass

    # Fallback: extract n-gram phrases from listing titles
    if len(tags) < 10:
        for ksd in report_dict.get("keyword_search_data", []):
            for title in ksd.get("top_listing_titles", []):
                words = title.lower().split()
                for n in (2, 3, 4):
                    for i in range(len(words) - n + 1):
                        phrase = " ".join(words[i:i + n])
                        if all(len(w) > 2 for w in phrase.split()):
                            tags.add(phrase)

    # Keep reasonable length, discard duplicates of original report seeds
    return [t for t in tags if 6 < len(t) < 60][:30]


def _extract_trends_related(keyword: str) -> list[str]:
    """
    Fetch Google Trends related queries (rising + top) for a keyword.
    Returns a list of related keyword strings.
    """
    try:
        from pytrends.request import TrendReq
        pt = TrendReq(hl="en-US", tz=360, timeout=(10, 25), retries=1, backoff_factor=0.5)
        pt.build_payload([keyword], cat=0, timeframe="today 12-m", geo="US")
        related = pt.related_queries()
        results: list[str] = []
        kw_data = related.get(keyword, {})
        for kind in ("rising", "top"):
            df = kw_data.get(kind)
            if df is not None and not df.empty:
                results.extend(df["query"].tolist()[:10])
        return [r.strip().lower() for r in results if len(r.strip()) > 4]
    except Exception:
        return []


def _deep_autocomplete(
    level1_suggestions: list[str],
    max_per_suggestion: int = 5,
    max_total: int = 40,
) -> list[str]:
    """
    Level-2 autocomplete expansion: run Etsy autocomplete on each level-1
    suggestion to discover more specific long-tail keywords.

    Example:
        level1 for "dog mom" → ["dog mom mug", "dog mom shirt", ...]
        level2 for "dog mom mug" → ["dog mom mug funny", "dog mom mug personalized", ...]

    Args:
        level1_suggestions: Autocomplete terms from the first-level search.
        max_per_suggestion: Max new terms to keep per suggestion (avoids explosion).
        max_total: Hard cap on total returned terms.

    Returns:
        List of unique level-2 keyword strings not already in level1_suggestions.
    """
    try:
        from adapters.research.etsy_autocomplete import EtsyAutocompleteAdapter
        adapter = EtsyAutocompleteAdapter()
    except Exception:
        return []

    level1_set = {kw.strip().lower() for kw in level1_suggestions}
    discovered: dict[str, None] = {}  # ordered deduplication

    for suggestion in level1_suggestions[:15]:  # limit breadth to stay polite
        if len(discovered) >= max_total:
            break
        try:
            sigs = adapter.search(suggestion)
            count = 0
            for sig in sigs:
                kw = sig.keyword.strip().lower()
                if kw and kw not in level1_set and kw not in discovered:
                    discovered[kw] = None
                    count += 1
                    if count >= max_per_suggestion:
                        break
            time.sleep(0.4)  # polite rate limit between level-2 calls
        except Exception:
            continue

    return list(discovered.keys())[:max_total]


# ---------------------------------------------------------------------------
# Compound keyword generator
# ---------------------------------------------------------------------------

# Domain pairs that tend to produce high-value compound keywords
_COMPOUND_PAIRS = [
    ("professions", "occasions_holidays"),
    ("professions", "funny_sarcastic"),
    ("professions", "pod_product_types"),
    ("relationships", "occasions_holidays"),
    ("relationships", "hobbies"),
    ("pets", "occasions_holidays"),
    ("pets", "aesthetics"),
    ("hobbies", "occasions_holidays"),
    ("hobbies", "identity_values"),
    ("aesthetics", "nature_themes"),
    ("trending_micro_niches", "pod_product_types"),
]

# Representative samples from each domain for compound generation
_DOMAIN_SAMPLES: dict[str, list[str]] = {}


def _get_domain_samples(limit_per_domain: int = 10) -> dict[str, list[str]]:
    """Load representative keywords from each domain for compound generation."""
    global _DOMAIN_SAMPLES
    if _DOMAIN_SAMPLES:
        return _DOMAIN_SAMPLES
    try:
        with open(SEED_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        for domain, keywords in data.get("domains", {}).items():
            _DOMAIN_SAMPLES[domain] = keywords[:limit_per_domain]
    except Exception:
        pass
    return _DOMAIN_SAMPLES


def generate_compound_keywords(
    max_per_pair: int = 20,
    log_fn=None,
) -> int:
    """
    Cross-pollinate domain lists to generate compound search phrases.
    E.g. "nurse" x "graduation gift" = "nurse graduation gift"
    Returns count of new seeds added.
    """
    _log = log_fn or print
    samples = _get_domain_samples(limit_per_domain=15)
    total_added = 0

    for domain_a, domain_b in _COMPOUND_PAIRS:
        a_kws = samples.get(domain_a, [])
        b_kws = samples.get(domain_b, [])
        if not a_kws or not b_kws:
            continue

        compounds: list[str] = []
        for a in a_kws:
            a_core = a.replace(" gift", "").replace(" lover", "").strip()
            for b in b_kws:
                b_core = b.replace("gifts for ", "").strip()
                compound = f"{a_core} {b_core}"
                if 8 < len(compound) < 55 and compound not in compounds:
                    compounds.append(compound)
                if len(compounds) >= max_per_pair:
                    break
            if len(compounds) >= max_per_pair:
                break

        if compounds:
            added = kdb.add_seeds_bulk(
                compounds,
                domain="compound",
                source=f"compound_{domain_a}x{domain_b}",
                priority=4,
            )
            total_added += added

    _log(f"[compound_gen] Added {total_added} compound keyword seeds")
    return total_added

    def get_top_opportunities(self, limit: int = 50) -> list[dict]:
        return kdb.get_top_opportunities(limit=limit)
