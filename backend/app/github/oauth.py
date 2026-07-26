"""GitHub OAuth (user login) and GitHub App installation-token exchange."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import settings
from app.core.errors import AuthenticationError, ExternalServiceError
from app.core.logging import get_logger
from app.core.security import create_github_app_jwt

logger = get_logger(__name__)

AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"


def build_authorize_url(state: str) -> str:
    """Build the GitHub consent URL. Requests the minimum scopes we need."""
    params = {
        "client_id": settings.github_client_id,
        "redirect_uri": f"{settings.api_url}{settings.api_v1_prefix}/auth/github/callback",
        "scope": " ".join(settings.github_scope_list),
        "state": state,
        "allow_signup": "false",
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code_for_token(code: str) -> dict[str, Any]:
    """Trade the OAuth callback code for an access token."""
    if not settings.github_oauth_configured:
        raise AuthenticationError("GitHub OAuth is not configured on this server")

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            ACCESS_TOKEN_URL,
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
                "redirect_uri": f"{settings.api_url}{settings.api_v1_prefix}/auth/github/callback",
            },
        )
    if response.status_code >= 400:
        raise ExternalServiceError("GitHub rejected the OAuth code exchange")

    payload = response.json()
    if "error" in payload:
        raise AuthenticationError(payload.get("error_description", payload["error"]))
    if not payload.get("access_token"):
        raise AuthenticationError("GitHub did not return an access token")
    return payload


async def create_installation_token(installation_id: int) -> dict[str, Any]:
    """Mint a short-lived installation access token for a GitHub App install."""
    app_jwt = create_github_app_jwt()
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            f"{settings.github_api_url}/app/installations/{installation_id}/access_tokens",
            headers={
                "Authorization": f"Bearer {app_jwt}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
    if response.status_code >= 400:
        raise ExternalServiceError(
            "Could not create GitHub installation token",
            details={"status": response.status_code},
        )
    payload = response.json()
    expires_at = payload.get("expires_at")
    return {
        "token": payload["token"],
        "expires_at": (
            datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if expires_at
            else datetime.now(timezone.utc) + timedelta(hours=1)
        ),
        "permissions": payload.get("permissions", {}),
    }
