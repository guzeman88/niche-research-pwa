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
import hashlib
import queue
import uuid
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from pipeline import keyword_database as kdb

STATE_FILE = Path(__file__).parent.parent / "workspace/_keyword_db/scheduler_state.json"

# Rates: how long to sleep between each keyword scan (seconds)
RATES = {
    "performance": 30,
    "continuous": 90,   # ~40 keywords/hour — gentle background operation
    "burst":      20,   # ~180 keywords/hour — fast batch when app is idle
    "slow":       300,  # ~12 keywords/hour — minimal footprint
}

# How often (in keywords scanned) to run full seed discovery
DISCOVER_EVERY_N_SCANS = max(25, int(os.environ.get("DISCOVER_EVERY_N_SCANS", "100")))

# Max expansion depth — don't expand keywords that are already 3 levels deep
MAX_EXPANSION_DEPTH = max(1, int(os.environ.get("MAX_EXPANSION_DEPTH", "2")))



class AutonomousScheduler:
    """
    Thread-safe background keyword scanner.
    All state is written atomically to STATE_FILE for crash recovery.
    """

    def __init__(
        self,
        store_slug: str = "__global__",
        mode: str = "performance",
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
        self._log_fn = log_fn or print
        self._last_progress_at = None
        self._consecutive_failures = 0
        self._fatal_error = None
        self._on_scan_complete = on_scan_complete  # called after each keyword, for UI refresh

        self._thread: Optional[threading.Thread] = None
        self._secondary_thread: Optional[threading.Thread] = None
        self._secondary_queue: queue.Queue[str] = queue.Queue()
        self._secondary_pending: set[str] = set()
        self._secondary_lock = threading.Lock()
        self._secondary_current: list[str] = []
        self._secondary_last_progress_at: Optional[str] = None
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()  # not paused by default

        self._keywords_scanned = 0
        self._new_seeds_found = 0
        self._current_keyword: Optional[str] = None
        self._run_id: Optional[int] = None
        self._started_at: Optional[str] = None
        self._last_external_discovery_at: Optional[str] = None
        self._external_discovery_by_source: dict[str, str] = {}
        self._external_discovery_fingerprints: dict[str, list[str]] = {}
        self._errors: list[str] = []

        kdb.init_db()
        kdb.load_seeds_from_library()
        try:
            from services.supabase_collection_hydration import hydrate_collection_state
            hydration = hydrate_collection_state()
            if hydration.get("error"):
                self._log(f"[scheduler] Durable queue hydration failed: {hydration['error']}")
            elif hydration.get("configured"):
                self._log(
                    f"[scheduler] Restored {hydration.get('seeds', 0)} seeds and "
                    f"{hydration.get('states', 0)} collection states from Supabase"
                )
        except Exception as exc:
            self._log(f"[scheduler] Durable queue hydration failed: {exc}")
        self._load_state()
        self._hydrate_external_discovery_fingerprints()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def _log(self, message: str) -> None:
        try:
            self._log_fn(message)
        except UnicodeEncodeError:
            try:
                self._log_fn(message.encode("ascii", errors="backslashreplace").decode("ascii"))
            except Exception:
                pass
        except Exception:
            pass

    def _run_guarded(self) -> None:
        status = "completed"
        try:
            self._loop()
        except Exception as exc:
            status = "failed"
            self._fatal_error = str(exc)
            self._errors.append(str(exc))
            self._log(f"[scheduler] Worker failed: {exc}")
        finally:
            stop_was_requested = self._stop_event.is_set()
            self._stop_event.set()
            if stop_was_requested:
                status = "stopped"
            if self._run_id:
                kdb.update_scheduler_run(self._run_id, keywords_scanned=self._keywords_scanned,
                    new_seeds=self._new_seeds_found, status=status, error_msg=self._fatal_error)
            self._save_state(running=False)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            self._log("[scheduler] Already running")
            return
        self._stop_event.clear()
        self._pause_event.set()
        self._keywords_scanned = 0
        self._new_seeds_found = 0
        self._errors = []
        self._fatal_error = None
        self._consecutive_failures = 0
        self._started_at = datetime.utcnow().isoformat()
        self._run_id = kdb.log_scheduler_run(mode=self._mode)
        self._thread = threading.Thread(target=self._run_guarded, daemon=True, name="keyword-scanner")
        self._secondary_thread = threading.Thread(
            target=self._secondary_loop,
            daemon=True,
            name="secondary-evidence-collector",
        )
        self._save_state(running=True)
        self._secondary_thread.start()
        self._thread.start()
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
        if self._secondary_thread:
            self._secondary_thread.join(timeout=10)
        self._save_state(running=self.is_running())
        self._log("[scheduler] Stop requested; current operation will finish before shutdown")

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def is_paused(self) -> bool:
        return not self._pause_event.is_set()

    def status(self) -> dict:
        return {
            "running":          self.is_running(),
            "last_progress_at": self._last_progress_at,
            "consecutive_failures": self._consecutive_failures,
            "fatal_error": self._fatal_error,
            "health": "failed" if self._fatal_error else "degraded" if self._consecutive_failures else "running" if self.is_running() else "stopped",
            "paused":           self.is_paused(),
            "mode":             self._mode,
            "batch_size":       self._batch_size,
            "keywords_scanned": self._keywords_scanned,
            "new_seeds_found":  self._new_seeds_found,
            "current_keyword":  self._current_keyword,
            "started_at":       self._started_at,
            "interval_s":       self._scan_interval_seconds(),
            "errors":           self._errors[-5:],
            "secondary_collector": {
                "running": bool(self._secondary_thread and self._secondary_thread.is_alive()),
                "queued_keywords": self._secondary_queue.qsize(),
                "current_keywords": list(self._secondary_current),
                "last_progress_at": self._secondary_last_progress_at,
            },
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

            # Discovery feeds have their own provider-derived cadence and must
            # not depend on reaching an arbitrary number of keyword scans.
            self._run_external_discovery()

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
                scan_started = time.monotonic()

                self._current_keyword = kw
                try:
                    new_seeds = self._scan_and_expand(kw)
                    self._last_progress_at = datetime.utcnow().isoformat()
                    self._consecutive_failures = 0
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
                    self._consecutive_failures += 1
                    kdb.save_scan(kw, {"scan_error": str(e), "sources_used": []})
                    if self._consecutive_failures >= 5:
                        raise RuntimeError("Scanner halted after five consecutive failures: " + str(e)) from e
                    self._log(f"[scheduler] Error on {err}")
                finally:
                    self._current_keyword = None

                # Hold the interval between scan starts, not after a scan ends.
                # Provider and persistence work already consume part of the
                # live quota-derived interval and should not be counted twice.
                if not self._stop_event.is_set():
                    elapsed = time.monotonic() - scan_started
                    self._interruptible_sleep(
                        _remaining_interval_seconds(
                            self._scan_interval_seconds(),
                            elapsed,
                        )
                    )

        self._log("[scheduler] Loop ended")

    def _scan_and_expand(self, keyword: str) -> int:
        """Scan one keyword and feed results back as new seeds. Returns new seed count."""
        from pipeline.stages.niche_research import run as research_run
        from pipeline.stages.keyword_scanner import (
            _extract_competitor_tags,
        )

        self._log(f"[scheduler] Scanning: {keyword}")
        adapter_names = _primary_scheduler_adapters()
        include_seasonality = os.environ.get("SCHEDULER_INCLUDE_SEASONALITY", "0").strip().lower() in {"1", "true", "yes"}
        allow_llm_synthesis = os.environ.get("SCHEDULER_ALLOW_LLM_SYNTHESIS", "0").strip().lower() in {"1", "true", "yes"}
        report = research_run(
            seed_keywords=[keyword],
            store_slug=self._store_slug,
            log_fn=self._log,
            adapter_names=adapter_names,
            skip_scraper=self._skip_scraper,
            include_seasonality=include_seasonality,
            allow_llm_synthesis=allow_llm_synthesis,
        )
        has_market_data = _report_has_market_data(report)
        source_data = self._report_to_dict(report)
        if not has_market_data and not source_data.get("sources_used"):
            raise RuntimeError("No research source returned usable data; check provider availability")
        if not has_market_data:
            self._log(
                f"[scheduler]   Thin market evidence for '{keyword}' - saving no-data scores and queuing for evidence refresh"
            )
        kdb.save_scan(keyword, report)
        report_dict = self._report_to_dict(report)

        # Slow secondary providers should only spend requests on phrases that
        # already have marketplace evidence.  This keeps scheduled coverage at
        # 100% while removing unsupported phrases that previously drove the
        # Google Trends useful-yield rate down.
        if has_market_data:
            self._queue_secondary_collection(keyword)

        # Gap analysis — runs after every scan to score the 6 gap types
        if not self._skip_scraper and has_market_data:
            try:
                self._analyze_gaps(keyword, report)
            except Exception as e:
                self._log(f"[scheduler]   Gap analysis failed for '{keyword}': {e}")
        elif not has_market_data:
            self._log(f"[scheduler]   Skipping gap analysis for '{keyword}' until listing evidence is available")

        # Expansion — only if we're not too deep
        depth = kdb.get_expansion_depth(keyword)
        if depth >= MAX_EXPANSION_DEPTH:
            self._log(f"[scheduler] '{keyword}' at max depth ({depth}) — skipping expansion")
            return 0

        new_seeds_total = 0

        if has_market_data:
            try:
                competitor_terms = self._rank_expansion_candidates(
                    _extract_competitor_tags(report_dict),
                    source="expand_competitor_terms",
                )
                if competitor_terms:
                    added = kdb.record_expansion(keyword, competitor_terms[:10], "competitor_terms", depth + 1)
                    new_seeds_total += added
                    if added:
                        self._log(f"[scheduler]   +{added} seeds from competitor phrases/tags")
            except Exception as e:
                self._log(f"[scheduler]   Competitor phrase expansion failed: {e}")

        # Reuse the Google Suggest evidence already collected in this report.
        # A second provider request would only duplicate the same query set.
        suggestion_terms = [
            signal.get("keyword")
            for signal in report_dict.get("keyword_signals", [])
            if signal.get("source") == "google_suggest" and signal.get("keyword")
        ]
        gs_kws = self._rank_expansion_candidates(
            suggestion_terms,
            source="expand_google_suggest",
        )
        expansion_limit = 14 if has_market_data else 6
        if gs_kws:
            added = kdb.record_expansion(keyword, gs_kws[:expansion_limit], "google_suggest", depth + 1)
            new_seeds_total += added
            if added:
                self._log(f"[scheduler]   +{added} seeds from Google Suggest")

        if has_market_data:
            related_terms: list[str] = []
            for signal in report_dict.get("keyword_signals", []):
                if signal.get("source") != "google_trends":
                    continue
                metadata = signal.get("metadata") or {}
                related_terms.extend(metadata.get("related_queries") or [])
            trends_terms = self._rank_expansion_candidates(
                related_terms,
                source="expand_trends_related",
            )
            if trends_terms:
                added = kdb.record_expansion(keyword, trends_terms[:6], "trends_related", depth + 1)
                new_seeds_total += added
                if added:
                    self._log(f"[scheduler]   +{added} seeds from Google Trends related queries")

        # LLM-based expansion — fallback for deeper keyword generation
        if os.environ.get("ALLOW_LLM_KEYWORD_EXPANSION", "0").strip().lower() in {"1", "true", "yes"}:
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
                        valid = self._rank_expansion_candidates(
                            [
                                k.strip().lower()
                                for k in related
                                if isinstance(k, str) and len(k.strip()) > 3 and k.strip().lower() != keyword.lower()
                            ],
                            source="expand_llm_related",
                        )
                        if valid:
                            added = kdb.record_expansion(keyword, valid[:5], "llm_related", depth + 1)
                            new_seeds_total += added
                            if added:
                                self._log(f"[scheduler]   +{added} seeds from LLM expansion")
            except Exception as e:
                self._log(f"[scheduler]   LLM expansion failed: {e}")

        return new_seeds_total

    def _rank_expansion_candidates(
        self,
        candidates: list[str],
        source: str,
    ) -> list[str]:
        accepted: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            kw = " ".join(str(candidate).lower().split())
            if not kw or kw in seen:
                continue
            seen.add(kw)
            if not kdb.is_scanworthy_seed(
                kw,
                domain="discovered",
                source=source,
            ):
                continue
            accepted.append(kw)
        return accepted

    def _report_to_dict(self, report) -> dict:
        if hasattr(report, "__dataclass_fields__"):
            import dataclasses
            return dataclasses.asdict(report)
        return dict(report)

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
                from adapters.research.etsy_search_scraper import EtsySearchScraper, get_etsy_html_block_reason, is_etsy_html_blocked
                if is_etsy_html_blocked():
                    self._log(f"[scheduler]   Listing ID fetch skipped: {get_etsy_html_block_reason()}")
                else:
                    scraper = EtsySearchScraper()
                    try:
                        sr = scraper.search(keyword, max_listings=15, page=1)
                        listing_ids = [l.listing_id for l in sr.listings if l.listing_id]
                    finally:
                        scraper.close()
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
        llm_enabled = os.environ.get("ALLOW_LLM_SEED_DISCOVERY", "0").strip().lower() in {"1", "true", "yes"}
        result = disc.run_all(
            llm=llm_enabled,
            llm_count=20,
            # Etsy does not provide a supported trending-page scraper. Listing
            # collection remains on the approved Open API path.
            etsy_trending=False,
        )
        return result.get("total_added", 0) + self._run_external_discovery()

    def _queue_secondary_collection(self, keyword: str) -> None:
        """Queue slow sources without delaying the Etsy quota-controlled lane."""
        normalized = " ".join(keyword.lower().split())
        if not normalized:
            return
        with self._secondary_lock:
            if normalized in self._secondary_pending:
                return
            self._secondary_pending.add(normalized)
        self._secondary_queue.put(normalized)

    def _secondary_loop(self) -> None:
        """Collect batch-capable and approval-gated keyword sources independently."""
        while not self._stop_event.is_set():
            self._pause_event.wait()
            try:
                first = self._secondary_queue.get(timeout=1)
            except queue.Empty:
                continue
            batch = [first]
            while len(batch) < 5:
                try:
                    batch.append(self._secondary_queue.get_nowait())
                except queue.Empty:
                    break
            self._secondary_current = list(batch)
            try:
                if "google_trends" in _scheduler_research_adapters():
                    self._collect_secondary_provider("google_trends", batch)
                if "reddit_etsy" in _scheduler_research_adapters():
                    self._collect_secondary_provider("reddit_etsy", batch)
                self._secondary_last_progress_at = datetime.utcnow().isoformat()
            except Exception as exc:
                self._errors.append(f"secondary collection: {exc}")
                self._log(f"[scheduler] Secondary collection failed: {exc}")
            finally:
                with self._secondary_lock:
                    self._secondary_pending.difference_update(batch)
                for _keyword in batch:
                    self._secondary_queue.task_done()
                self._secondary_current = []

    def _collect_secondary_provider(self, provider: str, batch: list[str]) -> None:
        from services.provider_telemetry import record_provider_attempt

        if provider == "google_trends":
            from adapters.research.google_trends import GoogleTrendsAdapter
            adapter = GoogleTrendsAdapter()
        elif provider == "reddit_etsy":
            from adapters.research.reddit_etsy import RedditEtsyAdapter
            adapter = RedditEtsyAdapter()
        else:
            return

        started_at = datetime.utcnow()
        if not adapter.is_configured():
            record_provider_attempt(
                provider=provider,
                operation="batch_keyword_search",
                status="not_configured",
                started_at=started_at,
                keyword_count=0,
                row_count=0,
                configured=False,
            )
            return

        due = kdb.provider_keywords_due(
            provider,
            batch,
            stale_days=self._stale_days,
        )
        if not due:
            return
        try:
            signals = adapter.bulk_search(due)
            by_keyword: dict[str, list] = {keyword: [] for keyword in due}
            for signal in signals:
                normalized = " ".join(str(signal.keyword).lower().split())
                if normalized in by_keyword:
                    by_keyword[normalized].append(signal)
            useful_keywords = 0
            stored_rows = 0
            for keyword in due:
                keyword_signals = by_keyword[keyword]
                evidence_rows = kdb.save_provider_signals(keyword, provider, keyword_signals)
                stored_rows += evidence_rows
                if keyword_signals:
                    useful_keywords += 1
                kdb.record_provider_keyword_attempt(
                    provider,
                    keyword,
                    status="completed" if keyword_signals else "no_data",
                    row_count=evidence_rows,
                )
            record_provider_attempt(
                provider=provider,
                operation="batch_keyword_search",
                status="completed" if signals else "no_data",
                started_at=started_at,
                keyword_count=len(due),
                row_count=stored_rows,
                metadata={
                    "batch_capacity": 5 if provider == "google_trends" else None,
                    "eligible_keywords": len(due),
                    "processed_keywords": len(due),
                    "usable_keywords": useful_keywords,
                },
            )
        except Exception as exc:
            for keyword in due:
                kdb.record_provider_keyword_attempt(
                    provider,
                    keyword,
                    status="failed",
                    row_count=0,
                    error=str(exc),
                )
            record_provider_attempt(
                provider=provider,
                operation="batch_keyword_search",
                status="failed",
                started_at=started_at,
                keyword_count=len(due),
                row_count=0,
                error=str(exc),
                metadata={
                    "eligible_keywords": len(due),
                    "processed_keywords": 0,
                    "usable_keywords": 0,
                },
            )

    def _run_external_discovery(self) -> int:
        """Collect each source-native discovery feed on its own cache cadence."""
        now = datetime.utcnow()

        from adapters.research.google_daily_trends import GoogleDailyTrendsAdapter
        from adapters.research.pinterest_trends import PinterestTrendsAdapter

        sources = (
            (GoogleDailyTrendsAdapter, "daily_search_trends"),
            (PinterestTrendsAdapter, "visual_trends"),
        )
        total_added = 0
        for adapter_factory, domain in sources:
            adapter = None
            started_at = datetime.utcnow()
            try:
                adapter = adapter_factory()
                interval_seconds = adapter.discovery_interval_seconds()
                last_value = self._external_discovery_by_source.get(adapter.name)
                if last_value:
                    try:
                        last = datetime.fromisoformat(last_value)
                        if (now - last).total_seconds() < interval_seconds:
                            continue
                    except ValueError:
                        pass
                if not adapter.is_configured():
                    self._log(f"[scheduler] {adapter.name} discovery is not configured")
                    from services.provider_telemetry import record_provider_attempt
                    record_provider_attempt(
                        provider=adapter.name,
                        operation="discovery",
                        status="not_configured",
                        started_at=started_at,
                        keyword_count=0,
                        row_count=0,
                        configured=False,
                    )
                    self._external_discovery_by_source[adapter.name] = now.isoformat()
                    continue
                signals = adapter.discover()
                added = 0
                covered = 0
                new_rows = 0
                known_ordered = list(self._external_discovery_fingerprints.get(adapter.name, []))
                known = set(known_ordered)
                for signal in signals:
                    if not signal.keyword:
                        continue
                    covered += 1
                    fingerprint = _signal_fingerprint(adapter.name, signal)
                    if fingerprint in known:
                        continue
                    known.add(fingerprint)
                    known_ordered.append(fingerprint)
                    new_rows += 1
                    if kdb.add_seed(signal.keyword, domain=domain, source=adapter.name):
                        added += 1
                    kdb.save_provider_signals(
                        signal.keyword,
                        adapter.name,
                        [signal],
                        generated_at=signal.observed_at or now.isoformat(),
                    )
                total_added += added
                self._external_discovery_fingerprints[adapter.name] = known_ordered[-2000:]
                self._log(
                    f"[scheduler] {adapter.name} discovery recorded "
                    f"{new_rows} changed trends from {covered} available and {added} new seeds"
                )
                from services.provider_telemetry import record_provider_attempt
                record_provider_attempt(
                    provider=adapter.name,
                    operation="discovery",
                    status="completed" if new_rows else "unchanged" if signals else "no_data",
                    started_at=started_at,
                    keyword_count=len(signals),
                    row_count=new_rows,
                    metadata={
                        "new_seeds": added,
                        "domain": domain,
                        "provider_rows": len(signals),
                        "covered_rows": covered,
                        "new_rows": new_rows,
                        "duplicate_rows": max(0, covered - new_rows),
                        "fingerprints": known_ordered[-2000:],
                    },
                )
                self._external_discovery_by_source[adapter.name] = now.isoformat()
            except Exception as exc:
                name = adapter.name if adapter is not None else adapter_factory.__name__
                self._log(f"[scheduler] {name} discovery failed: {exc}")
                from services.provider_telemetry import record_provider_attempt
                record_provider_attempt(
                    provider=name,
                    operation="discovery",
                    status="failed",
                    started_at=started_at,
                    keyword_count=0,
                    row_count=0,
                    error=str(exc),
                )
                if adapter is not None:
                    self._external_discovery_by_source[adapter.name] = now.isoformat()

        self._last_external_discovery_at = now.isoformat()
        self._save_state(running=self.is_running(), paused=self.is_paused())
        return total_added

    def _scan_interval_seconds(self) -> float:
        configured = RATES.get(self._mode, 90)
        if self._mode != "continuous" or "etsy_open_api" not in _scheduler_research_adapters():
            return float(configured)
        try:
            from adapters.research.etsy_open_api import recommended_request_interval_seconds
            provider_interval = recommended_request_interval_seconds()
            if provider_interval is not None:
                return provider_interval
        except Exception:
            pass
        return float(configured)

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
            "last_external_discovery_at": self._last_external_discovery_at,
            "external_discovery_by_source": self._external_discovery_by_source,
            "external_discovery_fingerprints": self._external_discovery_fingerprints,
            "last_updated":     datetime.utcnow().isoformat(),
        }
        temporary = STATE_FILE.with_name(f".{STATE_FILE.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
        temporary.replace(STATE_FILE)

    def _load_state(self) -> None:
        if STATE_FILE.exists():
            try:
                state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                self._mode = state.get("mode", self._mode)
                self._batch_size = state.get("batch_size", self._batch_size)
                self._stale_days = state.get("stale_days", self._stale_days)
                self._last_external_discovery_at = state.get("last_external_discovery_at")
                source_state = state.get("external_discovery_by_source")
                if isinstance(source_state, dict):
                    self._external_discovery_by_source = {
                        str(key): str(value) for key, value in source_state.items() if value
                    }
                fingerprints = state.get("external_discovery_fingerprints")
                if isinstance(fingerprints, dict):
                    self._external_discovery_fingerprints = {
                        str(source): [str(value) for value in values[-2000:]]
                        for source, values in fingerprints.items()
                        if isinstance(values, list)
                    }
            except Exception:
                pass

    def _hydrate_external_discovery_fingerprints(self) -> None:
        """Restore feed deduplication state from durable provider telemetry."""
        try:
            from services.provider_telemetry import get_provider_states
            for provider, state in get_provider_states().items():
                metadata = state.get("metadata") if isinstance(state, dict) else None
                fingerprints = metadata.get("fingerprints") if isinstance(metadata, dict) else None
                if not isinstance(fingerprints, list):
                    continue
                existing = self._external_discovery_fingerprints.get(provider, [])
                merged = list(dict.fromkeys([
                    *(str(value) for value in existing if value),
                    *(str(value) for value in fingerprints if value),
                ]))
                self._external_discovery_fingerprints[provider] = merged[-2000:]
        except Exception as exc:
            self._log(f"[scheduler] Durable discovery dedup hydration failed: {exc}")


# ── Singleton accessor (one scheduler per app process) ────────────────────────

_instance: Optional[AutonomousScheduler] = None


def get_scheduler(**kwargs) -> AutonomousScheduler:
    global _instance
    if _instance is None:
        _instance = AutonomousScheduler(**kwargs)
    return _instance


def _report_has_market_data(report) -> bool:
    if hasattr(report, "__dataclass_fields__"):
        import dataclasses
        data = dataclasses.asdict(report)
    else:
        data = dict(report)
    for row in data.get("keyword_search_data", []) or []:
        if (
            _is_positive_observation(row.get("sampled_listing_count"))
            or _is_positive_observation(row.get("avg_price_usd"))
            or _is_positive_observation(row.get("total_listing_count"))
        ):
            return True
    return False


def _is_positive_observation(value) -> bool:
    try:
        return value is not None and float(value) > 0
    except (TypeError, ValueError):
        return False


def _scheduler_research_adapters() -> list[str]:
    raw = os.environ.get(
        "SCHEDULER_RESEARCH_ADAPTERS",
        "etsy_open_api,google_suggest,google_trends,pinterest_trends,reddit_etsy",
    )
    names = [name.strip() for name in raw.split(",") if name.strip()]
    return names or ["etsy_open_api", "google_suggest", "google_trends"]


def _primary_scheduler_adapters() -> list[str]:
    """Sources safe to run inline with the quota-controlled Etsy lane."""
    secondary = {"google_trends", "pinterest_trends", "reddit_etsy"}
    return [name for name in _scheduler_research_adapters() if name not in secondary]


def _remaining_interval_seconds(target_seconds: float, elapsed_seconds: float) -> float:
    """Return only the unspent part of a provider-derived scan interval."""
    return max(0.0, float(target_seconds) - max(0.0, float(elapsed_seconds)))


def _signal_fingerprint(provider: str, signal) -> str:
    """Hash provider content while ignoring collector-generated timestamps."""
    if hasattr(signal, "__dataclass_fields__"):
        import dataclasses
        payload = dataclasses.asdict(signal)
    else:
        payload = dict(signal)
    payload.pop("observed_at", None)
    raw = json.dumps(
        {"provider": provider, "signal": payload},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
