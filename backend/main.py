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
from routers import research, keywords, gaps, scheduler, stats, settings, stream, export, stores, store_ideas

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
app.include_router(stores.router)
app.include_router(store_ideas.router)


# ── Startup ─────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    """Initialize database, seed from seed_data/ on first run, and load seed library."""
    import shutil, os
    from pathlib import Path

    seed_dir = BACKEND_DIR / "seed_data"
    workspace_dir = BACKEND_DIR / "workspace"
    db_path = workspace_dir / "_keyword_db" / "keywords.sqlite"

    print(f"[startup] BACKEND_DIR={BACKEND_DIR}")
    print(f"[startup] seed_dir exists={seed_dir.exists()}")
    print(f"[startup] db_path exists={db_path.exists()}")

    # Seed if: seed_data exists AND (no DB yet OR forced OR seed_data DB is newer)
    force_reseed = os.environ.get("FORCE_RESEED", "") == "1"
    needs_seed = False
    if seed_dir.exists():
        seed_db = seed_dir / "_keyword_db" / "keywords.sqlite"
        if force_reseed:
            print("[startup] FORCE_RESEED=1 — re-seeding")
            shutil.rmtree(workspace_dir, ignore_errors=True)
            needs_seed = True
        elif not db_path.exists():
            needs_seed = True
        elif seed_db.exists() and seed_db.stat().st_size > db_path.stat().st_size:
            # Seed data has been updated — replace workspace with fresh seed
            print(f"[startup] seed_data DB is newer ({seed_db.stat().st_size} > {db_path.stat().st_size}) — re-seeding")
            shutil.rmtree(workspace_dir, ignore_errors=True)
            needs_seed = True
        else:
            import sqlite3
            try:
                con = sqlite3.connect(str(db_path))
                scan_count = con.execute("SELECT COUNT(*) FROM scans").fetchone()[0]
                con.close()
                if scan_count == 0:
                    print(f"[startup] DB exists but has 0 scans — re-seeding")
                    shutil.rmtree(workspace_dir, ignore_errors=True)
                    needs_seed = True
                else:
                    print(f"[startup] DB has {scan_count} scans — skipping seed")
            except Exception:
                shutil.rmtree(workspace_dir, ignore_errors=True)
                needs_seed = True

    if needs_seed:
        print("[startup] Seeding workspace from seed_data/ ...")
        workspace_dir.mkdir(parents=True, exist_ok=True)
        for item in seed_dir.iterdir():
            dest = workspace_dir / item.name
            if item.is_dir():
                if not dest.exists():
                    shutil.copytree(item, dest)
            else:
                if not dest.exists():
                    shutil.copy2(item, dest)
        total_files = len(list(workspace_dir.rglob("*")))
        print(f"[startup] Seeded {total_files} files from seed_data/")

    from pipeline import keyword_database as kdb
    kdb.init_db()
    count = kdb.load_seeds_from_library()
    print(f"[startup] Keyword DB initialized. {count} library seeds loaded.")

    auto_start_scheduler = os.environ.get("AUTO_START_SCHEDULER", "1") != "0"
    if auto_start_scheduler:
        try:
            from services.scheduler_service import start_scheduler
            mode = os.environ.get("SCHEDULER_MODE", "continuous")
            batch_size = int(os.environ.get("SCHEDULER_BATCH_SIZE", "5"))
            result = start_scheduler(mode=mode, batch_size=batch_size)
            print(f"[startup] Scheduler auto-start result: {result}")
        except Exception as exc:
            print(f"[startup] Scheduler auto-start failed: {exc}", flush=True)
    else:
        print("[startup] Scheduler auto-start disabled by AUTO_START_SCHEDULER=0")


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
