"""
Scheduler service — wraps AutonomousScheduler as a managed background service.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Callable

from services.research_service import _emit

_scheduler = None
DEFAULT_SCHEDULER_MODE = "performance"
DEFAULT_BATCH_SIZE = 5


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
            mode=DEFAULT_SCHEDULER_MODE,
            batch_size=DEFAULT_BATCH_SIZE,
            log_fn=_scheduler_log,
        )
    return _scheduler


def _apply_scheduler_settings(s, mode: str, batch_size: int) -> bool:
    changed = False
    status = s.status()
    if mode and status.get("mode") != mode:
        s.set_mode(mode)
        changed = True
    if batch_size and status.get("batch_size") != batch_size:
        s.set_batch_size(batch_size)
        changed = True
    return changed


def start_scheduler(mode: str = DEFAULT_SCHEDULER_MODE, batch_size: int = DEFAULT_BATCH_SIZE) -> dict:
    s = get_scheduler()
    if s.is_running():
        changed = _apply_scheduler_settings(s, mode, batch_size)
        if s.is_paused():
            s.resume()
            return {"status": "resumed", "message": "Scheduler was paused and is now running", **s.status()}
        if changed:
            return {"status": "retuned", "message": "Scheduler settings updated while running", **s.status()}
        return {"status": "already_running", "message": "Scheduler is already running", **s.status()}

    s.set_mode(mode)
    s.set_batch_size(batch_size)
    s.start()
    return s.status()


def ensure_scheduler_running(mode: str = DEFAULT_SCHEDULER_MODE, batch_size: int = DEFAULT_BATCH_SIZE) -> dict:
    """Idempotently keep the scanner alive in the expected continuous mode."""
    s = get_scheduler()
    if not s.is_running():
        return start_scheduler(mode=mode, batch_size=batch_size)
    changed = _apply_scheduler_settings(s, mode, batch_size)
    if s.is_paused():
        s.resume()
        return {"status": "resumed", "message": "Scheduler was paused and is now running", **s.status()}
    if changed:
        return {"status": "retuned", "message": "Scheduler settings updated while running", **s.status()}
    return {"status": "running", "message": "Scheduler is running", **s.status()}


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
