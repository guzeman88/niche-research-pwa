"""
Niche Research PWA — FastAPI Backend
Serves REST API + SSE for the niche research Progressive Web App.
"""
from __future__ import annotations

import sys
import asyncio
from pathlib import Path

# Ensure backend/ is on sys.path so all internal imports resolve
BACKEND_DIR = Path(__file__).parent.resolve()
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi import FastAPI
from security import allowed_origins, protect_operator_api
from services.runtime_safety import safe_log, initialize_workspace
from fastapi.middleware.cors import CORSMiddleware

from config import load_settings, WORKSPACE
from routers import research, keywords, gaps, scheduler, stats, settings, stream, export, stores, store_ideas, designs, workspace

# ── App factory ─────────────────────────────────────────────────────────────

app = FastAPI(
    title="Niche Research PWA",
    description="Multi-source Etsy niche intelligence — REST API backend",
    version="1.0.0",
)

app.middleware("http")(protect_operator_api)

# Browser origins are restricted; private API actions also require authorization.
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|\[::1\])(:[0-9]+)?",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(research.router)
app.include_router(keywords.router)
app.include_router(gaps.router)
app.include_router(scheduler.router)
app.include_router(stats.router)
app.include_router(settings.router)
app.include_router(stream.router)
app.include_router(export.router)
app.include_router(stores.router)
app.include_router(store_ideas.router)
app.include_router(designs.router)
app.include_router(workspace.router)


async def _scheduler_watchdog() -> None:
    """Keep the background scanner alive for long-running local/API processes."""
    import os

    interval_s = max(15, int(os.environ.get("SCHEDULER_WATCHDOG_INTERVAL", "60")))
    mode = os.environ.get("SCHEDULER_MODE", "burst")
    batch_size = int(os.environ.get("SCHEDULER_BATCH_SIZE", "20"))
    while True:
        await asyncio.sleep(interval_s)
        try:
            from services.scheduler_service import ensure_scheduler_running
            result = ensure_scheduler_running(mode=mode, batch_size=batch_size)
            if result.get("status") not in {"running", "already_running"}:
                safe_log(f"[watchdog] Scheduler ensure result: {result}")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            safe_log(f"[watchdog] Scheduler ensure failed: {exc}")


# ── Startup ─────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    """Initialize database, seed from seed_data/ on first run, and load seed library."""
    import os
    from pipeline import keyword_database as kdb

    if os.environ.get("FORCE_RESEED") == "1":
        raise RuntimeError("FORCE_RESEED is disabled: preserve the workspace and restore an explicit backup instead.")
    initialize_workspace(kdb.DB_PATH.resolve(), kdb.SEED_DB_PATH.resolve())

    kdb.init_db()
    count = kdb.load_seeds_from_library()
    safe_log(f"[startup] Keyword DB initialized. {count} library seeds loaded.")

    auto_start_scheduler = os.environ.get("AUTO_START_SCHEDULER", "1") != "0"
    if auto_start_scheduler:
        try:
            from services.scheduler_service import start_scheduler
            mode = os.environ.get("SCHEDULER_MODE", "burst")
            batch_size = int(os.environ.get("SCHEDULER_BATCH_SIZE", "20"))
            result = start_scheduler(mode=mode, batch_size=batch_size)
            safe_log(f"[startup] Scheduler auto-start result: {result}")
            if not hasattr(app.state, "scheduler_watchdog_task"):
                app.state.scheduler_watchdog_task = asyncio.create_task(_scheduler_watchdog())
                safe_log("[startup] Scheduler watchdog started")
        except Exception as exc:
            safe_log(f"[startup] Scheduler auto-start failed: {exc}")
    else:
        safe_log("[startup] Scheduler auto-start disabled by AUTO_START_SCHEDULER=0")


@app.on_event("shutdown")
async def shutdown():
    """Gracefully stop the scheduler if running."""
    try:
        task = getattr(app.state, "scheduler_watchdog_task", None)
        if task:
            task.cancel()
        from services.scheduler_service import _scheduler
        if _scheduler and _scheduler.is_running():
            _scheduler.stop()
    except Exception:
        pass


# ── Root health check ───────────────────────────────────────────────────────

@app.get("/")
def root():
    return {
        "app": "Niche Research PWA",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/api/health")
def api_health():
    """Quick health check — returns OK if the server is up."""
    from pipeline import keyword_database as kdb
    db_ok = False
    try:
        kdb.init_db()
        stats = kdb.get_stats()
        db_ok = stats.get("total_seeds", 0) > 0
    except Exception:
        pass
    return {
        "status": "ok",
        "database": "connected" if db_ok else "empty",
    }
