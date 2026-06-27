"""Scheduler router — control the autonomous keyword scanner."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from models.schemas import SchedulerStatus, SchedulerAction
from services.scheduler_service import (
    start_scheduler, stop_scheduler, pause_scheduler,
    resume_scheduler, set_scheduler_mode, set_scheduler_batch_size,
    scheduler_status,
)

router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])


@router.get("/status", response_model=SchedulerStatus)
def status():
    """Get current scheduler status."""
    s = scheduler_status()
    return SchedulerStatus(
        running=s.get("running", False),
        paused=s.get("paused", False),
        mode=s.get("mode", "performance"),
        batch_size=s.get("batch_size", 5),
        keywords_scanned=s.get("keywords_scanned", 0),
        new_seeds_found=s.get("new_seeds_found", 0),
        current_keyword=s.get("current_keyword"),
        started_at=s.get("started_at"),
        interval_s=s.get("interval_s", 30),
        errors=s.get("errors", []),
    )


@router.post("/start")
def start(action: SchedulerAction = SchedulerAction()):
    """Start the scheduler."""
    result = start_scheduler(
        mode=action.mode or "performance",
        batch_size=action.batch_size or 5,
    )
    return result


@router.post("/stop")
def stop():
    """Stop the scheduler."""
    return stop_scheduler()


@router.post("/pause")
def pause():
    """Pause the scheduler."""
    return pause_scheduler()


@router.post("/resume")
def resume():
    """Resume the scheduler."""
    return resume_scheduler()


@router.post("/mode")
def change_mode(action: SchedulerAction):
    """Change scheduler mode."""
    if not action.mode:
        raise HTTPException(status_code=400, detail="mode is required")
    return set_scheduler_mode(action.mode)


@router.post("/batch-size")
def change_batch_size(action: SchedulerAction):
    """Change scheduler batch size."""
    if action.batch_size is None:
        raise HTTPException(status_code=400, detail="batch_size is required")
    return set_scheduler_batch_size(action.batch_size)


@router.get("/history")
def history(limit: int = 20):
    """Get scheduler run history."""
    from pipeline import keyword_database as kdb
    kdb.init_db()
    return kdb.get_scheduler_history(limit=limit)
