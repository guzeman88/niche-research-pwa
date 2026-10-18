"""App-owned discovery refresh; process lease survives parallel API requests."""
import asyncio
from contextlib import closing
from datetime import timedelta
import json
import os

from services import selling_discovery as discovery
from services.app_keyword_feed import supervisor_lock


def cycle():
    with supervisor_lock(discovery.root() / 'refresh.lock') as acquired:
        if not acquired:
            return {'status': 'already_running'}
        with closing(discovery.connect()) as con:
            con.execute("UPDATE runs SET status='interrupted',completed_at=? WHERE status='running'", (discovery.now().isoformat(),))
            identity = con.execute("INSERT INTO runs(started_at,status) VALUES(?,'running')", (discovery.now().isoformat(),)).lastrowid
            con.commit()
        result = {'status': 'needs_attention', 'scanned': 0, 'skipped': 0, 'requests': 0}
        try:
            result.update(discovery.sync_catalog())
            # One live source pass per 15 minutes at most. Local ingestion may
            # catch up every minute, without adding marketplace requests.
            with closing(discovery.connect()) as con:
                saved = con.execute("SELECT value FROM control WHERE name='source_pass_after'").fetchone()
                due = not saved or discovery._time(saved[0]) <= discovery.now()
                if due:
                    con.execute('INSERT OR REPLACE INTO control VALUES(?,?)', ('source_pass_after', (discovery.now() + timedelta(minutes=15)).isoformat()))
                    con.commit()
            if due:
                from services.selling_discovery_sources import refresh_sources
                source = refresh_sources(identity)
                result['requests'] = source['requests']
                result['source_status'] = source['status']
                with closing(discovery.connect()) as con:
                    con.execute('INSERT OR REPLACE INTO control VALUES(?,?)', ('source_status', source['status']))
                    if source['status'] in ('native_collector_running', 'collection_paused'):
                        # No source request was made. Retry locally next minute so a
                        # busy native worker cannot postpone every opportunity forever.
                        con.execute('INSERT OR REPLACE INTO control VALUES(?,?)', ('source_pass_after', (discovery.now() + timedelta(minutes=1)).isoformat()))
                    con.commit()
            discovery.sync_watchlist()
        except Exception as exc:
            result['status'] = 'needs_attention'
            # Keep error classes observable without paths, credentials or bodies.
            result['error'] = type(exc).__name__
        with closing(discovery.connect()) as con:
            con.execute('UPDATE runs SET completed_at=?,status=?,scanned=?,skipped=?,requests=? WHERE id=?',
                (discovery.now().isoformat(), result['status'], result['scanned'], result['skipped'], result['requests'], identity))
            con.execute('INSERT OR REPLACE INTO control VALUES(?,?)', ('last_result', json.dumps(result)))
            con.commit()
        return result


class Worker:
    def __init__(self):
        self.task = None

    async def run(self):
        await asyncio.sleep(3)
        while True:
            await asyncio.to_thread(cycle)
            await asyncio.sleep(60)

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
    return Worker() if os.environ.get('APP_KEYWORD_FEED_ENABLED') == '1' else None
