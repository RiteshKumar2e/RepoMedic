"""Analysis progress pub/sub feeding the Server-Sent Events endpoint.

Redis-backed when ``REDIS_URL`` is configured (so API replicas see events from
worker processes); otherwise an in-process asyncio broker for single-node dev.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict, deque
from typing import Any, AsyncIterator, Optional

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_CHANNEL_PREFIX = "repomedic:analysis:"
_REPLAY_LIMIT = 200

# Recent events per analysis so a late subscriber can catch up rather than
# staring at an empty stream.
_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=_REPLAY_LIMIT))
_subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)
_loop: Optional[asyncio.AbstractEventLoop] = None


def set_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Registered at app startup so worker threads can publish safely."""
    global _loop
    _loop = loop


def _redis():
    if not settings.redis_url:
        return None
    try:
        import redis

        return redis.Redis.from_url(settings.redis_url, socket_connect_timeout=0.25)
    except Exception:
        return None


def publish(analysis_id: str, event_type: str, payload: dict[str, Any]) -> None:
    """Publish a progress event. Safe to call from any thread."""
    message = {
        "type": event_type,
        "analysis_id": analysis_id,
        "timestamp": time.time(),
        **payload,
    }
    _history[analysis_id].append(message)

    client = _redis()
    if client is not None:
        try:
            client.publish(_CHANNEL_PREFIX + analysis_id, json.dumps(message))
            client.rpush(_CHANNEL_PREFIX + analysis_id + ":log", json.dumps(message))
            client.expire(_CHANNEL_PREFIX + analysis_id + ":log", 3600)
        except Exception:
            pass

    queues = list(_subscribers.get(analysis_id, ()))
    if not queues:
        return
    for queue in queues:
        try:
            if _loop and _loop.is_running():
                _loop.call_soon_threadsafe(queue.put_nowait, message)
            else:
                queue.put_nowait(message)
        except (asyncio.QueueFull, RuntimeError):
            continue


def history(analysis_id: str) -> list[dict[str, Any]]:
    local = list(_history.get(analysis_id, ()))
    if local:
        return local
    client = _redis()
    if client is None:
        return []
    try:
        raw = client.lrange(_CHANNEL_PREFIX + analysis_id + ":log", 0, -1)
        return [json.loads(item) for item in raw]
    except Exception:
        return []


async def subscribe(analysis_id: str) -> AsyncIterator[dict[str, Any]]:
    """Yield replayed history, then live events until the analysis terminates."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=512)
    _subscribers[analysis_id].add(queue)

    redis_task: Optional[asyncio.Task] = None
    client = _redis()
    if client is not None:
        redis_task = asyncio.create_task(_pump_redis(analysis_id, queue, client))

    try:
        for message in history(analysis_id):
            yield message
        while True:
            try:
                message = await asyncio.wait_for(queue.get(), timeout=15.0)
            except asyncio.TimeoutError:
                yield {"type": "heartbeat", "analysis_id": analysis_id, "timestamp": time.time()}
                continue
            yield message
            if message.get("type") in ("completed", "failed", "cancelled"):
                break
    finally:
        _subscribers[analysis_id].discard(queue)
        if redis_task:
            redis_task.cancel()


async def _pump_redis(analysis_id: str, queue: asyncio.Queue, client: Any) -> None:
    """Bridge Redis pub/sub into the local asyncio queue."""

    def _listen() -> None:
        pubsub = client.pubsub()
        pubsub.subscribe(_CHANNEL_PREFIX + analysis_id)
        for raw in pubsub.listen():
            if raw.get("type") != "message":
                continue
            try:
                message = json.loads(raw["data"])
            except (ValueError, TypeError):
                continue
            loop = _loop or asyncio.get_event_loop()
            loop.call_soon_threadsafe(queue.put_nowait, message)

    try:
        await asyncio.get_running_loop().run_in_executor(None, _listen)
    except asyncio.CancelledError:  # pragma: no cover - shutdown path
        raise
    except Exception as exc:  # pragma: no cover - redis hiccup
        logger.warning("events.redis_pump_failed", error=str(exc))


def clear(analysis_id: str) -> None:
    _history.pop(analysis_id, None)
    _subscribers.pop(analysis_id, None)
