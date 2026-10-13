"""App-owned cadence for the packaged EtGen collector; no external scheduler."""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import time
import uuid


@contextmanager
def supervisor_lock(path):
    """Only one API process supervises collection; crash releases the lease."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as stream:
        if os.fstat(stream.fileno()).st_size == 0:
            stream.write(b'0'); stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            yield False
            return
        try:
            yield True
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def installation(root):
    value = json.loads((root / 'installation.json').read_text(encoding='utf-8'))
    if value.get('scheduler_owner') != 'etgen_backend':
        raise ValueError('FeedSchedulerOwnershipMismatch')
    code = Path(value['code_root']).resolve()
    python = Path(value['python']).resolve()
    if not code.is_relative_to((root / 'versions').resolve()) or python != (root / 'venv/Scripts/python.exe').resolve():
        raise ValueError('UnexpectedFeedInstallation')
    if not (code / 'scripts/keyword_feed.py').is_file() or not python.is_file():
        raise ValueError('FeedInstallationMissing')
    minutes = value.get('schedule_minutes', 15)
    if type(minutes) is not int or not 15 <= minutes <= 60:
        raise ValueError('InvalidFeedCadence')
    return value, minutes


async def collect(root, metadata):
    """Run the existing app module; its durable worker lock/quotas remain authoritative."""
    directory = root / 'data/logs'
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / ('app-cycle-' + uuid.uuid4().hex + '.log')
    with path.open('xb') as log:
        process = subprocess.Popen(
            [metadata['python'], '-m', 'scripts.keyword_feed', 'run', '--root', str(root)],
            cwd=metadata['code_root'], stdout=log, stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        # Cancellation leaves a committing cycle intact. Its OS lock prevents
        # duplicate work across app restarts; the next app cycle reconciles it.
        while process.poll() is None:
            await asyncio.sleep(1)
        code = process.returncode
    if code or path.stat().st_size > 2_000_000:
        return 'needs_attention'
    result = json.loads(path.read_text(encoding='utf-8'))
    return result.get('status', 'needs_attention')


class AppKeywordFeed:
    def __init__(self, root, runner=collect, clock=time.monotonic):
        self.root = Path(root).resolve()
        self.runner = runner
        self.clock = clock
        self.next_tick = 0.0
        self.task = None
        self.state = {'owner': 'etgen_backend', 'enabled': True, 'running': False,
                      'interval_minutes': 15, 'last_outcome': 'starting'}

    async def tick(self):
        if self.clock() < self.next_tick or self.state['running']:
            return
        # Bound retries even if metadata is missing or malformed. Errors are
        # classified, never copied with local paths/credentials into health.
        self.next_tick = self.clock() + 900
        self.state['last_started'] = datetime.now(timezone.utc).isoformat()
        self.state['running'] = True
        try:
            metadata, minutes = installation(self.root)
            self.next_tick = self.clock() + minutes * 60
            self.state['interval_minutes'] = minutes
            result = await self.runner(self.root, metadata)
            self.state['last_outcome'] = result if result in {'completed', 'needs_attention', 'paused', 'already_running'} else 'needs_attention'
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.state['last_outcome'] = type(exc).__name__
        finally:
            self.state['running'] = False
            self.state['last_completed'] = datetime.now(timezone.utc).isoformat()

    async def run(self):
        with supervisor_lock(self.root / 'app-supervisor.lock') as acquired:
            if not acquired:
                self.state['last_outcome'] = 'another_app_process_owns_collection'
                return
            # The API must be serving before the collector requests its private
            # validation overview. This also keeps startup itself nonblocking.
            await asyncio.sleep(5)
            while True:
                await self.tick()
                await asyncio.sleep(max(1, self.next_tick - self.clock()))

    def start(self):
        if not self.task or self.task.done():
            self.task = asyncio.create_task(self.run())

    async def stop(self):
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass


def configured_worker():
    # Default off prevents hosted or unrelated API installations from creating
    # a second collector. The local app installer explicitly enables this owner.
    if os.environ.get('APP_KEYWORD_FEED_ENABLED', '0') != '1':
        return None
    if os.environ.get('AUTO_START_SCHEDULER', '0') == '1':
        raise ValueError('ChooseOneCollectionScheduler')
    return AppKeywordFeed(Path(os.environ.get('APP_KEYWORD_FEED_ROOT') or Path.home() / 'EtGen/keyword-feed'))
