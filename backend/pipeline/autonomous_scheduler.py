"""
Autonomous keyword scanner scheduler.

Runs a background thread that continuously:
  1. Picks the next batch of keywords from the DB (breakouts first, then unscanned, then stale)
  2. Runs niche_research on each keyword
  3. Expands: feeds autocomplete + competitor tags + trends related queries back as new seeds
  4. Sleeps between keywords to respect rate limits
  5. Periodically runs SeedDiscovery to keep the seed library growing

Usage:
    scheduler = AutonomousScheduler(log_fn=print)
    scheduler.start()          # non-blocking, runs in background
    scheduler.pause()
    scheduler.resume()
    scheduler.stop()
    scheduler.status()         # -> dict

State is persisted to workspace/_keyword_db/scheduler_state.json so the
scheduler can resume after app restart.
"""

import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from pipeline import keyword_database as kdb

STATE_FILE = Path(__file__).parent.parent / "workspace/_keyword_db/scheduler_state.json"

# Rates: how long to sleep between each keyword scan (seconds)
RATES = {
    "continuous": 90,   # ~40 keywords/hour — gentle background operation
    "burst":      20,   # ~180 keywords/hour — fast batch when app is idle
    "slow":       300,  # ~12 keywords/hour — minimal footprint
}

# How often (in keywords scanned) to run full seed discovery
DISCOVER_EVERY_N_SCANS = 50

# Max expansion depth — don't expand keywords that are already 3 levels deep
MAX_EXPANSION_DEPTH = 3


class AutonomousScheduler:
    """
    Thread-safe background keyword scanner.
    All state is written atomically to STATE_FILE for crash recovery.
    """

    def __init__(
        self,
        store_slug: str = "__global__",
        mode: str = "continuous",
        batch_size: int = 5,
        stale_days: int = 30,
        skip_scraper: bool = False,
        log_fn: Optional[Callable] = None,
        on_scan_complete: Optional[Callable] = None,
    ):
        self._store_slug = store_slug
        self._mode = mode
        self._batch_size = batch_size
        self._stale_days = stale_days
        self._skip_scraper = skip_scraper
        self._log = log_fn or print
        self._on_scan_complete = on_scan_complete  # called after each keyword, for UI refresh

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()  # not paused by default

        self._keywords_scanned = 0
        self._new_seeds_found = 0
        self._current_keyword: Optional[str] = None
        self._run_id: Optional[int] = None
        self._started_at: Optional[str] = None
        self._errors: list[str] = []

        kdb.init_db()
        kdb.load_seeds_from_library()
        self._load_state()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            self._log("[scheduler] Already running")
            return
        self._stop_event.clear()
        self._pause_event.set()
        self._keywords_scanned = 0
        self._new_seeds_found = 0
        self._errors = []
        self._started_at = datetime.utcnow().isoformat()
        self._run_id = kdb.log_scheduler_run(mode=self._mode)
        self._thread = threading.Thread(target=self._loop, daemon=True, name="keyword-scanner")
        self._thread.start()
        self._save_state(running=True)
        self._log(f"[scheduler] Started in '{self._mode}' mode — {RATES[self._mode]}s between keywords")

    def pause(self) -> None:
        self._pause_event.clear()
        self._save_state(running=True, paused=True)
        self._log("[scheduler] Paused")

    def resume(self) -> None:
        self._pause_event.set()
        self._save_state(running=True, paused=False)
        self._log("[scheduler] Resumed")

    def stop(self) -> None:
        self._stop_event.set()
        self._pause_event.set()  # unblock if paused
        if self._thread:
            self._thread.join(timeout=10)
        if self._run_id:
            kdb.update_scheduler_run(
                self._run_id,
                keywords_scanned=self._keywords_scanned,
                new_seeds=self._new_seeds_found,
                status="stopped",
            )
        self._save_state(running=False)
        self._log(f"[scheduler] Stopped. Total scanned: {self._keywords_scanned}, new seeds: {self._new_seeds_found}")

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def is_paused(self) -> bool:
        return not self._pause_event.is_set()

    def status(self) -> dict:
        return {
            "running":          self.is_running(),
            "paused":           self.is_paused(),
            "mode":             self._mode,
            "batch_size":       self._batch_size,
            "keywords_scanned": self._keywords_scanned,
            "new_seeds_found":  self._new_seeds_found,
            "current_keyword":  self._current_keyword,
            "started_at":       self._started_at,
            "interval_s":       RATES.get(self._mode, 90),
            "errors":           self._errors[-5:],
        }

    def set_mode(self, mode: str) -> None:
        if mode in RATES:
            self._mode = mode
            self._save_state(running=self.is_running())
            self._log(f"[scheduler] Mode changed to '{mode}' ({RATES[mode]}s/keyword)")

    def set_batch_size(self, n: int) -> None:
        self._batch_size = max(1, min(n, 50))

    # ── Main loop ─────────────────────────────────────────────────────────────

    def _loop(self) -> None:
        self._log("[scheduler] Loop started")
        scans_since_discover = 0

        while not self._stop_event.is_set():
            # Wait if paused
            self._pause_event.wait()
            if self._stop_event.is_set():
                break

            # Periodic seed discovery
            if scans_since_discover >= DISCOVER_EVERY_N_SCANS:
                self._log("[scheduler] Running seed discovery...")
                try:
                    self._run_discovery()
                except Exception as e:
                    self._log(f"[scheduler] Seed discovery failed: {e}")
                scans_since_discover = 0

            # Get next batch
            keywords = kdb.get_next_batch(count=self._batch_size, stale_days=self._stale_days)
            if not keywords:
                self._log("[scheduler] No keywords to scan — running seed discovery...")
                try:
                    added = self._run_discovery()
                    if added == 0:
                        self._log("[scheduler] No new seeds found either — sleeping 10min")
                        self._interruptible_sleep(600)
                except Exception as e:
                    self._log(f"[scheduler] Discovery failed: {e}")
                    self._interruptible_sleep(300)
                continue

            for kw in keywords:
                if self._stop_event.is_set():
                    break
                self._pause_event.wait()

                self._current_keyword = kw
                try:
                    new_seeds = self._scan_and_expand(kw)
                    self._keywords_scanned += 1
                    self._new_seeds_found += new_seeds
                    scans_since_discover += 1

                    if self._run_id:
                        kdb.update_scheduler_run(
                            self._run_id,
                            keywords_scanned=self._keywords_scanned,
                            new_seeds=self._new_seeds_found,
                            status="running",
                        )
                    if self._on_scan_complete:
                        try:
                            self._on_scan_complete(kw)
                        except Exception:
                            pass
                except Exception as e:
                    err = f"'{kw}': {e}"
                    self._errors.append(err)
                    self._log(f"[scheduler] Error on {err}")
                finally:
                    self._current_keyword = None

                # Rate-limited sleep between keywords
                if not self._stop_event.is_set():
                    self._interruptible_sleep(RATES.get(self._mode, 90))

        if self._run_id:
            kdb.update_scheduler_run(
                self._run_id,
                keywords_scanned=self._keywords_scanned,
                new_seeds=self._new_seeds_found,
                status="completed",
            )
        self._save_state(running=False)
        self._log("[scheduler] Loop ended")

    def _scan_and_expand(self, keyword: str) -> int:
        """Scan one keyword and feed results back as new seeds. Returns new seed count."""
        from pipeline.stages.niche_research import run as research_run
        from pipeline.stages.keyword_scanner import (
            _extract_competitor_tags,
            _extract_trends_related,
        )

        self._log(f"[scheduler] Scanning: {keyword}")
        report = research_run(
            seed_keywords=[keyword],
            store_slug=self._store_slug,
            log_fn=self._log,
            skip_scraper=self._skip_scraper,
        )
        kdb.save_scan(keyword, report)

        # Gap analysis — runs after every scan to score the 6 gap types
        if not self._skip_scraper:
            try:
                self._analyze_gaps(keyword, report)
            except Exception as e:
                self._log(f"[scheduler]   Gap analysis failed for '{keyword}': {e}")

        # Expansion — only if we're not too deep
        depth = kdb.get_expansion_depth(keyword)
        if depth >= MAX_EXPANSION_DEPTH:
            self._log(f"[scheduler] '{keyword}' at max depth ({depth}) — skipping expansion")
            return 0

        new_seeds_total = 0

        # Google Suggest expansion — real buyer search queries, free & unblocked
        try:
            from adapters.research.google_suggest import GoogleSuggestAdapter
            gs = GoogleSuggestAdapter()
            sigs = gs.search(keyword)
            gs_kws = [s.keyword for s in sigs if s.keyword != keyword.lower()]
            if gs_kws:
                added = kdb.record_expansion(keyword, gs_kws[:10], "google_suggest", depth + 1)
                new_seeds_total += added
                if added:
                    self._log(f"[scheduler]   +{added} seeds from Google Suggest")
        except Exception as e:
            self._log(f"[scheduler]   Google Suggest failed: {e}")

        # LLM-based expansion — fallback for deeper keyword generation
        try:
            from adapters.registry import get_llm_with_fallback
            llm = get_llm_with_fallback()
            if llm.health_check():
                prompt = f"""Generate 5-8 Etsy search keywords related to "{keyword}" that buyers might type.
Return ONLY a JSON array of strings: ["keyword1", "keyword2", ...]
Make them specific, 2-5 words, realistic search phrases. No markdown, no explanation."""
                resp = llm.complete(prompt, json_mode=True)
                related = json.loads(resp.content)
                if isinstance(related, list) and related:
                    valid = [k.strip().lower() for k in related if isinstance(k, str) and len(k.strip()) > 3 and k.strip().lower() != keyword.lower()]
                    if valid:
                        added = kdb.record_expansion(keyword, valid, "llm_related", depth + 1)
                        new_seeds_total += added
                        if added:
                            self._log(f"[scheduler]   +{added} seeds from LLM expansion")
        except Exception as e:
            self._log(f"[scheduler]   LLM expansion failed: {e}")

        return new_seeds_total

    def _analyze_gaps(self, keyword: str, report) -> None:
        """
        Run gap analysis after a niche_research scan completes.
        Extracts listing IDs and autocomplete terms from the report,
        then calls the gap_analysis stage which fetches listing pages
        for tags/dates and scores all 6 gap types.
        """
        from pipeline.stages.gap_analysis import run as gap_run

        # Convert report to dict for easy field access
        if hasattr(report, "__dataclass_fields__"):
            import dataclasses
            r_dict = dataclasses.asdict(report)
        else:
            r_dict = dict(report)

        # Extract listing IDs from the keyword_search_data embedded in the report
        listing_ids: list[str] = []
        for ksd in r_dict.get("keyword_search_data", []):
            if ksd.get("keyword", "").lower() == keyword.lower():
                # The top listing titles are in keyword_search_data but not IDs —
                # we need to re-scrape briefly or pull from the scraper result stored
                # in the report. Since niche_research doesn't store listing IDs in
                # keyword_search_data, we do a quick targeted search to get IDs.
                break

        # Quick listing ID fetch: run a single-page search to get the top 15 IDs
        if not listing_ids:
            try:
                from adapters.research.etsy_search_scraper import EtsySearchScraper
                scraper = EtsySearchScraper()
                sr = scraper.search(keyword, max_listings=15, page=1)
                listing_ids = [l.listing_id for l in sr.listings if l.listing_id]
                scraper._client.close()
            except Exception as e:
                self._log(f"[scheduler]   Listing ID fetch failed: {e}")

        # Get autocomplete terms for the tag gap analysis
        autocomplete_terms: list[str] = []
        try:
            from adapters.research.etsy_autocomplete import EtsyAutocompleteAdapter
            adapter = EtsyAutocompleteAdapter()
            sigs = adapter.search(keyword)
            autocomplete_terms = [s.keyword for s in sigs]
        except Exception as e:
            self._log(f"[scheduler]   Autocomplete fetch for gap analysis failed: {e}")

        if not listing_ids and not autocomplete_terms:
            self._log(f"[scheduler]   No data for gap analysis of '{keyword}', skipping")
            return

        gap_run(
            keyword=keyword,
            listing_ids=listing_ids,
            autocomplete_terms=autocomplete_terms,
            niche_report_data=r_dict,
            store_slug=self._store_slug,
            log_fn=self._log,
        )

    def _run_discovery(self) -> int:
        from pipeline.stages.keyword_scanner import SeedDiscovery
        disc = SeedDiscovery(log_fn=self._log)
        result = disc.run_all(llm_count=20)
        return result.get("total_added", 0)

    def _interruptible_sleep(self, seconds: float) -> None:
        """Sleep that wakes immediately on stop signal."""
        self._stop_event.wait(timeout=seconds)

    # ── State persistence ─────────────────────────────────────────────────────

    def _save_state(self, running: bool = False, paused: bool = False) -> None:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "running":          running,
            "paused":           paused,
            "mode":             self._mode,
            "batch_size":       self._batch_size,
            "stale_days":       self._stale_days,
            "skip_scraper":     self._skip_scraper,
            "keywords_scanned": self._keywords_scanned,
            "new_seeds_found":  self._new_seeds_found,
            "last_updated":     datetime.utcnow().isoformat(),
        }
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def _load_state(self) -> None:
        if STATE_FILE.exists():
            try:
                state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                self._mode = state.get("mode", self._mode)
                self._batch_size = state.get("batch_size", self._batch_size)
                self._stale_days = state.get("stale_days", self._stale_days)
            except Exception:
                pass


# ── Singleton accessor (one scheduler per app process) ────────────────────────

_instance: Optional[AutonomousScheduler] = None


def get_scheduler(**kwargs) -> AutonomousScheduler:
    global _instance
    if _instance is None:
        _instance = AutonomousScheduler(**kwargs)
    return _instance
