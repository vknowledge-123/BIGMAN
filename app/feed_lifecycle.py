"""Bounded shutdown for the scanner's SDK feed (separate from algo feeds)."""
import asyncio
from concurrent.futures import TimeoutError as FutureTimeout
import logging
import threading

LOGGER = logging.getLogger(__name__)


def close_market_feed(feed, timeout=1.0):
    loop = getattr(feed, 'loop', None)
    disconnect = getattr(feed, 'disconnect', None)
    if loop is not None and loop.is_running() and callable(disconnect):
        def abort():
            feed._running = False
            transport = getattr(getattr(feed, 'ws', None), 'transport', None)
            if transport is not None:
                transport.abort()

        async def close():
            try:
                await asyncio.wait_for(disconnect(), timeout=timeout)
            except Exception:
                abort()
                raise
            finally:
                feed._running = False

        # SDK close_connection waits on future.result() without a timeout. Its
        # receive loop can exit before resolving that future. Bound our wait.
        coroutine = close()
        try:
            future = asyncio.run_coroutine_threadsafe(coroutine, loop)
        except RuntimeError:
            coroutine.close()  # Loop closed between the readiness check and submit.
        else:
            try:
                future.result(timeout=timeout + .05)
            except FutureTimeout:
                feed._running = False
                future.cancel()
                try:
                    loop.call_soon_threadsafe(abort)
                except RuntimeError:
                    pass  # The receive loop has already closed.
                LOGGER.warning('Scanner feed close exceeded its deadline; cleanup requested')
            except Exception as exc:
                LOGGER.warning('Scanner feed close failed (%s)', type(exc).__name__)
            return

    # Handles a feed that failed before its loop started, and older SDK adapters.
    def close_sync():
        try:
            feed.close_connection()
        except Exception as exc:
            LOGGER.warning('Scanner feed close failed (%s)', type(exc).__name__)

    worker = threading.Thread(target=close_sync, name='scanner-feed-close', daemon=True)
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        LOGGER.warning('Scanner feed close is still pending; scanner callbacks are detached')
