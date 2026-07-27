"""User provisioning and session issuance."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from sqlalchemy import func
from sqlmodel import Session, select

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import create_session_token, encrypt_secret, hash_password, verify_password
from app.models.entities import GitHubInstallation, User, utcnow

logger = get_logger(__name__)

DEMO_USER_LOGIN = "demo-user"
DEMO_USER_EMAIL = "demo@repomedic.dev"

@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    """Compared against when no account matches, so a failed lookup costs the
    same as a wrong password. Derived lazily — the KDF is deliberately slow."""
    return hash_password("repomedic-timing-equalisation-placeholder")


class EmailAlreadyRegisteredError(Exception):
    """Raised when a signup targets an address that already has an account."""

    def __init__(self, email: str) -> None:
        super().__init__(f"An account already exists for {email}")
        self.email = email


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


# --------------------------------------------------------------------------- #
# Email + password accounts
# --------------------------------------------------------------------------- #
def find_user_by_email(session: Session, email: str) -> User | None:
    """Case-insensitive lookup. Schemas already lower-case the input."""
    return session.exec(select(User).where(func.lower(User.email) == email.lower())).first()


def register_user(session: Session, *, name: str, email: str, password: str) -> User:
    """Create a password account, or raise if the address is already claimed."""
    if find_user_by_email(session, email) is not None:
        raise EmailAlreadyRegisteredError(email)

    user = User(
        name=name,
        email=email,
        login=_login_from_email(session, email),
        password_hash=hash_password(password),
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    logger.info("auth.registered", user_id=user.id)
    return user


def authenticate_user(session: Session, *, email: str, password: str) -> User | None:
    """Return the user when the password matches, ``None`` otherwise.

    The hash comparison runs even for unknown addresses so response timing does
    not reveal which accounts exist.
    """
    user = find_user_by_email(session, email)
    stored_hash = user.password_hash if user and user.password_hash else _dummy_hash()
    if not verify_password(password, stored_hash):
        return None
    return user


def _login_from_email(session: Session, email: str) -> str:
    """Derive a readable handle, suffixed until it stops colliding."""
    base = re.sub(r"[^a-z0-9-]", "-", email.split("@", 1)[0].lower()).strip("-") or "user"
    candidate = base
    suffix = 1
    while session.exec(select(User).where(User.login == candidate)).first() is not None:
        suffix += 1
        candidate = f"{base}-{suffix}"
    return candidate


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
    same_site = settings.cookie_samesite
    kwargs: dict[str, Any] = {
        "key": settings.cookie_name,
        "httponly": True,
        # SameSite=None is only honoured on a Secure cookie; browsers reject the
        # pair otherwise, which would silently drop the session.
        "secure": settings.cookie_secure or settings.is_production or same_site == "none",
        "samesite": same_site,
        "path": "/",
    }
    if settings.cookie_domain:
        kwargs["domain"] = settings.cookie_domain
    return kwargs
