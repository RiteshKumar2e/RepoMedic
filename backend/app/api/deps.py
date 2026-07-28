"""Shared FastAPI dependencies: session, current user, ownership checks, limits."""

from __future__ import annotations

from typing import Annotated

import jwt
from fastapi import Depends, Query, Request
from sqlmodel import Session, select

from app.core.config import settings
from app.core.errors import AuthenticationError, AuthorizationError, NotFoundError
from app.core.rate_limit import check_rate_limit
from app.core.security import decode_session_token
from app.db.session import get_session
from app.models.entities import (
    Analysis,
    Finding,
    GitHubInstallation,
    Patch,
    PullRequest,
    Repository,
    User,
)

SessionDep = Annotated[Session, Depends(get_session)]


def _extract_token(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return request.cookies.get(settings.cookie_name)


def get_current_user(request: Request, session: SessionDep) -> User:
    """Resolve the authenticated user from the session cookie or bearer token."""
    token = _extract_token(request)
    if not token:
        raise AuthenticationError("Authentication required")
    try:
        payload = decode_session_token(token)
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Session expired") from exc
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Invalid session token") from exc

    user = session.get(User, payload["sub"])
    if user is None:
        raise AuthenticationError("Session user no longer exists")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_optional_user(request: Request, session: SessionDep) -> User | None:
    try:
        return get_current_user(request, session)
    except AuthenticationError:
        return None


OptionalUser = Annotated[User | None, Depends(get_optional_user)]


def get_stream_user(
    request: Request,
    session: SessionDep,
    token: str | None = Query(default=None, description="Session token for EventSource"),
) -> User:
    """Authenticate a Server-Sent Events connection.

    ``EventSource`` cannot set request headers, so it can never send a bearer
    token. Its only other credential is the session cookie — which, when the app
    and the API are on different sites, is a third-party cookie that browsers
    now block outright. Without this the stream is unauthenticated for every
    split deployment.

    Accepting the token in the query string is deliberately scoped to this one
    route: query strings are recorded in access logs and proxy history, so it is
    not something to generalise to the rest of the API.
    """
    if token:
        try:
            payload = decode_session_token(token)
        except jwt.ExpiredSignatureError as exc:
            raise AuthenticationError("Session expired") from exc
        except jwt.PyJWTError as exc:
            raise AuthenticationError("Invalid session token") from exc

        user = session.get(User, payload["sub"])
        if user is None:
            raise AuthenticationError("Session user no longer exists")
        return user

    return get_current_user(request, session)


StreamUser = Annotated[User, Depends(get_stream_user)]


def get_admin_user(user: CurrentUser) -> User:
    """Gate the cross-tenant admin views.

    Admin is granted by the ADMIN_EMAILS allowlist rather than a database flag,
    so access is revoked by editing configuration and cannot be escalated by
    anything a user is able to change about their own account. An empty
    allowlist denies everyone.
    """
    if not settings.is_admin_email(user.email):
        raise AuthorizationError("Administrator access is required")
    return user


AdminUser = Annotated[User, Depends(get_admin_user)]


def rate_limiter(request: Request) -> None:
    identity = request.client.host if request.client else "anonymous"
    token = _extract_token(request)
    if token:
        identity = f"token:{token[-16:]}"
    check_rate_limit(identity)


RateLimited = Depends(rate_limiter)


# --------------------------------------------------------------------------- #
# Ownership-scoped resource loaders — every read is filtered by the caller.
# --------------------------------------------------------------------------- #
def _user_installation_ids(session: Session, user: User) -> list[str]:
    return [
        row.id
        for row in session.exec(
            select(GitHubInstallation).where(GitHubInstallation.user_id == user.id)
        )
    ]


def load_repository(repository_id: str, session: Session, user: User) -> Repository:
    repo = session.get(Repository, repository_id)
    if repo is None:
        raise NotFoundError("Repository not found")
    if repo.installation_id not in _user_installation_ids(session, user):
        raise AuthorizationError("You do not have access to this repository")
    return repo


def load_pull_request(pull_request_id: str, session: Session, user: User) -> PullRequest:
    pr = session.get(PullRequest, pull_request_id)
    if pr is None:
        raise NotFoundError("Pull request not found")
    load_repository(pr.repository_id, session, user)
    return pr


def load_analysis(analysis_id: str, session: Session, user: User) -> Analysis:
    analysis = session.get(Analysis, analysis_id)
    if analysis is None:
        raise NotFoundError("Analysis not found")
    load_pull_request(analysis.pull_request_id, session, user)
    return analysis


def load_finding(finding_id: str, session: Session, user: User) -> Finding:
    finding = session.get(Finding, finding_id)
    if finding is None:
        raise NotFoundError("Finding not found")
    load_analysis(finding.analysis_id, session, user)
    return finding


def load_patch(patch_id: str, session: Session, user: User) -> Patch:
    patch = session.get(Patch, patch_id)
    if patch is None:
        raise NotFoundError("Patch not found")
    load_finding(patch.finding_id, session, user)
    return patch


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
