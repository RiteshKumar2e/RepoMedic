"""Version 1 of the public REST API."""

from fastapi import APIRouter

from app.api.v1 import (
    analyses,
    analytics,
    auth,
    findings,
    graph,
    health,
    patches,
    pull_requests,
    repositories,
    webhooks,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(repositories.router)
api_router.include_router(pull_requests.router)
api_router.include_router(analyses.router)
api_router.include_router(findings.router)
api_router.include_router(patches.router)
api_router.include_router(graph.router)
api_router.include_router(analytics.router)
api_router.include_router(webhooks.router)

__all__ = ["api_router"]
