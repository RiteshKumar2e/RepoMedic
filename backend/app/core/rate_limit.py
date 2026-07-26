"""Fixed-window rate limiting.

Uses Redis when configured (correct across worker processes) and falls back to
an in-process counter for single-node development.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict

from app.core.config import settings
from app.core.errors import RateLimitError

_local_buckets: dict[str, list[float]] = defaultdict(list)
_lock = threading.Lock()


def _redis_client():
    if not settings.redis_url:
        return None
    try:
        import redis

        return redis.Redis.from_url(settings.redis_url, socket_connect_timeout=0.25)
    except Exception:  # pragma: no cover - redis optional
        return None


def check_rate_limit(identity: str, *, limit: int | None = None, window: int | None = None) -> None:
    """Raise :class:`RateLimitError` when ``identity`` exceeds its quota."""
    limit = limit or settings.rate_limit_requests
    window = window or settings.rate_limit_window_seconds
    now = time.time()
    bucket = f"ratelimit:{identity}:{int(now // window)}"

    client = _redis_client()
    if client is not None:
        try:
            count = client.incr(bucket)
            if count == 1:
                client.expire(bucket, window)
            if count > limit:
                raise RateLimitError(
                    "Rate limit exceeded", details={"limit": limit, "window_seconds": window}
                )
            return
        except RateLimitError:
            raise
        except Exception:
            pass  # Redis unavailable — degrade to the local limiter.

    with _lock:
        hits = [t for t in _local_buckets[identity] if now - t < window]
        hits.append(now)
        _local_buckets[identity] = hits
        if len(hits) > limit:
            raise RateLimitError(
                "Rate limit exceeded", details={"limit": limit, "window_seconds": window}
            )
