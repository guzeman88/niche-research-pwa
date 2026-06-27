"""Scheduler daemon — keeps running until killed. Start with: python scripts/run-scheduler.py"""
import sys, os, time, signal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
os.chdir(os.path.join(os.path.dirname(__file__), '..', 'backend'))

from services.scheduler_service import start_scheduler

MODE = os.environ.get('SCHEDULER_MODE', 'performance')
BATCH = int(os.environ.get('SCHEDULER_BATCH', '5'))

print(f'[daemon] Starting scheduler: mode={MODE}, batch={BATCH}')
result = start_scheduler(MODE, BATCH)
print(f'[daemon] Scheduler running={result["running"]} paused={result["paused"]}')

running = True
def shutdown(sig, frame):
    global running
    running = False
    print('[daemon] Shutting down...')

signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)

while running:
    time.sleep(30)

print('[daemon] Stopped.')
