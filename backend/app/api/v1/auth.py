"""GitHub OAuth login, demo login, session inspection and logout."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlmodel import select

from app.api.deps import CurrentUser, RateLimited, SessionDep, client_ip
from app.core.config import settings
from app.core.errors import AuthenticationError
from app.core.logging import get_logger
from app.core.security import create_oauth_state, verify_oauth_state
from app.github.client import GitHubClient
from app.github.oauth import build_authorize_url, exchange_code_for_token
from app.models.entities import GitHubInstallation
from app.schemas.auth import (
    GitHubAuthStartRequest,
    GitHubAuthStartResponse,
    SessionResponse,
    UserRead,
)
from app.schemas.common import Acknowledgement
from app.services import audit
from app.services import auth as auth_service

logger = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/github",
    response_model=GitHubAuthStartResponse,
    dependencies=[RateLimited],
    summary="Begin the GitHub OAuth flow",
)
def start_github_auth(payload: GitHubAuthStartRequest) -> GitHubAuthStartResponse:
    """Returns a consent URL carrying a signed, time-limited ``state`` value."""
    state = create_oauth_state(payload.redirect_path)
    if not settings.github_oauth_configured:
        return GitHubAuthStartResponse(authorize_url="", state=state, configured=False)
    return GitHubAuthStartResponse(
        authorize_url=build_authorize_url(state), state=state, configured=True
    )


@router.get("/github/callback", summary="GitHub OAuth callback")
async def github_callback(
    request: Request,
    session: SessionDep,
    code: str = Query(...),
    state: str = Query(...),
) -> RedirectResponse:
    """Validate state, exchange the code, provision the user, set the cookie."""
    try:
        redirect_path = verify_oauth_state(state)
    except ValueError as exc:
        raise AuthenticationError(f"OAuth state rejected: {exc}") from exc

    token_payload = await exchange_code_for_token(code)
    access_token = token_payload["access_token"]

    async with GitHubClient(access_token) as gh:
        profile = await gh.get_authenticated_user()
        emails = await gh.get_user_emails()

    primary_email = next(
        (e["email"] for e in emails if e.get("primary") and e.get("verified")), None
    )
    user = auth_service.upsert_github_user(session, profile, primary_email)
    auth_service.store_oauth_installation(
        session, user, access_token, scopes=token_payload.get("scope", "")
    )
    audit.record(
        session,
        action="auth.login",
        entity_type="user",
        entity_id=user.id,
        user_id=user.id,
        metadata={"method": "github_oauth"},
        ip_address=client_ip(request),
    )

    response = RedirectResponse(url=f"{settings.frontend_url}{redirect_path}", status_code=302)
    response.set_cookie(
        value=auth_service.issue_session(user),
        max_age=settings.jwt_expire_minutes * 60,
        **auth_service.cookie_kwargs(),
    )
    return response


@router.post(
    "/demo",
    response_model=SessionResponse,
    dependencies=[RateLimited],
    summary="Sign in to the seeded demo workspace",
)
def demo_login(request: Request, response: Response, session: SessionDep) -> SessionResponse:
    """Demo mode exists so the product is explorable without GitHub credentials."""
    if not settings.demo_mode:
        raise AuthenticationError("Demo mode is disabled on this deployment")

    user = auth_service.get_or_create_demo_user(session)
    token = auth_service.issue_session(user)
    response.set_cookie(
        value=token, max_age=settings.jwt_expire_minutes * 60, **auth_service.cookie_kwargs()
    )
    audit.record(
        session,
        action="auth.login",
        entity_type="user",
        entity_id=user.id,
        user_id=user.id,
        metadata={"method": "demo"},
        ip_address=client_ip(request),
    )
    return SessionResponse(
        user=UserRead.model_validate(user),
        github_connected=False,
        token=token,
    )


@router.get("/session", response_model=SessionResponse, summary="Inspect the current session")
def read_session(user: CurrentUser, session: SessionDep) -> SessionResponse:
    installation = session.exec(
        select(GitHubInstallation).where(GitHubInstallation.user_id == user.id)
    ).first()
    return SessionResponse(
        user=UserRead.model_validate(user),
        github_connected=bool(installation and installation.encrypted_access_token),
    )


@router.post("/logout", response_model=Acknowledgement, summary="Clear the session cookie")
def logout(response: Response) -> Acknowledgement:
    kwargs = auth_service.cookie_kwargs()
    response.delete_cookie(
        key=kwargs["key"], path=kwargs["path"], domain=kwargs.get("domain")
    )
    return Acknowledgement(message="Signed out")
