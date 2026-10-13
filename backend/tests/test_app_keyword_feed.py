"""App cadence, exclusive ownership and restart/pause preservation boundaries."""
import asyncio
import json
from services import app_keyword_feed as feed


def installed(tmp_path):
    code = tmp_path / 'versions/proof'
    (code / 'scripts').mkdir(parents=True)
    (code / 'scripts/keyword_feed.py').write_text('')
    python = tmp_path / 'venv/Scripts/python.exe'
    python.parent.mkdir(parents=True); python.write_text('')
    (tmp_path / 'installation.json').write_text(json.dumps({
        'code_root': str(code), 'python': str(python), 'schedule_minutes': 15,
        'scheduler_owner': 'etgen_backend'}))


def test_app_tick_uses_start_to_start_cadence_and_keeps_pause_visible(tmp_path):
    installed(tmp_path)
    clock = [0]; calls = []
    async def runner(*args):
        calls.append(args)
        return 'paused' if len(calls) == 1 else 'completed'
    worker = feed.AppKeywordFeed(tmp_path, runner, lambda: clock[0])
    asyncio.run(worker.tick())
    assert worker.state['last_outcome'] == 'paused'
    clock[0] = 899; asyncio.run(worker.tick())
    assert len(calls) == 1
    clock[0] = 900; asyncio.run(worker.tick())
    assert len(calls) == 2
    assert worker.state['last_outcome'] == 'completed'


def test_concurrent_ticks_cannot_start_two_collectors(tmp_path):
    installed(tmp_path)
    calls = []
    async def scenario():
        started, finish = asyncio.Event(), asyncio.Event()
        async def runner(*_args):
            calls.append(1); started.set(); await finish.wait()
            return 'completed'
        worker = feed.AppKeywordFeed(tmp_path, runner, lambda: 0)
        first = asyncio.create_task(worker.tick())
        await started.wait(); await worker.tick()
        finish.set(); await first
    asyncio.run(scenario())
    assert calls == [1]


def test_supervisor_lease_rejects_other_owner_and_releases_after_exit(tmp_path):
    path = tmp_path / 'supervisor.lock'
    with feed.supervisor_lock(path) as acquired:
        assert acquired
        with feed.supervisor_lock(path) as other:
            assert not other
    with feed.supervisor_lock(path) as recovered:
        assert recovered


def test_invalid_installation_is_bounded_without_executing_or_exposing_paths(tmp_path):
    installed(tmp_path)
    value = json.loads((tmp_path / 'installation.json').read_text())
    value['code_root'] = str(tmp_path / 'untrusted-private')
    (tmp_path / 'installation.json').write_text(json.dumps(value))
    clock = [0]; calls = []
    async def runner(*args):
        calls.append(args)
    worker = feed.AppKeywordFeed(tmp_path, runner, lambda: clock[0])
    asyncio.run(worker.tick())
    assert worker.state['last_outcome'] == 'ValueError'
    assert 'private' not in json.dumps(worker.state)
    assert worker.next_tick == 900 and not calls


def test_default_off_and_mutually_exclusive_with_legacy_scanner(monkeypatch):
    import pytest
    monkeypatch.delenv('APP_KEYWORD_FEED_ENABLED', raising=False)
    assert feed.configured_worker() is None
    monkeypatch.setenv('APP_KEYWORD_FEED_ENABLED', '1')
    monkeypatch.setenv('AUTO_START_SCHEDULER', '1')
    with pytest.raises(ValueError, match='ChooseOneCollectionScheduler'):
        feed.configured_worker()


def test_old_external_scheduler_installation_cannot_be_claimed_by_app(tmp_path):
    import pytest
    installed(tmp_path)
    value = json.loads((tmp_path / 'installation.json').read_text())
    value.pop('scheduler_owner')
    (tmp_path / 'installation.json').write_text(json.dumps(value))
    with pytest.raises(ValueError, match='FeedSchedulerOwnershipMismatch'):
        feed.installation(tmp_path)


def test_shutdown_leaves_already_committing_cycle_intact(tmp_path):
    installed(tmp_path)
    async def scenario():
        started = asyncio.Event(); writes = []
        async def runner(*_args):
            # Simulate an independently committing packaged collector process.
            async def commit():
                await asyncio.sleep(.02); writes.append('preserved')
            asyncio.create_task(commit()); started.set()
            await asyncio.sleep(30)
        worker = feed.AppKeywordFeed(tmp_path, runner, lambda: 0)
        worker.task = asyncio.create_task(worker.tick())
        await started.wait(); await worker.stop()
        await asyncio.sleep(.03)
        assert writes == ['preserved']
    asyncio.run(scenario())


def test_real_child_survives_supervisor_cancellation(tmp_path):
    import sys
    code = tmp_path / 'code/scripts'; code.mkdir(parents=True)
    (code / 'keyword_feed.py').write_text(
        "import pathlib,time,json\n"
        "pathlib.Path('started').write_text('yes')\n"
        "time.sleep(.2)\n"
        "pathlib.Path('committed').write_text('preserved')\n"
        "print(json.dumps({'status':'completed'}))\n")
    async def scenario():
        task = asyncio.create_task(feed.collect(tmp_path, {'python': sys.executable, 'code_root': str(code.parent)}))
        for _ in range(200):
            if (code.parent / 'started').exists():
                break
            await asyncio.sleep(.01)
        assert (code.parent / 'started').exists()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        for _ in range(200):
            if (code.parent / 'committed').exists():
                break
            await asyncio.sleep(.01)
        assert (code.parent / 'committed').read_text() == 'preserved'
    asyncio.run(scenario())
