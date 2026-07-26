"""Persistent entities.

Design notes
------------
* Primary keys are UUID4 strings — portable across SQLite/libSQL/Postgres and
  safe to expose in URLs.
* Repository source code is **never** stored here. Only metadata, findings and
  the small code excerpts needed to render a patch.
* Every foreign key declares ``ondelete`` so deleting a repository tears down
  its whole analysis history deterministically.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import JSON, Column, ForeignKey, String, Text, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from app.models.enums import (
    AnalysisStatus,
    FindingCategory,
    FindingSource,
    FindingStatus,
    PatchStatus,
    PullRequestStatus,
    RiskLevel,
    Severity,
    ValidationStatus,
)


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _fk(target: str, nullable: bool = False) -> Column:
    return Column(String, ForeignKey(target, ondelete="CASCADE"), nullable=nullable, index=True)


# --------------------------------------------------------------------------- #
# Identity
# --------------------------------------------------------------------------- #
class User(SQLModel, table=True):
    __tablename__ = "users"

    id: str = Field(default_factory=new_id, primary_key=True)
    github_user_id: Optional[int] = Field(default=None, index=True, unique=True)
    login: Optional[str] = Field(default=None, index=True)
    name: Optional[str] = None
    email: Optional[str] = Field(default=None, index=True)
    avatar_url: Optional[str] = None
    is_demo: bool = Field(default=False, index=True)
    created_at: datetime = Field(default_factory=utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=utcnow, nullable=False)

    installations: list["GitHubInstallation"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class GitHubInstallation(SQLModel, table=True):
    __tablename__ = "github_installations"

    id: str = Field(default_factory=new_id, primary_key=True)
    user_id: str = Field(sa_column=_fk("users.id"))
    installation_id: Optional[int] = Field(default=None, index=True)
    account_login: Optional[str] = None
    account_type: Optional[str] = None
    # Fernet ciphertext — plaintext tokens never touch the database.
    encrypted_access_token: str = Field(default="", sa_column=Column(Text, nullable=False, default=""))
    token_expires_at: Optional[datetime] = None
    scopes: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=utcnow, nullable=False)

    user: Optional[User] = Relationship(back_populates="installations")
    repositories: list["Repository"] = Relationship(
        back_populates="installation",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


# --------------------------------------------------------------------------- #
# Repositories & pull requests
# --------------------------------------------------------------------------- #
class Repository(SQLModel, table=True):
    __tablename__ = "repositories"
    __table_args__ = (
        UniqueConstraint("installation_id", "github_repository_id", name="uq_repo_per_installation"),
    )

    id: str = Field(default_factory=new_id, primary_key=True)
    installation_id: str = Field(sa_column=_fk("github_installations.id"))
    github_repository_id: int = Field(index=True)
    owner: str = Field(index=True)
    name: str = Field(index=True)
    full_name: str = Field(index=True)
    description: Optional[str] = None
    default_branch: str = "main"
    primary_language: Optional[str] = None
    languages: dict[str, int] = Field(default_factory=dict, sa_column=Column(JSON))
    is_private: bool = True
    html_url: Optional[str] = None
    clone_url: Optional[str] = None
    stars: int = 0
    open_pr_count: int = 0
    last_analyzed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=utcnow, nullable=False)

    installation: Optional[GitHubInstallation] = Relationship(back_populates="repositories")
    pull_requests: list["PullRequest"] = Relationship(
        back_populates="repository",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    settings: Optional["RepositorySettings"] = Relationship(
        back_populates="repository",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "uselist": False},
    )


class PullRequest(SQLModel, table=True):
    __tablename__ = "pull_requests"
    __table_args__ = (
        UniqueConstraint("repository_id", "github_pr_number", name="uq_pr_per_repo"),
    )

    id: str = Field(default_factory=new_id, primary_key=True)
    repository_id: str = Field(sa_column=_fk("repositories.id"))
    github_pr_number: int = Field(index=True)
    title: str
    body: Optional[str] = Field(default=None, sa_column=Column(Text))
    base_ref: str = "main"
    head_ref: str = ""
    base_sha: str = ""
    head_sha: str = ""
    author: str = ""
    author_avatar_url: Optional[str] = None
    status: PullRequestStatus = Field(default=PullRequestStatus.OPEN, index=True)
    is_draft: bool = False
    additions: int = 0
    deletions: int = 0
    changed_files: int = 0
    html_url: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=utcnow, nullable=False)

    repository: Optional[Repository] = Relationship(back_populates="pull_requests")
    analyses: list["Analysis"] = Relationship(
        back_populates="pull_request",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


# --------------------------------------------------------------------------- #
# Analyses, findings, patches
# --------------------------------------------------------------------------- #
class Analysis(SQLModel, table=True):
    __tablename__ = "analyses"

    id: str = Field(default_factory=new_id, primary_key=True)
    pull_request_id: str = Field(sa_column=_fk("pull_requests.id"))
    status: AnalysisStatus = Field(default=AnalysisStatus.QUEUED, index=True)
    stage: str = "queued"
    progress: int = 0
    model_provider: Optional[str] = None
    model_name: Optional[str] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    token_usage: int = 0
    estimated_cost: float = 0.0
    files_analyzed: int = 0
    scanners_run: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    reviewers_run: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    stage_timings: dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    context_manifest: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    graph_snapshot: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    summary: Optional[str] = Field(default=None, sa_column=Column(Text))
    triggered_by: str = "manual"
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    error_message: Optional[str] = Field(default=None, sa_column=Column(Text))
    created_at: datetime = Field(default_factory=utcnow, nullable=False)

    pull_request: Optional[PullRequest] = Relationship(back_populates="analyses")
    findings: list["Finding"] = Relationship(
        back_populates="analysis",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class Finding(SQLModel, table=True):
    __tablename__ = "findings"
    __table_args__ = (
        UniqueConstraint("analysis_id", "fingerprint", name="uq_finding_fingerprint"),
    )

    id: str = Field(default_factory=new_id, primary_key=True)
    analysis_id: str = Field(sa_column=_fk("analyses.id"))
    category: FindingCategory = Field(index=True)
    severity: Severity = Field(index=True)
    confidence: float = 0.0
    score: float = 0.0
    title: str
    description: str = Field(default="", sa_column=Column(Text))
    risk: str = Field(default="", sa_column=Column(Text))
    recommendation: str = Field(default="", sa_column=Column(Text))
    file_path: str = Field(index=True)
    start_line: int = 1
    end_line: int = 1
    code_snippet: str = Field(default="", sa_column=Column(Text))
    source: FindingSource = Field(index=True)
    corroborating_sources: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    rule_id: Optional[str] = Field(default=None, index=True)
    cwe: Optional[str] = None
    fingerprint: str = Field(index=True)
    status: FindingStatus = Field(default=FindingStatus.OPEN, index=True)
    related_files: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    score_breakdown: dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow, nullable=False)

    analysis: Optional[Analysis] = Relationship(back_populates="findings")
    patches: list["Patch"] = Relationship(
        back_populates="finding",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    comments: list["ReviewComment"] = Relationship(
        back_populates="finding",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class Patch(SQLModel, table=True):
    __tablename__ = "patches"

    id: str = Field(default_factory=new_id, primary_key=True)
    finding_id: str = Field(sa_column=_fk("findings.id"))
    file_path: str = ""
    original_code: str = Field(default="", sa_column=Column(Text))
    suggested_code: str = Field(default="", sa_column=Column(Text))
    unified_diff: str = Field(default="", sa_column=Column(Text))
    explanation: str = Field(default="", sa_column=Column(Text))
    expected_impact: str = Field(default="", sa_column=Column(Text))
    side_effects: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    confidence: float = 0.0
    confidence_breakdown: dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    risk_level: RiskLevel = Field(default=RiskLevel.MEDIUM, index=True)
    status: PatchStatus = Field(default=PatchStatus.PROPOSED, index=True)
    validation_status: ValidationStatus = Field(default=ValidationStatus.PENDING, index=True)
    auto_apply_eligible: bool = False
    generated_by: str = "fix_generator"
    approved_at: Optional[datetime] = None
    approved_by: Optional[str] = None
    rejected_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    applied_commit_sha: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow, nullable=False)

    finding: Optional[Finding] = Relationship(back_populates="patches")
    validation_runs: list["ValidationRun"] = Relationship(
        back_populates="patch",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class ValidationRun(SQLModel, table=True):
    __tablename__ = "validation_runs"

    id: str = Field(default_factory=new_id, primary_key=True)
    patch_id: str = Field(sa_column=_fk("patches.id"))
    parser_passed: Optional[bool] = None
    lint_passed: Optional[bool] = None
    typecheck_passed: Optional[bool] = None
    tests_passed: Optional[bool] = None
    security_scan_passed: Optional[bool] = None
    semantic_similarity: float = 0.0
    tests_before: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    tests_after: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    step_results: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    test_output: str = Field(default="", sa_column=Column(Text))
    skipped_reason: Optional[str] = None
    execution_time: float = 0.0
    created_at: datetime = Field(default_factory=utcnow, nullable=False)

    patch: Optional[Patch] = Relationship(back_populates="validation_runs")


class ReviewComment(SQLModel, table=True):
    __tablename__ = "review_comments"

    id: str = Field(default_factory=new_id, primary_key=True)
    finding_id: str = Field(sa_column=_fk("findings.id"))
    github_comment_id: Optional[int] = Field(default=None, index=True)
    body: str = Field(default="", sa_column=Column(Text))
    html_url: Optional[str] = None
    posted_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utcnow, nullable=False)

    finding: Optional[Finding] = Relationship(back_populates="comments")


# --------------------------------------------------------------------------- #
# Configuration & audit
# --------------------------------------------------------------------------- #
class RepositorySettings(SQLModel, table=True):
    __tablename__ = "repository_settings"
    __table_args__ = (UniqueConstraint("repository_id", name="uq_settings_per_repo"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    repository_id: str = Field(sa_column=_fk("repositories.id"))
    enabled_reviewers: list[str] = Field(
        default_factory=lambda: ["architecture", "security", "performance", "reliability", "testing"],
        sa_column=Column(JSON),
    )
    enabled_scanners: list[str] = Field(
        default_factory=lambda: ["ruff", "bandit", "mypy", "semgrep", "eslint", "tsc", "gitleaks", "osv", "npm_audit"],
        sa_column=Column(JSON),
    )
    severity_threshold: Severity = Field(default=Severity.LOW)
    auto_scan_enabled: bool = True
    auto_apply_enabled: bool = False  # Security default: humans approve every patch.
    preferred_llm_provider: Optional[str] = None
    preferred_llm_model: Optional[str] = None
    max_analysis_cost: float = 2.0
    excluded_paths: list[str] = Field(
        default_factory=lambda: ["node_modules/**", "dist/**", "build/**", "**/*.min.js", ".venv/**"],
        sa_column=Column(JSON),
    )
    custom_rules: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    notification_settings: dict[str, Any] = Field(
        default_factory=lambda: {"on_analysis_complete": True, "on_critical_finding": True},
        sa_column=Column(JSON),
    )
    data_retention_minutes: int = 60
    created_at: datetime = Field(default_factory=utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=utcnow, nullable=False)

    repository: Optional[Repository] = Relationship(back_populates="settings")


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_logs"

    id: str = Field(default_factory=new_id, primary_key=True)
    user_id: Optional[str] = Field(
        default=None,
        sa_column=Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True),
    )
    action: str = Field(index=True)
    entity_type: str = Field(index=True)
    entity_id: Optional[str] = Field(default=None, index=True)
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    ip_address: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow, nullable=False, index=True)
