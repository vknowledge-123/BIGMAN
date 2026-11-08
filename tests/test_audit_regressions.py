"""Requirement regressions found during the November integration audit."""
import threading
import asyncio
from types import SimpleNamespace

import pytest

from app.schemas import VolumeFilterSettings
from test_staged_scan import clock, engine, prepared
from test_daily_filter import SESSION, daily_data
from test_open_cross import close_history, opening
from test_integration_workflows import integration
from app.feed_lifecycle import close_market_feed


def test_open_cross_refetches_incomplete_raw_cache_after_toggle(engine, monkeypatch):
    state = prepared('A')
    engine._states = {'A': state}
    calls = []
    responses = [daily_data(), close_history()]
    def fetch(*args):
        calls.append(args)
        return responses.pop(0)
    monkeypatch.setattr(engine, '_historical_daily_with_retry', fetch)
    state.daily_filter = engine._fetch_daily_filter(object(), state.instrument, SESSION)
    engine._apply_opening_candidate('A', [opening()])
    engine.update_volume_filters(VolumeFilterSettings(today_open_cross=True))
    assert state.confirmation_status == 'unresolved'
    engine.evaluate_opening_candidates(only_pending=True)
    assert len(calls) == 2
    assert state.possible_candidate
    assert state.daily_filter['five_day_highest_close'] == 199
    assert state.confirmation_status == 'confirmed'


def test_stop_endpoint_is_responsive_when_sdk_disconnect_blocks(integration):
    ctx = integration
    entered, release, returned = threading.Event(), threading.Event(), threading.Event()
    class BlockedFeed:
        def close_connection(self):
            entered.set()
            release.wait(5)
    old = BlockedFeed()
    ctx.engine._feed = old
    ctx.engine._running = ctx.engine._connected = True
    responses = []
    def stop():
        responses.append(ctx.http.post('/api/stop'))
        returned.set()
    worker = threading.Thread(target=stop)
    worker.start()
    try:
        assert entered.wait(1)
        assert returned.wait(1.5), 'A stuck SDK close must not hang Stop or server shutdown'
        assert responses[0].status_code == 200
        state = ctx.http.get('/api/state').json()
        assert not state['running'] and not state['connected']
        replacement = object()
        ctx.engine._feed = replacement
        ctx.engine._connected = True
        ctx.engine._on_close(old)
        assert ctx.engine._connected  # Late close cannot disconnect a new feed.
        ctx.engine._feed = None
    finally:
        release.set()
        worker.join(2)


@pytest.mark.parametrize('stuck', [False, True])
def test_sdk_async_feed_close_is_bounded_and_aborts_stuck_transport(stuck):
    loop = asyncio.new_event_loop()
    started, closed, aborted = threading.Event(), threading.Event(), threading.Event()
    class AsyncFeed:
        _running = True
        def close_connection(self):
            pytest.fail('Do not invoke the SDK unbounded future.result() wrapper')
        async def disconnect(self):
            started.set()
            try:
                if stuck:
                    await asyncio.Event().wait()
            finally:
                closed.set()
    feed = AsyncFeed()
    feed.loop = loop
    feed.ws = SimpleNamespace(transport=SimpleNamespace(abort=aborted.set))
    ready = threading.Event()
    loop.call_soon(ready.set)
    worker = threading.Thread(target=loop.run_forever)
    worker.start()
    assert ready.wait(1)
    try:
        close_market_feed(feed, timeout=.05)
        assert started.is_set()
        assert closed.wait(1)
        if stuck:
            assert aborted.wait(1)
        assert not feed._running
    finally:
        async def drain():
            pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
        asyncio.run_coroutine_threadsafe(drain(), loop).result(2)
        loop.call_soon_threadsafe(loop.stop)
        worker.join(2)
        loop.close()
