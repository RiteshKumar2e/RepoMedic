"""Cross-tenant administration views.

These are the only schemas in the project that deliberately cross account
boundaries, so they carry identifying data. They expose metadata only — never
repository source, tokens or password hashes.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AdminTotals(BaseModel):
    users: int = 0
    repositories: int = 0
    analyses: int = 0
    findings: int = 0
    patches: int = 0
    pull_requests: int = 0


class AdminUserRow(BaseModel):
    id: str
    login: str | None = None
    name: str | None = None
    email: str | None = None
    avatar_url: str | None = None
    # How the account signs in — a GitHub id, a password hash, or neither.
    auth_method: str = "unknown"
    github_connected: bool = False
    repository_count: int = 0
    analysis_count: int = 0
    is_admin: bool = False
    created_at: datetime


class AdminRepositoryRow(BaseModel):
    id: str
    full_name: str
    owner_login: str | None = None
    owner_email: str | None = None
    primary_language: str | None = None
    is_private: bool = False
    open_pr_count: int = 0
    analysis_count: int = 0
    finding_count: int = 0
    last_analyzed_at: datetime | None = None
    created_at: datetime


class AdminAnalysisRow(BaseModel):
    id: str
    repository_full_name: str | None = None
    pull_request_number: int | None = None
    status: str
    stage: str
    triggered_by: str
    finding_count: int = 0
    duration_seconds: float | None = None
    estimated_cost: float = 0.0
    created_at: datetime


class SeverityBreakdown(BaseModel):
    severity: str
    count: int


class CategoryBreakdown(BaseModel):
    category: str
    count: int


class AdminFindingStats(BaseModel):
    total: int = 0
    by_severity: list[SeverityBreakdown] = Field(default_factory=list)
    by_category: list[CategoryBreakdown] = Field(default_factory=list)
    patches_proposed: int = 0
    patches_approved: int = 0
    patches_rejected: int = 0
    fix_acceptance_rate: float = 0.0


class AdminAuditRow(BaseModel):
    id: str
    action: str
    entity_type: str
    entity_id: str | None = None
    actor_login: str | None = None
    actor_email: str | None = None
    ip_address: str | None = None
    created_at: datetime


class AdminOverview(BaseModel):
    totals: AdminTotals
    users: list[AdminUserRow] = Field(default_factory=list)
    repositories: list[AdminRepositoryRow] = Field(default_factory=list)
    analyses: list[AdminAnalysisRow] = Field(default_factory=list)
    findings: AdminFindingStats = Field(default_factory=AdminFindingStats)
    audit: list[AdminAuditRow] = Field(default_factory=list)
