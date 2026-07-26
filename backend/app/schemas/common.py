"""Envelope and utility schemas shared by every endpoint."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorDetail


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int = 1
    page_size: int = 50

    @property
    def pages(self) -> int:
        return max(1, -(-self.total // self.page_size))


class Acknowledgement(BaseModel):
    ok: bool = True
    message: str = ""


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    database: str
    queue: str
    llm_provider: str
    demo_mode: bool
    sandbox_mode: str
    github_oauth_configured: bool
    github_app_configured: bool
