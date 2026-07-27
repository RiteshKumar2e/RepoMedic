"""GitHub OAuth login, demo login, session inspection and logout."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlmodel import select

from app.api.deps import OptionalUser, RateLimited, SessionDep, client_ip
from app.core.config import settings
from app.core.errors import AuthenticationError, ConflictError
from app.core.logging import get_logger
from app.core.security import create_oauth_state, verify_oauth_state
from app.github.client import GitHubClient
from app.github.oauth import build_authorize_url, exchange_code_for_token
from app.models.entities import GitHubInstallation, User
from app.schemas.auth import (
    GitHubAuthStartRequest,
    GitHubAuthStartResponse,
    LoginRequest,
    RegisterRequest,
    SessionResponse,
    UserRead,
)
from app.schemas.common import Acknowledgement
from app.services import audit
from app.services import auth as auth_service

logger = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


def _start_session(response: Response, user: User) -> str:
    """Issue the session token and attach the hardened cookie."""
    token = auth_service.issue_session(user)
    response.set_cookie(
        value=token, max_age=settings.jwt_expire_minutes * 60, **auth_service.cookie_kwargs()
    )
    return token


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
    "/register",
    response_model=SessionResponse,
    status_code=201,
    dependencies=[RateLimited],
    summary="Create an email and password account",
)
def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    session: SessionDep,
) -> SessionResponse:
    """Provision the account and sign the new user straight in."""
    try:
        user = auth_service.register_user(
            session, name=payload.name, email=payload.email, password=payload.password
        )
    except auth_service.EmailAlreadyRegisteredError as exc:
        raise ConflictError("An account with that email already exists") from exc

    token = _start_session(response, user)
    audit.record(
        session,
        action="auth.register",
        entity_type="user",
        entity_id=user.id,
        user_id=user.id,
        metadata={"method": "password"},
        ip_address=client_ip(request),
    )
    return SessionResponse(
        user=UserRead.model_validate(user), github_connected=False, token=token
    )


@router.post(
    "/login",
    response_model=SessionResponse,
    dependencies=[RateLimited],
    summary="Sign in with email and password",
)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: SessionDep,
) -> SessionResponse:
    user = auth_service.authenticate_user(
        session, email=payload.email, password=payload.password
    )
    if user is None:
        # One message for both causes — never disclose which addresses exist.
        raise AuthenticationError("Incorrect email or password")

    token = _start_session(response, user)
    audit.record(
        session,
        action="auth.login",
        entity_type="user",
        entity_id=user.id,
        user_id=user.id,
        metadata={"method": "password"},
        ip_address=client_ip(request),
    )
    installation = session.exec(
        select(GitHubInstallation).where(GitHubInstallation.user_id == user.id)
    ).first()
    return SessionResponse(
        user=UserRead.model_validate(user),
        github_connected=bool(installation and installation.encrypted_access_token),
        token=token,
    )


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
    token = _start_session(response, user)
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
def read_session(user: OptionalUser, session: SessionDep) -> SessionResponse:
    """Report who the caller is, if anyone.

    This asks a question rather than guarding a resource, and "nobody is signed
    in" is a valid answer — so it returns 200 with ``authenticated: false``
    instead of 401. Every public page calls this on load; a 401 there is console
    noise that hides real authentication failures. Protected endpoints still
    reject anonymous callers.
    """
    if user is None:
        return SessionResponse(user=None, authenticated=False)

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
