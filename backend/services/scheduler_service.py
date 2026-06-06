"""
Scheduler service — wraps AutonomousScheduler as a managed background service.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Callable

from services.research_service import _emit

_scheduler = None


def _scheduler_log(msg: str) -> None:
    """Bridge scheduler logs to SSE."""
    _emit("log", {
        "level": "info",
        "message": msg,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    print(msg, flush=True)


def get_scheduler():
    """Get or create the singleton AutonomousScheduler."""
    global _scheduler
    if _scheduler is None:
        from pipeline.autonomous_scheduler import AutonomousScheduler
        _scheduler = AutonomousScheduler(
            store_slug="__global__",
            mode="continuous",
            batch_size=5,
            log_fn=_scheduler_log,
        )
    return _scheduler


def start_scheduler(mode: str = "continuous", batch_size: int = 5) -> dict:
    s = get_scheduler()
    if s.is_running():
        return {"status": "already_running", "message": "Scheduler is already running"}

    s.set_mode(mode)
    s.set_batch_size(batch_size)
    s.start()
    return s.status()


def stop_scheduler() -> dict:
    s = get_scheduler()
    s.stop()
    return {"status": "stopped"}


def pause_scheduler() -> dict:
    s = get_scheduler()
    s.pause()
    return s.status()


def resume_scheduler() -> dict:
    s = get_scheduler()
    s.resume()
    return s.status()


def set_scheduler_mode(mode: str) -> dict:
    s = get_scheduler()
    s.set_mode(mode)
    return s.status()


def set_scheduler_batch_size(n: int) -> dict:
    s = get_scheduler()
    s.set_batch_size(n)
    return s.status()


def scheduler_status() -> dict:
    s = get_scheduler()
    return s.status()
