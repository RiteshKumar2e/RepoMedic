"""Repository, settings and pull-request schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from app.models.enums import PullRequestStatus, Severity


class RepositoryRead(BaseModel):
    id: str
    github_repository_id: int
    owner: str
    name: str
    full_name: str
    description: Optional[str] = None
    default_branch: str
    primary_language: Optional[str] = None
    languages: dict[str, int] = Field(default_factory=dict)
    is_private: bool
    html_url: Optional[str] = None
    stars: int = 0
    open_pr_count: int = 0
    last_analyzed_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PullRequestRead(BaseModel):
    id: str
    repository_id: str
    github_pr_number: int
    title: str
    body: Optional[str] = None
    base_ref: str
    head_ref: str
    base_sha: str
    head_sha: str
    author: str
    author_avatar_url: Optional[str] = None
    status: PullRequestStatus
    is_draft: bool = False
    additions: int = 0
    deletions: int = 0
    changed_files: int = 0
    html_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PullRequestDetail(PullRequestRead):
    repository: Optional[RepositoryRead] = None
    latest_analysis_id: Optional[str] = None
    analysis_count: int = 0


class CustomRule(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=500)
    pattern: Optional[str] = Field(default=None, max_length=500)
    severity: Severity = Severity.MEDIUM
    languages: list[str] = Field(default_factory=list)
    enabled: bool = True


class RepositorySettingsRead(BaseModel):
    id: str
    repository_id: str
    enabled_reviewers: list[str]
    enabled_scanners: list[str]
    severity_threshold: Severity
    auto_scan_enabled: bool
    auto_apply_enabled: bool
    preferred_llm_provider: Optional[str] = None
    preferred_llm_model: Optional[str] = None
    max_analysis_cost: float
    excluded_paths: list[str]
    custom_rules: list[dict[str, Any]] = Field(default_factory=list)
    notification_settings: dict[str, Any] = Field(default_factory=dict)
    data_retention_minutes: int
    updated_at: datetime

    model_config = {"from_attributes": True}


class RepositorySettingsUpdate(BaseModel):
    enabled_reviewers: Optional[list[str]] = None
    enabled_scanners: Optional[list[str]] = None
    severity_threshold: Optional[Severity] = None
    auto_scan_enabled: Optional[bool] = None
    auto_apply_enabled: Optional[bool] = None
    preferred_llm_provider: Optional[str] = None
    preferred_llm_model: Optional[str] = None
    max_analysis_cost: Optional[float] = Field(default=None, ge=0, le=100)
    excluded_paths: Optional[list[str]] = None
    custom_rules: Optional[list[CustomRule]] = None
    notification_settings: Optional[dict[str, Any]] = None
    data_retention_minutes: Optional[int] = Field(default=None, ge=0, le=10080)

    @field_validator("excluded_paths")
    @classmethod
    def _no_absolute_paths(cls, value: Optional[list[str]]) -> Optional[list[str]]:
        if value is None:
            return value
        for pattern in value:
            if pattern.startswith("/") or ".." in pattern:
                raise ValueError("Excluded paths must be repository-relative glob patterns")
        return value
