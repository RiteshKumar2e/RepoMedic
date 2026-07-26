"""Dashboard and analytics response schemas."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class SeverityCount(BaseModel):
    severity: str
    count: int


class CategoryCount(BaseModel):
    category: str
    count: int


class TrendPoint(BaseModel):
    date: str
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    informational: int = 0
    total: int = 0


class RiskyModule(BaseModel):
    file_path: str
    finding_count: int
    max_severity: str
    score: float


class ActivityItem(BaseModel):
    id: str
    action: str
    entity_type: str
    entity_id: Optional[str] = None
    summary: str
    created_at: str


class DashboardResponse(BaseModel):
    repository_count: int = 0
    open_pull_requests: int = 0
    active_analyses: int = 0
    total_findings: int = 0
    findings_by_severity: list[SeverityCount] = Field(default_factory=list)
    fix_acceptance_rate: float = 0.0
    average_review_seconds: float = 0.0
    patches_pending_review: int = 0
    recent_activity: list[ActivityItem] = Field(default_factory=list)
    trend: list[TrendPoint] = Field(default_factory=list)


class RepositoryAnalyticsResponse(BaseModel):
    repository_id: str
    analyses_run: int = 0
    total_findings: int = 0
    findings_by_severity: list[SeverityCount] = Field(default_factory=list)
    findings_by_category: list[CategoryCount] = Field(default_factory=list)
    findings_by_source: list[CategoryCount] = Field(default_factory=list)
    fix_acceptance_rate: float = 0.0
    average_review_seconds: float = 0.0
    defect_trend: list[TrendPoint] = Field(default_factory=list)
    riskiest_modules: list[RiskyModule] = Field(default_factory=list)
    security_posture_score: float = 0.0
    language_distribution: dict[str, int] = Field(default_factory=dict)
    total_estimated_cost: float = 0.0
