"""Repository listing, sync, settings, and nested pull-request listing."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from app.api.deps import CurrentUser, RateLimited, SessionDep, client_ip, load_repository
from app.core.errors import AuthenticationError
from app.core.logging import get_logger
from app.github import service as github_service
from app.models.enums import PullRequestStatus
from app.schemas.repository import (
    PullRequestRead,
    RepositoryRead,
    RepositorySettingsRead,
    RepositorySettingsUpdate,
)
from app.services import audit
from app.services import repositories as repo_service

logger = get_logger(__name__)
router = APIRouter(prefix="/repositories", tags=["repositories"])


@router.get("", response_model=list[RepositoryRead], summary="List connected repositories")
def list_repositories(user: CurrentUser, session: SessionDep) -> list[RepositoryRead]:
    rows = repo_service.list_repositories(session, user)
    return [RepositoryRead.model_validate(r) for r in rows]


@router.post(
    "/sync",
    response_model=list[RepositoryRead],
    dependencies=[RateLimited],
    summary="Re-sync repositories from GitHub",
)
async def sync_repositories(
    request: Request, user: CurrentUser, session: SessionDep
) -> list[RepositoryRead]:
    if user.is_demo:
        raise AuthenticationError("The demo account cannot sync from GitHub")
    rows = await github_service.sync_repositories(session, user.id)
    audit.record(
        session,
        action="repository.synced",
        entity_type="user",
        entity_id=user.id,
        user_id=user.id,
        metadata={"count": len(rows)},
        ip_address=client_ip(request),
    )
    return [RepositoryRead.model_validate(r) for r in rows]


@router.get("/{repository_id}", response_model=RepositoryRead, summary="Repository detail")
def get_repository(repository_id: str, user: CurrentUser, session: SessionDep) -> RepositoryRead:
    repo = load_repository(repository_id, session, user)
    return RepositoryRead.model_validate(repo)


@router.get(
    "/{repository_id}/pull-requests",
    response_model=list[PullRequestRead],
    summary="List pull requests for a repository",
)
def list_pull_requests(
    repository_id: str,
    user: CurrentUser,
    session: SessionDep,
    status: PullRequestStatus | None = Query(default=None),
) -> list[PullRequestRead]:
    repo = load_repository(repository_id, session, user)
    rows = repo_service.list_pull_requests(session, repo, status)
    return [PullRequestRead.model_validate(pr) for pr in rows]


@router.post(
    "/{repository_id}/pull-requests/sync",
    response_model=list[PullRequestRead],
    dependencies=[RateLimited],
    summary="Re-sync pull requests from GitHub",
)
async def sync_pull_requests(
    repository_id: str, user: CurrentUser, session: SessionDep
) -> list[PullRequestRead]:
    repo = load_repository(repository_id, session, user)
    if user.is_demo:
        raise AuthenticationError("The demo account cannot sync from GitHub")
    rows = await github_service.sync_pull_requests(session, repo)
    return [PullRequestRead.model_validate(pr) for pr in rows]


@router.get(
    "/{repository_id}/settings",
    response_model=RepositorySettingsRead,
    summary="Read repository review settings",
)
def get_settings(
    repository_id: str, user: CurrentUser, session: SessionDep
) -> RepositorySettingsRead:
    repo = load_repository(repository_id, session, user)
    return RepositorySettingsRead.model_validate(repo_service.get_or_create_settings(session, repo))


@router.put(
    "/{repository_id}/settings",
    response_model=RepositorySettingsRead,
    dependencies=[RateLimited],
    summary="Update repository review settings",
)
def update_settings(
    repository_id: str,
    payload: RepositorySettingsUpdate,
    request: Request,
    user: CurrentUser,
    session: SessionDep,
) -> RepositorySettingsRead:
    repo = load_repository(repository_id, session, user)
    updated = repo_service.update_settings(
        session, repo, payload.model_dump(exclude_unset=True, exclude_none=True)
    )
    audit.record(
        session,
        action="settings.updated",
        entity_type="repository",
        entity_id=repo.id,
        user_id=user.id,
        metadata={"target": repo.full_name, "fields": list(payload.model_dump(exclude_unset=True).keys())},
        ip_address=client_ip(request),
    )
    return RepositorySettingsRead.model_validate(updated)
