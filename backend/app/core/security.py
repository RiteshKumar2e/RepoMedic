"""Token encryption, session JWTs, OAuth state, and webhook signature checks."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

_ALGORITHM = "HS256"


# --------------------------------------------------------------------------- #
# Token encryption at rest
# --------------------------------------------------------------------------- #
def _fernet() -> Fernet:
    key = settings.effective_encryption_key
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except (ValueError, TypeError) as exc:  # pragma: no cover - misconfiguration
        raise RuntimeError(
            "ENCRYPTION_KEY must be a urlsafe base64-encoded 32-byte Fernet key"
        ) from exc


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a credential for storage. Empty input stays empty."""
    if not plaintext:
        return ""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    if not ciphertext:
        return ""
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Stored credential could not be decrypted") from exc


# --------------------------------------------------------------------------- #
# Account passwords
#
# PBKDF2-HMAC-SHA256 from the standard library: no extra dependency to install,
# which keeps the offline-first promise intact. Iterations follow the OWASP
# recommendation and are stored per-hash so the cost can be raised later
# without invalidating existing credentials.
# --------------------------------------------------------------------------- #
_PBKDF2_ALGORITHM = "pbkdf2_sha256"
_PBKDF2_ITERATIONS = 600_000
_SALT_BYTES = 16


def hash_password(password: str) -> str:
    """Return ``pbkdf2_sha256$iterations$salt$hash`` — safe to store verbatim."""
    if not password:
        raise ValueError("Password must not be empty")
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERATIONS)
    return "$".join(
        (
            _PBKDF2_ALGORITHM,
            str(_PBKDF2_ITERATIONS),
            base64.urlsafe_b64encode(salt).decode(),
            base64.urlsafe_b64encode(digest).decode(),
        )
    )


def verify_password(password: str, stored_hash: str) -> bool:
    """Constant-time check. Any malformed or absent hash simply fails."""
    if not password or not stored_hash:
        return False
    try:
        algorithm, iterations, salt_b64, digest_b64 = stored_hash.split("$", 3)
        if algorithm != _PBKDF2_ALGORITHM:
            return False
        salt = base64.urlsafe_b64decode(salt_b64)
        expected = base64.urlsafe_b64decode(digest_b64)
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(iterations))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate, expected)


# --------------------------------------------------------------------------- #
# Session JWTs
# --------------------------------------------------------------------------- #
def create_session_token(user_id: str, extra: dict[str, Any] | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": user_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_expire_minutes)).timestamp()),
        "iss": settings.app_name,
        "jti": secrets.token_urlsafe(12),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.effective_jwt_secret, algorithm=_ALGORITHM)


def decode_session_token(token: str) -> dict[str, Any]:
    return jwt.decode(
        token,
        settings.effective_jwt_secret,
        algorithms=[_ALGORITHM],
        issuer=settings.app_name,
        options={"require": ["exp", "sub"]},
    )


# --------------------------------------------------------------------------- #
# OAuth state (signed + time-limited, so no server-side session store is needed)
# --------------------------------------------------------------------------- #
_STATE_TTL_SECONDS = 600


def create_oauth_state(redirect_path: str = "/dashboard") -> str:
    nonce = secrets.token_urlsafe(16)
    issued = int(time.time())
    payload = f"{nonce}.{issued}.{redirect_path}"
    signature = hmac.new(
        settings.effective_jwt_secret.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    raw = f"{payload}.{signature}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def verify_oauth_state(state: str) -> str:
    """Return the redirect path if the state is authentic and unexpired."""
    try:
        padding = "=" * (-len(state) % 4)
        raw = base64.urlsafe_b64decode(state + padding).decode()
        nonce, issued, redirect_path, signature = raw.split(".", 3)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("Malformed OAuth state") from exc

    payload = f"{nonce}.{issued}.{redirect_path}"
    expected = hmac.new(
        settings.effective_jwt_secret.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise ValueError("OAuth state signature mismatch")
    if int(time.time()) - int(issued) > _STATE_TTL_SECONDS:
        raise ValueError("OAuth state expired")
    # Only allow same-site relative redirects — blocks open-redirect abuse.
    if not redirect_path.startswith("/") or redirect_path.startswith("//"):
        return "/dashboard"
    return redirect_path


# --------------------------------------------------------------------------- #
# GitHub webhook signatures
# --------------------------------------------------------------------------- #
def verify_webhook_signature(body: bytes, signature_header: str | None) -> bool:
    """Constant-time validation of the ``X-Hub-Signature-256`` header."""
    secret = settings.github_webhook_secret
    if not secret or not signature_header:
        return False
    if not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header[len("sha256=") :])


# --------------------------------------------------------------------------- #
# GitHub App JWT (used to mint installation tokens)
# --------------------------------------------------------------------------- #
def create_github_app_jwt() -> str:
    if not settings.github_app_configured:
        raise RuntimeError("GITHUB_APP_ID and GITHUB_PRIVATE_KEY are not configured")
    now = int(time.time())
    payload = {"iat": now - 60, "exp": now + 540, "iss": settings.github_app_id}
    private_key = settings.github_private_key.replace("\\n", "\n")
    return jwt.encode(payload, private_key, algorithm="RS256")


def constant_time_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)
