"""Typed application settings loaded from the environment.

Every runtime knob lives here so services never read ``os.environ`` directly.
"""

from __future__ import annotations

import base64
import hashlib
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _as_fernet_key(raw: str) -> str:
    """Return a valid Fernet key for ``raw``.

    Fernet only accepts urlsafe-base64 of exactly 32 bytes. A secret generated
    the way JWT_SECRET is (``openssl rand -hex 32``) has the right entropy but
    the wrong encoding, so derive a key from it instead of failing at the first
    token write. Derivation is deterministic: the same secret always yields the
    same key, so tokens already at rest stay readable.
    """
    candidate = raw.strip()
    try:
        if len(base64.urlsafe_b64decode(candidate)) == 32:
            return candidate
    except ValueError:  # not base64 at all
        pass
    return base64.urlsafe_b64encode(hashlib.sha256(candidate.encode()).digest()).decode()


class SandboxMode(str, Enum):
    DOCKER = "docker"
    SUBPROCESS = "subprocess"
    DISABLED = "disabled"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- Application -----------------------------------------------------
    app_env: Literal["development", "test", "staging", "production"] = "development"
    app_name: str = "RepoMedic"
    app_url: str = "http://localhost:3000"
    api_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:3000"
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"
    demo_mode: bool = True

    # ---- Database --------------------------------------------------------
    database_url: str = ""
    database_auth_token: str = ""

    # ---- Secrets ---------------------------------------------------------
    jwt_secret: str = ""
    encryption_key: str = ""
    jwt_expire_minutes: int = 720
    cookie_name: str = "repomedic_session"
    cookie_secure: bool = False
    cookie_domain: str = ""

    # ---- GitHub ----------------------------------------------------------
    github_client_id: str = ""
    github_client_secret: str = ""
    github_oauth_scopes: str = "read:user,user:email,repo"
    github_app_id: str = ""
    github_private_key: str = ""
    github_webhook_secret: str = ""
    github_api_url: str = "https://api.github.com"

    # ---- LLM -------------------------------------------------------------
    gemini_api_key: str = ""
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    groq_api_key: str = ""
    local_llm_base_url: str = "http://localhost:11434/v1"
    default_llm_provider: str = "heuristic"
    default_llm_model: str = "gemini-2.5-flash"

    # ---- Queue -----------------------------------------------------------
    redis_url: str = ""

    # ---- Workspace / budgets --------------------------------------------
    workspace_root: str = "./.workspaces"
    max_repository_size_mb: int = 200
    workspace_retention_minutes: int = 60
    max_analysis_cost_usd: float = 2.0
    max_context_files: int = 24
    max_context_tokens: int = 60_000
    agent_max_steps: int = 12

    # ---- Sandbox ---------------------------------------------------------
    sandbox_mode: SandboxMode = SandboxMode.SUBPROCESS
    sandbox_image: str = "repomedic/sandbox:latest"
    sandbox_cpu_limit: str = "1.0"
    sandbox_memory_limit: str = "1g"
    scanner_timeout_seconds: int = 120
    allow_host_test_execution: bool = False

    # ---- Rate limiting ---------------------------------------------------
    rate_limit_requests: int = 120
    rate_limit_window_seconds: int = 60

    @field_validator("frontend_url", "app_url", "api_url", mode="before")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        return str(value).rstrip("/")

    # ---- Derived helpers -------------------------------------------------
    @property
    def is_production(self) -> bool:
        return self.app_env in ("production", "staging")

    @property
    def cors_origins(self) -> list[str]:
        """Strict allowlist — the browser origins permitted to call the API."""
        origins = {self.frontend_url, self.app_url}
        return sorted(o for o in origins if o)

    @property
    def workspace_path(self) -> Path:
        raw = Path(self.workspace_root)
        path = raw if raw.is_absolute() else (BACKEND_ROOT / raw)
        return path.resolve()

    @property
    def sqlalchemy_url(self) -> str:
        """Resolve the SQLAlchemy URL, defaulting to a local SQLite file.

        Turso is addressed through the ``sqlite+libsql`` dialect; the auth token
        travels as a query parameter, which is what ``sqlalchemy-libsql`` expects.
        """
        url = self.database_url.strip()
        if not url:
            data_dir = BACKEND_ROOT / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            return f"sqlite:///{(data_dir / 'repomedic.db').as_posix()}"

        # Route Turso through the HTTP-transport dialect in app/db/libsql_dialect.py.
        # The stock sqlite+libsql driver only speaks WebSocket, which Turso now
        # rejects with a 400 handshake.
        for prefix in ("libsql://", "sqlite+libsql://"):
            if url.startswith(prefix):
                url = "sqlite+libsql_http://" + url[len(prefix) :]
                break

        if url.startswith("sqlite+libsql_http://") and self.database_auth_token:
            joiner = "&" if "?" in url else "?"
            url = f"{url}{joiner}authToken={self.database_auth_token}"
        return url

    @property
    def is_turso(self) -> bool:
        return "libsql" in self.sqlalchemy_url

    @property
    def effective_jwt_secret(self) -> str:
        if self.jwt_secret:
            return self.jwt_secret
        if self.is_production:
            raise RuntimeError("JWT_SECRET must be set outside development")
        # Deterministic dev-only secret so local restarts do not invalidate sessions.
        return hashlib.sha256(b"repomedic-development-jwt-secret").hexdigest()

    @property
    def effective_encryption_key(self) -> str:
        if self.encryption_key:
            return _as_fernet_key(self.encryption_key)
        if self.is_production:
            raise RuntimeError("ENCRYPTION_KEY must be set outside development")
        digest = hashlib.sha256(b"repomedic-development-encryption-key").digest()
        return base64.urlsafe_b64encode(digest).decode()

    @property
    def github_oauth_configured(self) -> bool:
        return bool(self.github_client_id and self.github_client_secret)

    @property
    def github_app_configured(self) -> bool:
        return bool(self.github_app_id and self.github_private_key)

    @property
    def github_scope_list(self) -> list[str]:
        return [s.strip() for s in self.github_oauth_scopes.split(",") if s.strip()]

    def llm_api_key(self, provider: str) -> str:
        return {
            "gemini": self.gemini_api_key,
            "groq": self.groq_api_key,
            "local": "local",
            "heuristic": "heuristic",
        }.get(provider, "")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
