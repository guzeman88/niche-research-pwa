"""
Research service — wraps niche_research.run() with SSE log broadcasting.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Callable

# SSE event queue (imported by routers/stream.py)
_sse_queue: asyncio.Queue | None = None


def get_sse_queue() -> asyncio.Queue:
    global _sse_queue
    if _sse_queue is None:
        _sse_queue = asyncio.Queue(maxsize=500)
    return _sse_queue


def _emit(event_type: str, data: dict) -> None:
    """Thread-safe push to the SSE queue."""
    q = _sse_queue
    if q is not None:
        try:
            q.put_nowait({"event": event_type, "data": data})
        except asyncio.QueueFull:
            pass


def _log_callback(msg: str) -> None:
    """Bridge from synchronous niche_research logging to SSE."""
    _emit("log", {
        "level": "info",
        "message": msg,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    # Also log to stdout for server console
    print(msg, flush=True)


def _progress_callback(stage: str, keyword: str = "", percent: float = 0.0) -> None:
    _emit("progress", {
        "stage": stage,
        "keyword": keyword,
        "percent": percent,
        "message": f"[{stage}] {keyword} ({percent:.0f}%)",
    })


def run_research_sync(
    keywords: list[str],
    store_slug: str = "__global__",
    skip_scraper: bool = False,
    adapter_names: list[str] | None = None,
) -> dict:
    """Run niche research synchronously in the current thread. Returns report dict."""
    from pipeline.stages.niche_research import run

    _emit("progress", {"stage": "starting", "keyword": keywords[0] if keywords else "",
                       "percent": 0.0, "message": f"Starting research for: {keywords}"})

    report = run(
        seed_keywords=keywords,
        store_slug=store_slug,
        log_fn=_log_callback,
        skip_scraper=skip_scraper,
        adapter_names=adapter_names,
    )

    # Save to keyword database
    try:
        from pipeline import keyword_database as kdb
        kdb.init_db()
        for kw in keywords:
            kdb.save_scan(kw, report)
    except Exception as e:
        _log_callback(f"[research_service] DB save error: {e}")

    _emit("complete", {
        "report_id": report.report_id,
        "opportunity_score": report.opportunity_score,
        "demand_score": report.demand_score,
        "competition_score": report.competition_score,
        "margin_score": report.margin_score,
        "trend_velocity_score": report.trend_velocity_score,
    })

    # Convert dataclass to dict for JSON response
    from dataclasses import asdict
    return asdict(report)


# Track active runs
_active_runs: dict[str, dict] = {}


def start_research_background(
    keywords: list[str],
    store_slug: str = "__global__",
    skip_scraper: bool = False,
    adapter_names: list[str] | None = None,
) -> str:
    """Start research in a background thread. Returns run_id."""
    run_id = f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

    _active_runs[run_id] = {"status": "running", "keywords": keywords, "store_slug": store_slug}

    def _worker():
        try:
            result = run_research_sync(
                keywords=keywords,
                store_slug=store_slug,
                skip_scraper=skip_scraper,
                adapter_names=adapter_names,
            )
            _active_runs[run_id] = {"status": "completed", "result": result}
        except Exception as e:
            _emit("log", {
                "level": "error",
                "message": f"Research failed: {e}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            _active_runs[run_id] = {"status": "failed", "error": str(e)}

    t = threading.Thread(target=_worker, daemon=True, name=f"research-{run_id}")
    t.start()
    return run_id


def get_run_status(run_id: str) -> dict | None:
    return _active_runs.get(run_id)
