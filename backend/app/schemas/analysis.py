"""Analysis, finding, patch and validation schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import (
    AnalysisStatus,
    FindingCategory,
    FindingSource,
    FindingStatus,
    PatchStatus,
    RiskLevel,
    Severity,
    ValidationStatus,
)


class AnalyzeRequest(BaseModel):
    force: bool = False
    reviewers: list[str] | None = None
    generate_patches: bool = True


class AnalysisRead(BaseModel):
    id: str
    pull_request_id: str
    status: AnalysisStatus
    stage: str
    progress: int
    model_provider: str | None = None
    model_name: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    token_usage: int = 0
    estimated_cost: float = 0.0
    files_analyzed: int = 0
    scanners_run: list[str] = Field(default_factory=list)
    reviewers_run: list[str] = Field(default_factory=list)
    stage_timings: dict[str, float] = Field(default_factory=dict)
    context_manifest: dict[str, Any] = Field(default_factory=dict)
    summary: str | None = None
    triggered_by: str = "manual"
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    error_message: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AnalysisSummary(BaseModel):
    """Aggregate counters rendered on the analysis header."""

    total_findings: int = 0
    by_severity: dict[str, int] = Field(default_factory=dict)
    by_category: dict[str, int] = Field(default_factory=dict)
    by_source: dict[str, int] = Field(default_factory=dict)
    patches_proposed: int = 0
    patches_validated: int = 0
    patches_approved: int = 0
    files_with_findings: int = 0


class AnalysisDetail(AnalysisRead):
    summary_stats: AnalysisSummary = Field(default_factory=AnalysisSummary)


class ValidationRunRead(BaseModel):
    id: str
    patch_id: str
    parser_passed: bool | None = None
    lint_passed: bool | None = None
    typecheck_passed: bool | None = None
    tests_passed: bool | None = None
    security_scan_passed: bool | None = None
    semantic_similarity: float = 0.0
    tests_before: dict[str, Any] = Field(default_factory=dict)
    tests_after: dict[str, Any] = Field(default_factory=dict)
    step_results: list[dict[str, Any]] = Field(default_factory=list)
    test_output: str = ""
    skipped_reason: str | None = None
    execution_time: float = 0.0
    created_at: datetime

    model_config = {"from_attributes": True}


class PatchRead(BaseModel):
    id: str
    finding_id: str
    file_path: str
    original_code: str
    suggested_code: str
    unified_diff: str
    explanation: str
    expected_impact: str
    side_effects: list[str] = Field(default_factory=list)
    confidence: float
    confidence_breakdown: dict[str, float] = Field(default_factory=dict)
    risk_level: RiskLevel
    status: PatchStatus
    validation_status: ValidationStatus
    auto_apply_eligible: bool
    generated_by: str
    approved_at: datetime | None = None
    rejected_at: datetime | None = None
    rejection_reason: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PatchDetail(PatchRead):
    validation_runs: list[ValidationRunRead] = Field(default_factory=list)
    finding: FindingRead | None = None


class FindingRead(BaseModel):
    id: str
    analysis_id: str
    category: FindingCategory
    severity: Severity
    confidence: float
    score: float
    title: str
    description: str
    risk: str
    recommendation: str
    file_path: str
    start_line: int
    end_line: int
    code_snippet: str = ""
    source: FindingSource
    corroborating_sources: list[str] = Field(default_factory=list)
    rule_id: str | None = None
    cwe: str | None = None
    fingerprint: str
    status: FindingStatus
    related_files: list[str] = Field(default_factory=list)
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    created_at: datetime

    model_config = {"from_attributes": True}


class FindingDetail(FindingRead):
    patches: list[PatchRead] = Field(default_factory=list)


class RejectPatchRequest(BaseModel):
    reason: str = Field(default="", max_length=500)


class PublishReviewRequest(BaseModel):
    min_severity: Severity = Severity.MEDIUM
    include_inline_comments: bool = True
    dry_run: bool = False


class PublishReviewResponse(BaseModel):
    posted: bool
    summary_comment_url: str | None = None
    inline_comments: int = 0
    dry_run_body: str | None = None


class CreateFixPRRequest(BaseModel):
    patch_ids: list[str] | None = None
    branch_name: str | None = Field(default=None, max_length=200)
    title: str | None = Field(default=None, max_length=200)
    dry_run: bool = False


class CreateFixPRResponse(BaseModel):
    created: bool
    branch: str
    pull_request_url: str | None = None
    pull_request_number: int | None = None
    applied_patches: list[str] = Field(default_factory=list)
    skipped_patches: list[dict[str, str]] = Field(default_factory=list)
    dry_run_diff: str | None = None


PatchDetail.model_rebuild()
