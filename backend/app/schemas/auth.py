"""Authentication request/response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class GitHubAuthStartRequest(BaseModel):
    redirect_path: str = Field(default="/dashboard", max_length=200)


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
    user: UserRead
    authenticated: bool = True
    github_connected: bool = False
    token: str | None = None


class DemoLoginResponse(SessionResponse):
    pass
