"""Admin allowlist gating and the cross-tenant overview."""

from __future__ import annotations

import uuid

import pytest

from app.core.config import Settings

PASSWORD = "correct-horse-9"
ADMIN_EMAIL = "boss@example.com"


def _unique_email() -> str:
    return f"admin-test-{uuid.uuid4().hex[:12]}@example.com"


@pytest.fixture
def as_admin(monkeypatch):
    """Put ADMIN_EMAIL on the allowlist for the duration of one test."""
    from app.api import deps
    from app.api.v1 import admin as admin_router

    patched = Settings(_env_file=None, admin_emails=f" {ADMIN_EMAIL.upper()} ,other@example.com")
    monkeypatch.setattr(deps, "settings", patched)
    monkeypatch.setattr(admin_router, "settings", patched)
    return patched


# --------------------------------------------------------------------------- #
# Allowlist
# --------------------------------------------------------------------------- #
def test_allowlist_is_case_and_whitespace_insensitive():
    settings = Settings(_env_file=None, admin_emails="  Boss@Example.com , second@example.com ")

    assert settings.is_admin_email("boss@example.com")
    assert settings.is_admin_email("BOSS@EXAMPLE.COM")
    assert settings.is_admin_email("second@example.com")
    assert not settings.is_admin_email("someone@example.com")


@pytest.mark.parametrize("email", [None, "", "nobody@example.com"])
def test_empty_allowlist_grants_nobody(email):
    """The default must be closed: no ADMIN_EMAILS means no admins at all."""
    settings = Settings(_env_file=None, admin_emails="")

    assert settings.is_admin_email(email) is False


# --------------------------------------------------------------------------- #
# Endpoint gating
# --------------------------------------------------------------------------- #
def test_overview_rejects_anonymous_callers(client):
    client.post("/api/v1/auth/logout")

    assert client.get("/api/v1/admin/overview").status_code == 401


def test_overview_rejects_a_signed_in_non_admin(client):
    email = _unique_email()
    client.post(
        "/api/v1/auth/register",
        json={"name": "Regular", "email": email, "password": PASSWORD},
    )

    response = client.get("/api/v1/admin/overview")

    assert response.status_code == 403
    client.post("/api/v1/auth/logout")


def test_overview_allows_an_allowlisted_admin(client, as_admin):
    client.post(
        "/api/v1/auth/register",
        json={"name": "Boss", "email": ADMIN_EMAIL, "password": PASSWORD},
    )
    # The account may already exist from an earlier run; sign in either way.
    client.post("/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": PASSWORD})

    response = client.get("/api/v1/admin/overview")

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"totals", "users", "repositories", "analyses", "findings", "audit"}
    assert body["totals"]["users"] >= 1
    client.post("/api/v1/auth/logout")


def test_overview_never_exposes_credentials(client, as_admin):
    client.post(
        "/api/v1/auth/register",
        json={"name": "Boss", "email": ADMIN_EMAIL, "password": PASSWORD},
    )
    client.post("/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": PASSWORD})

    raw = client.get("/api/v1/admin/overview").text.lower()

    for secret in ("password_hash", "pbkdf2", "encrypted_access_token", PASSWORD):
        assert secret.lower() not in raw
    client.post("/api/v1/auth/logout")


def test_session_reports_admin_status(client, as_admin):
    from app.api.v1 import auth as auth_router

    # read_session builds the flag from its own module-level settings.
    original = auth_router.settings
    auth_router.settings = as_admin
    try:
        client.post(
            "/api/v1/auth/register",
            json={"name": "Boss", "email": ADMIN_EMAIL, "password": PASSWORD},
        )
        client.post("/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": PASSWORD})
        assert client.get("/api/v1/auth/session").json()["is_admin"] is True

        other = _unique_email()
        client.post(
            "/api/v1/auth/register",
            json={"name": "Regular", "email": other, "password": PASSWORD},
        )
        assert client.get("/api/v1/auth/session").json()["is_admin"] is False
    finally:
        auth_router.settings = original
        client.post("/api/v1/auth/logout")
