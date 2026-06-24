"""
Niche Scanner System Tray App
Runs silently in the background. Click the tray icon for status and logs.
"""
import os, sys, subprocess, threading, time, webbrowser, shutil
from datetime import datetime
from pathlib import Path
import json

PWA_DIR = Path(__file__).resolve().parents[1]
BACKEND = PWA_DIR / "backend"
LOG_FILE = PWA_DIR / "scanner.log"
PWA_URL = "https://etsy-niches.netlify.app"

_procs = []
_log_lines = []

def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    _log_lines.append(line)
    if len(_log_lines) > 500:
        _log_lines.pop(0)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except: pass

def start_backend():
    log("Starting backend API...")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(BACKEND)
    p = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=str(BACKEND), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    _procs.append(("Backend API", p))
    log(f"Backend started (PID {p.pid})")
    time.sleep(6)

def start_scheduler():
    log("Starting scheduler...")
    import httpx
    for i in range(10):
        try:
            r = httpx.post("http://localhost:8000/api/scheduler/start",
                          json={"mode": "burst", "batch_size": 5}, timeout=5)
            if r.status_code == 200:
                log(f"Scheduler started: {r.json().get('running', False)}")
                return
        except Exception:
            time.sleep(2)
    log("Scheduler failed to start")

def start_tunnel():
    log("Starting Cloudflare tunnel...")
    cloudflared = r"C:\Program Files (x86)\cloudflared\cloudflared.exe"
    if not os.path.exists(cloudflared):
        log("cloudflared not found — tunnel skipped")
        return
    p = subprocess.Popen(
        [cloudflared, "tunnel", "--url", "http://localhost:8000", "--no-autoupdate"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    _procs.append(("Tunnel", p))
    log(f"Tunnel started (PID {p.pid})")
    time.sleep(4)

def refresh_pwa_data():
    """Rebuild static data and deploy to Netlify."""
    pwa_dir = PWA_DIR
    node = shutil.which("node")
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    npx = shutil.which("npx.cmd") or shutil.which("npx")
    try:
        missing = [name for name, exe in (("node", node), ("npm", npm), ("npx", npx)) if not exe]
        if missing:
            log(f"PWA refresh skipped: missing executable(s): {', '.join(missing)}")
            return

        log("Refreshing PWA data...")
        data_result = subprocess.run(
            [node, "scripts/build-data.cjs"],
            cwd=str(pwa_dir), capture_output=True, timeout=60, creationflags=subprocess.CREATE_NO_WINDOW,
            env={**os.environ, "VITE_API_URL": "http://localhost:8000"},
        )
        if data_result.returncode != 0:
            log(f"PWA data build failed: {(data_result.stderr or data_result.stdout).decode(errors='replace')[:300]}")
            return

        build_result = subprocess.run(
            [npm, "run", "build"],
            cwd=str(pwa_dir), capture_output=True, timeout=60, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if build_result.returncode != 0:
            log(f"PWA frontend build failed: {(build_result.stderr or build_result.stdout).decode(errors='replace')[:300]}")
            return

        deploy_result = subprocess.run(
            [npx, "netlify", "deploy", "--prod", "--dir=dist"],
            cwd=str(pwa_dir), capture_output=True, timeout=120,
        )
        if deploy_result.returncode != 0:
            log(f"PWA deploy failed: {(deploy_result.stderr or deploy_result.stdout).decode(errors='replace')[:300]}")
            return
        log("PWA data refreshed")
    except Exception as e:
        log(f"PWA refresh failed: {e}")

def _refresh_loop():
    while True:
        time.sleep(300)  # every 5 minutes
        try:
            refresh_pwa_data()
        except Exception:
            pass

def start_all():
    log("=" * 40)
    log("Niche Scanner starting up...")
    start_backend()
    start_scheduler()
    start_tunnel()
    threading.Thread(target=_refresh_loop, daemon=True).start()
    log("All services started. Scanner + auto-refresh running.")
    log("=" * 40)

def stop_all():
    log("Shutting down...")
    for name, p in _procs:
        try:
            p.terminate()
            p.wait(timeout=5)
            log(f"Stopped: {name}")
        except Exception as e:
            log(f"Stop {name} error: {e}")
    _procs.clear()
    log("All services stopped.")

def get_status() -> str:
    try:
        import httpx
        r = httpx.get("http://localhost:8000/api/scheduler/status", timeout=5)
        if r.status_code == 200:
            d = r.json()
            return f"Scanner: {'Running' if d.get('running') else 'Stopped'} | "
        r2 = httpx.get("http://localhost:8000/api/stats", timeout=5)
        if r2.status_code == 200:
            s = r2.json()
            return f"Scanner: Running | Keywords: {s.get('total_seeds',0)} | Scanned: {s.get('scanned',0)} | Coverage: {s.get('coverage_pct',0):.0f}%"
    except:
        return "Scanner: Offline"
    return "Scanner: Unknown"

# ── System Tray ──────────────────────────────────────────────────────────

def make_icon():
    """Create a simple 16x16 icon."""
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Circle background
    draw.ellipse([4, 4, 60, 60], fill=(99, 102, 241, 255))
    # Magnifying glass
    draw.ellipse([18, 18, 42, 42], outline=(255,255,255,220), width=3)
    draw.line([36, 36, 52, 52], fill=(255,255,255,220), width=3)
    return img

def setup_tray():
    import pystray

    def on_open(icon, item):
        webbrowser.open(PWA_URL)

    def on_status(icon, item):
        icon.notify(get_status(), "Scanner Status")

    def on_logs(icon, item):
        # Show last 20 log lines in a notification
        recent = "\n".join(_log_lines[-15:]) if _log_lines else "No logs yet"
        icon.notify(recent[:500], "Recent Logs")

    def on_restart(icon, item):
        stop_all()
        threading.Thread(target=start_all, daemon=True).start()
        icon.notify("Scanner restarted", "Info")

    def on_exit(icon, item):
        stop_all()
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("Open PWA", on_open, default=True),
        pystray.MenuItem("Status", on_status),
        pystray.MenuItem("Recent Logs", on_logs),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Restart Scanner", on_restart),
        pystray.MenuItem("Exit", on_exit),
    )

    icon = pystray.Icon("niche-scanner", make_icon(), "Niche Scanner", menu)
    return icon

def main():
    # Start services in background
    threading.Thread(target=start_all, daemon=True).start()
    # Start system tray
    icon = setup_tray()
    icon.run()

if __name__ == "__main__":
    main()
