"""User provisioning and session issuance."""

from __future__ import annotations

from typing import Any

from sqlmodel import Session, select

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import create_session_token, encrypt_secret
from app.models.entities import GitHubInstallation, User, utcnow

logger = get_logger(__name__)

DEMO_USER_LOGIN = "demo-user"
DEMO_USER_EMAIL = "demo@repomedic.dev"


def upsert_github_user(session: Session, profile: dict[str, Any], email: str | None) -> User:
    user = session.exec(select(User).where(User.github_user_id == profile["id"])).first()
    if user is None:
        user = User(github_user_id=profile["id"])
    user.login = profile.get("login")
    user.name = profile.get("name") or profile.get("login")
    user.email = email or profile.get("email") or user.email
    user.avatar_url = profile.get("avatar_url")
    user.updated_at = utcnow()
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def store_oauth_installation(
    session: Session,
    user: User,
    access_token: str,
    *,
    scopes: str = "",
    installation_id: int | None = None,
) -> GitHubInstallation:
    """Persist the GitHub credential, encrypted at rest."""
    installation = session.exec(
        select(GitHubInstallation).where(GitHubInstallation.user_id == user.id)
    ).first()
    if installation is None:
        installation = GitHubInstallation(user_id=user.id)
    installation.encrypted_access_token = encrypt_secret(access_token)
    installation.scopes = scopes
    installation.account_login = user.login
    installation.account_type = "User"
    if installation_id:
        installation.installation_id = installation_id
    installation.updated_at = utcnow()
    session.add(installation)
    session.commit()
    session.refresh(installation)
    return installation


def get_or_create_demo_user(session: Session) -> User:
    """The seeded account used by demo mode — never has real GitHub credentials."""
    user = session.exec(select(User).where(User.login == DEMO_USER_LOGIN)).first()
    if user is None:
        user = User(
            login=DEMO_USER_LOGIN,
            name="Demo Reviewer",
            email=DEMO_USER_EMAIL,
            avatar_url="https://avatars.githubusercontent.com/u/9919?v=4",
            is_demo=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
    return user


def issue_session(user: User) -> str:
    return create_session_token(user.id, extra={"login": user.login or "", "demo": user.is_demo})


def cookie_kwargs() -> dict[str, Any]:
    """Hardened cookie attributes shared by login and logout."""
    kwargs: dict[str, Any] = {
        "key": settings.cookie_name,
        "httponly": True,
        "secure": settings.cookie_secure or settings.is_production,
        "samesite": "lax",
        "path": "/",
    }
    if settings.cookie_domain:
        kwargs["domain"] = settings.cookie_domain
    return kwargs
