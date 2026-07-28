"""Authentication request/response schemas."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field, field_validator

# Long enough to resist offline guessing, capped so a huge body cannot be used
# to burn CPU in the KDF.
MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 200

# Deliberately pragmatic rather than RFC-complete: the authoritative check is
# whether mail is deliverable, which no regex can answer. Validating shape here
# avoids pulling in `email-validator`, which the offline install does not have.
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")


def _normalize_email(value: str) -> str:
    cleaned = value.strip().lower()
    if not _EMAIL_PATTERN.match(cleaned):
        raise ValueError("Enter a valid email address")
    return cleaned


# Normalised at the boundary so lookups and uniqueness are case-insensitive.
EmailField = Annotated[str, Field(max_length=254), AfterValidator(_normalize_email)]


class GitHubAuthStartRequest(BaseModel):
    redirect_path: str = Field(default="/dashboard", max_length=200)


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailField
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Name must not be blank")
        return cleaned

    @field_validator("password")
    @classmethod
    def _password_strength(cls, value: str) -> str:
        if value.strip() != value:
            raise ValueError("Password must not start or end with whitespace")
        if not any(c.isalpha() for c in value) or not any(c.isdigit() for c in value):
            raise ValueError("Password must contain at least one letter and one number")
        return value


class LoginRequest(BaseModel):
    email: EmailField
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)


class GitHubAuthStartResponse(BaseModel):
    authorize_url: str
    state: str
    configured: bool


class UserRead(BaseModel):
    id: str
    login: str | None = None
    name: str | None = None
    email: str | None = None
    avatar_url: str | None = None
    is_demo: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class SessionResponse(BaseModel):
    # None when nobody is signed in — /auth/session answers that with 200.
    user: UserRead | None = None
    authenticated: bool = True
    github_connected: bool = False
    # Derived from the ADMIN_EMAILS allowlist, never stored on the user row.
    is_admin: bool = False
    token: str | None = None
