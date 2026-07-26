"""Liveness and capability reporting."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from app import __version__
from app.core.config import settings
from app.db.session import engine
from app.schemas.common import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Service health and capabilities")
def health() -> HealthResponse:
    database = "unavailable"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        database = "turso" if settings.is_turso else "sqlite"
    except Exception:
        database = "error"

    queue = "in-process"
    if settings.redis_url:
        try:
            import redis

            redis.Redis.from_url(settings.redis_url, socket_connect_timeout=0.25).ping()
            queue = "redis"
        except Exception:
            queue = "redis-unreachable"

    return HealthResponse(
        status="ok" if database != "error" else "degraded",
        version=__version__,
        environment=settings.app_env,
        database=database,
        queue=queue,
        llm_provider=settings.default_llm_provider,
        demo_mode=settings.demo_mode,
        sandbox_mode=settings.sandbox_mode.value,
        github_oauth_configured=settings.github_oauth_configured,
        github_app_configured=settings.github_app_configured,
    )
