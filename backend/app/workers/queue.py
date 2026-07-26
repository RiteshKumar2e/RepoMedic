"""Task dispatch.

Dramatiq + Redis when ``REDIS_URL`` points at a reachable broker; otherwise a
daemon-thread executor so the whole product runs with no external services in
development. The calling code does not change between the two.
"""

from __future__ import annotations

import asyncio
import threading

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_broker = None
_dramatiq_actor = None


def _init_dramatiq():
    """Configure the Redis broker once, returning the registered actor."""
    global _broker, _dramatiq_actor
    if _dramatiq_actor is not None:
        return _dramatiq_actor
    if not settings.redis_url:
        return None

    try:
        import dramatiq
        from dramatiq.brokers.redis import RedisBroker

        broker = RedisBroker(url=settings.redis_url)
        broker.client.ping()
        dramatiq.set_broker(broker)
        _broker = broker

        @dramatiq.actor(max_retries=1, time_limit=1_800_000, queue_name="repomedic")
        def run_analysis_actor(analysis_id: str) -> None:  # pragma: no cover - worker process
            from app.workers.tasks import run_analysis_sync

            run_analysis_sync(analysis_id)

        _dramatiq_actor = run_analysis_actor
        logger.info("queue.dramatiq_ready", broker="redis")
        return _dramatiq_actor
    except Exception as exc:
        logger.info("queue.dramatiq_unavailable", error=str(exc))
        return None


def queue_backend() -> str:
    return "dramatiq+redis" if _init_dramatiq() is not None else "in-process"


def enqueue_analysis(analysis_id: str) -> str:
    """Schedule an analysis. Returns the backend that accepted it."""
    actor = _init_dramatiq()
    if actor is not None:
        actor.send(analysis_id)
        logger.info("queue.enqueued", analysis_id=analysis_id, backend="dramatiq")
        return "dramatiq"

    thread = threading.Thread(
        target=_run_in_thread, args=(analysis_id,), name=f"analysis-{analysis_id[:8]}", daemon=True
    )
    thread.start()
    logger.info("queue.enqueued", analysis_id=analysis_id, backend="thread")
    return "thread"


def _run_in_thread(analysis_id: str) -> None:
    from app.workers.tasks import run_analysis_sync

    try:
        run_analysis_sync(analysis_id)
    except Exception:  # pragma: no cover - defensive; tasks already log failures
        logger.exception("queue.thread_task_failed", analysis_id=analysis_id)


def run_coroutine(coro) -> None:
    """Run a coroutine on a private event loop inside a worker thread."""
    loop: asyncio.AbstractEventLoop | None = None
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(coro)
    finally:
        if loop is not None:
            loop.close()
            asyncio.set_event_loop(None)
