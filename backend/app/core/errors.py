"""Domain exceptions mapped to HTTP responses by a single handler in main.py."""

from __future__ import annotations

from typing import Any


class RepoMedicError(Exception):
    """Base error carrying an HTTP status and a machine-readable code."""

    status_code = 500
    code = "internal_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_payload(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class NotFoundError(RepoMedicError):
    status_code = 404
    code = "not_found"


class ValidationError(RepoMedicError):
    status_code = 422
    code = "validation_error"


class AuthenticationError(RepoMedicError):
    status_code = 401
    code = "unauthenticated"


class AuthorizationError(RepoMedicError):
    status_code = 403
    code = "forbidden"


class ConflictError(RepoMedicError):
    status_code = 409
    code = "conflict"


class RateLimitError(RepoMedicError):
    status_code = 429
    code = "rate_limited"


class ExternalServiceError(RepoMedicError):
    status_code = 502
    code = "upstream_error"


class BudgetExceededError(RepoMedicError):
    status_code = 402
    code = "budget_exceeded"


class SandboxError(RepoMedicError):
    status_code = 500
    code = "sandbox_error"
