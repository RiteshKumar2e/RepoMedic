"""Dashboard and analytics endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, SessionDep, load_repository
from app.llm.registry import provider_status
from app.scanners.registry import available_scanners
from app.schemas.analytics import DashboardResponse, RepositoryAnalyticsResponse
from app.services import analytics as analytics_service

router = APIRouter(tags=["analytics"])


@router.get("/dashboard", response_model=DashboardResponse, summary="Workspace dashboard")
def dashboard(user: CurrentUser, session: SessionDep) -> DashboardResponse:
    return analytics_service.dashboard(session, user)


@router.get(
    "/repositories/{repository_id}/analytics",
    response_model=RepositoryAnalyticsResponse,
    summary="Repository analytics",
)
def repository_analytics(
    repository_id: str, user: CurrentUser, session: SessionDep
) -> RepositoryAnalyticsResponse:
    repository = load_repository(repository_id, session, user)
    return analytics_service.repository_analytics(session, repository)


@router.get("/capabilities", summary="Which scanners and LLM providers are usable right now")
def capabilities(user: CurrentUser) -> dict:
    """Surfaced in Settings so users can see exactly what is and is not active."""
    from app.analyzers.registry import supported_languages
    from app.core.config import settings
    from app.workers.queue import queue_backend

    return {
        "scanners": available_scanners(),
        "llm_providers": provider_status(),
        "languages": supported_languages(),
        "sandbox_mode": settings.sandbox_mode.value,
        "queue": queue_backend(),
        "host_test_execution_allowed": settings.allow_host_test_execution,
        "default_provider": settings.default_llm_provider,
        "max_analysis_cost_usd": settings.max_analysis_cost_usd,
    }
