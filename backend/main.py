"""
Niche Research PWA — FastAPI Backend
Serves REST API + SSE for the niche research Progressive Web App.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure backend/ is on sys.path so all internal imports resolve
BACKEND_DIR = Path(__file__).parent.resolve()
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import load_settings, WORKSPACE
from routers import research, keywords, gaps, scheduler, stats, settings, stream, export

# ── App factory ─────────────────────────────────────────────────────────────

app = FastAPI(
    title="Niche Research PWA",
    description="Multi-source Etsy niche intelligence — REST API backend",
    version="1.0.0",
)

# CORS — allow all origins in development; restrict in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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


# ── Startup ─────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    """Initialize database and load seed library on startup."""
    from pipeline import keyword_database as kdb
    kdb.init_db()
    count = kdb.load_seeds_from_library()
    print(f"[startup] Keyword DB initialized. {count} library seeds loaded.")


@app.on_event("shutdown")
async def shutdown():
    """Gracefully stop the scheduler if running."""
    try:
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
