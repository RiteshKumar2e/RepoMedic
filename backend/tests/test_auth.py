"""Email/password registration, sign-in and session lifecycle."""

from __future__ import annotations

import uuid

import pytest

from app.core.security import hash_password, verify_password

PASSWORD = "correct-horse-9"


def _unique_email() -> str:
    return f"dev-{uuid.uuid4().hex[:12]}@example.com"


# --------------------------------------------------------------------------- #
# Hashing
# --------------------------------------------------------------------------- #
def test_password_hash_is_salted_and_verifiable():
    first = hash_password(PASSWORD)
    second = hash_password(PASSWORD)

    assert PASSWORD not in first
    assert first != second, "each hash must use a fresh salt"
    assert verify_password(PASSWORD, first)
    assert verify_password(PASSWORD, second)


@pytest.mark.parametrize(
    "password,stored",
    [
        ("wrong-password-1", hash_password(PASSWORD)),
        (PASSWORD, "not-a-hash"),
        (PASSWORD, ""),
        ("", hash_password(PASSWORD)),
    ],
)
def test_verify_password_rejects_bad_input(password, stored):
    assert verify_password(password, stored) is False


# --------------------------------------------------------------------------- #
# Registration
# --------------------------------------------------------------------------- #
def test_register_creates_account_and_signs_in(client):
    email = _unique_email()
    response = client.post(
        "/api/v1/auth/register",
        json={"name": "  Ada Lovelace  ", "email": email.upper(), "password": PASSWORD},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["user"]["name"] == "Ada Lovelace", "name should be trimmed"
    assert body["user"]["email"] == email, "email should be normalised to lower case"
    assert body["user"]["is_demo"] is False
    assert body["token"]
    assert "password" not in response.text.lower()

    session = client.get("/api/v1/auth/session")
    assert session.status_code == 200
    assert session.json()["user"]["email"] == email

    client.post("/api/v1/auth/logout")


def test_register_rejects_duplicate_email(client):
    email = _unique_email()
    payload = {"name": "First", "email": email, "password": PASSWORD}

    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    duplicate = client.post(
        "/api/v1/auth/register", json={**payload, "name": "Second"}
    )

    assert duplicate.status_code == 409
    client.post("/api/v1/auth/logout")


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "Weak", "email": "weak@example.com", "password": "short1"},
        {"name": "Weak", "email": "weak@example.com", "password": "no-digits-here"},
        {"name": "Weak", "email": "not-an-email", "password": PASSWORD},
        {"name": "   ", "email": "blank@example.com", "password": PASSWORD},
    ],
)
def test_register_rejects_invalid_input(client, payload):
    assert client.post("/api/v1/auth/register", json=payload).status_code == 422


# --------------------------------------------------------------------------- #
# Login
# --------------------------------------------------------------------------- #
def test_login_round_trip(client):
    email = _unique_email()
    client.post(
        "/api/v1/auth/register",
        json={"name": "Grace", "email": email, "password": PASSWORD},
    )
    client.post("/api/v1/auth/logout")

    response = client.post(
        "/api/v1/auth/login", json={"email": email.upper(), "password": PASSWORD}
    )

    assert response.status_code == 200, response.text
    assert response.json()["user"]["email"] == email
    assert client.get("/api/v1/auth/session").status_code == 200

    client.post("/api/v1/auth/logout")


@pytest.mark.parametrize("password", [PASSWORD + "x", "totally-wrong-1"])
def test_login_rejects_wrong_password(client, password):
    email = _unique_email()
    client.post(
        "/api/v1/auth/register",
        json={"name": "Alan", "email": email, "password": PASSWORD},
    )
    client.post("/api/v1/auth/logout")

    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})

    assert response.status_code == 401
    assert "email or password" in response.json()["error"]["message"].lower()


def test_login_does_not_disclose_whether_an_account_exists(client):
    unknown = client.post(
        "/api/v1/auth/login", json={"email": _unique_email(), "password": PASSWORD}
    )
    email = _unique_email()
    client.post(
        "/api/v1/auth/register",
        json={"name": "Known", "email": email, "password": PASSWORD},
    )
    client.post("/api/v1/auth/logout")
    known = client.post("/api/v1/auth/login", json={"email": email, "password": "wrong-pass-1"})

    assert unknown.status_code == known.status_code == 401
    assert unknown.json()["error"]["message"] == known.json()["error"]["message"]


def test_demo_user_cannot_be_signed_into_with_a_password(client):
    """The seeded demo account has no password hash, so it must never match."""
    client.post("/api/v1/auth/demo")
    client.post("/api/v1/auth/logout")

    response = client.post(
        "/api/v1/auth/login", json={"email": "demo@repomedic.dev", "password": PASSWORD}
    )

    assert response.status_code == 401


# --------------------------------------------------------------------------- #
# Session lifecycle
# --------------------------------------------------------------------------- #
def test_logout_clears_the_session(client):
    email = _unique_email()
    client.post(
        "/api/v1/auth/register",
        json={"name": "Katherine", "email": email, "password": PASSWORD},
    )
    assert client.get("/api/v1/auth/session").status_code == 200

    assert client.post("/api/v1/auth/logout").status_code == 200
    assert client.get("/api/v1/auth/session").status_code == 401


def test_session_requires_authentication(client):
    client.post("/api/v1/auth/logout")
    assert client.get("/api/v1/auth/session").status_code == 401
