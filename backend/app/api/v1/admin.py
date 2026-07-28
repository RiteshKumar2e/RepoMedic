"""Cross-tenant administration.

Every other router scopes reads to the calling user. These endpoints
deliberately do not, so all of them sit behind :data:`AdminUser`, which grants
access from the ADMIN_EMAILS allowlist rather than anything a user controls.

Metadata only: no repository source, no tokens, no password hashes.
"""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Query
from sqlmodel import Session, func, select

from app.api.deps import AdminUser, SessionDep
from app.core.config import settings
from app.core.logging import get_logger
from app.models.entities import (
    Analysis,
    AuditLog,
    Finding,
    GitHubInstallation,
    Patch,
    PullRequest,
    Repository,
    User,
)
from app.models.enums import PatchStatus
from app.schemas.admin import (
    AdminAnalysisRow,
    AdminAuditRow,
    AdminFindingStats,
    AdminOverview,
    AdminRepositoryRow,
    AdminTotals,
    AdminUserRow,
    CategoryBreakdown,
    SeverityBreakdown,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


def _count(session: Session, model) -> int:
    return session.exec(select(func.count()).select_from(model)).one()


def _build_users(session: Session, limit: int) -> list[AdminUserRow]:
    users = list(
        session.exec(select(User).order_by(User.created_at.desc()).limit(limit))
    )
    if not users:
        return []

    user_ids = [u.id for u in users]

    installations = list(
        session.exec(select(GitHubInstallation).where(GitHubInstallation.user_id.in_(user_ids)))
    )
    connected = {
        i.user_id for i in installations if i.encrypted_access_token
    }
    installation_owner = {i.id: i.user_id for i in installations}

    repos = list(
        session.exec(
            select(Repository).where(Repository.installation_id.in_(list(installation_owner)))
        )
    )
    repos_per_user: Counter[str] = Counter()
    repo_owner: dict[str, str] = {}
    for repo in repos:
        owner = installation_owner.get(repo.installation_id)
        if owner:
            repos_per_user[owner] += 1
            repo_owner[repo.id] = owner

    analyses_per_user: Counter[str] = Counter()
    if repo_owner:
        pairs = session.exec(
            select(PullRequest.repository_id, func.count(Analysis.id))
            .join(Analysis, Analysis.pull_request_id == PullRequest.id)
            .where(PullRequest.repository_id.in_(list(repo_owner)))
            .group_by(PullRequest.repository_id)
        )
        for repository_id, count in pairs:
            owner = repo_owner.get(repository_id)
            if owner:
                analyses_per_user[owner] += count

    rows: list[AdminUserRow] = []
    for user in users:
        if user.github_user_id:
            method = "github"
        elif user.password_hash:
            method = "password"
        else:
            method = "none"
        rows.append(
            AdminUserRow(
                id=user.id,
                login=user.login,
                name=user.name,
                email=user.email,
                avatar_url=user.avatar_url,
                auth_method=method,
                github_connected=user.id in connected,
                repository_count=repos_per_user.get(user.id, 0),
                analysis_count=analyses_per_user.get(user.id, 0),
                is_admin=settings.is_admin_email(user.email),
                created_at=user.created_at,
            )
        )
    return rows


def _build_repositories(session: Session, limit: int) -> list[AdminRepositoryRow]:
    repos = list(
        session.exec(select(Repository).order_by(Repository.created_at.desc()).limit(limit))
    )
    if not repos:
        return []

    owners: dict[str, User] = {}
    for repo in repos:
        installation = session.get(GitHubInstallation, repo.installation_id)
        if installation is not None:
            user = session.get(User, installation.user_id)
            if user is not None:
                owners[repo.id] = user

    repo_ids = [r.id for r in repos]
    analyses_per_repo: Counter[str] = Counter()
    findings_per_repo: Counter[str] = Counter()

    rows = session.exec(
        select(PullRequest.repository_id, func.count(Analysis.id))
        .join(Analysis, Analysis.pull_request_id == PullRequest.id)
        .where(PullRequest.repository_id.in_(repo_ids))
        .group_by(PullRequest.repository_id)
    )
    for repository_id, count in rows:
        analyses_per_repo[repository_id] = count

    rows = session.exec(
        select(PullRequest.repository_id, func.count(Finding.id))
        .join(Analysis, Analysis.pull_request_id == PullRequest.id)
        .join(Finding, Finding.analysis_id == Analysis.id)
        .where(PullRequest.repository_id.in_(repo_ids))
        .group_by(PullRequest.repository_id)
    )
    for repository_id, count in rows:
        findings_per_repo[repository_id] = count

    return [
        AdminRepositoryRow(
            id=repo.id,
            full_name=repo.full_name,
            owner_login=owners[repo.id].login if repo.id in owners else None,
            owner_email=owners[repo.id].email if repo.id in owners else None,
            primary_language=repo.primary_language,
            is_private=repo.is_private,
            open_pr_count=repo.open_pr_count,
            analysis_count=analyses_per_repo.get(repo.id, 0),
            finding_count=findings_per_repo.get(repo.id, 0),
            last_analyzed_at=repo.last_analyzed_at,
            created_at=repo.created_at,
        )
        for repo in repos
    ]


def _build_analyses(session: Session, limit: int) -> list[AdminAnalysisRow]:
    analyses = list(
        session.exec(select(Analysis).order_by(Analysis.created_at.desc()).limit(limit))
    )
    if not analyses:
        return []

    finding_counts: Counter[str] = Counter()
    rows = session.exec(
        select(Finding.analysis_id, func.count(Finding.id))
        .where(Finding.analysis_id.in_([a.id for a in analyses]))
        .group_by(Finding.analysis_id)
    )
    for analysis_id, count in rows:
        finding_counts[analysis_id] = count

    result: list[AdminAnalysisRow] = []
    for analysis in analyses:
        pull_request = session.get(PullRequest, analysis.pull_request_id)
        repository = (
            session.get(Repository, pull_request.repository_id) if pull_request else None
        )
        result.append(
            AdminAnalysisRow(
                id=analysis.id,
                repository_full_name=repository.full_name if repository else None,
                pull_request_number=pull_request.github_pr_number if pull_request else None,
                status=analysis.status.value,
                stage=analysis.stage,
                triggered_by=analysis.triggered_by,
                finding_count=finding_counts.get(analysis.id, 0),
                duration_seconds=analysis.duration_seconds,
                estimated_cost=analysis.estimated_cost,
                created_at=analysis.created_at,
            )
        )
    return result


def _build_finding_stats(session: Session) -> AdminFindingStats:
    severity_rows = session.exec(
        select(Finding.severity, func.count(Finding.id)).group_by(Finding.severity)
    )
    by_severity = [
        SeverityBreakdown(severity=getattr(sev, "value", str(sev)), count=count)
        for sev, count in severity_rows
    ]

    category_rows = session.exec(
        select(Finding.category, func.count(Finding.id)).group_by(Finding.category)
    )
    by_category = sorted(
        (
            CategoryBreakdown(category=getattr(cat, "value", str(cat)), count=count)
            for cat, count in category_rows
        ),
        key=lambda row: row.count,
        reverse=True,
    )

    status_rows = session.exec(
        select(Patch.status, func.count(Patch.id)).group_by(Patch.status)
    )
    counts = {getattr(s, "value", str(s)): c for s, c in status_rows}
    approved = counts.get(PatchStatus.APPROVED.value, 0) + counts.get(
        PatchStatus.APPLIED.value, 0
    )
    rejected = counts.get(PatchStatus.REJECTED.value, 0)
    reviewed = approved + rejected

    return AdminFindingStats(
        total=sum(row.count for row in by_severity),
        by_severity=by_severity,
        by_category=by_category[:10],
        patches_proposed=sum(counts.values()),
        patches_approved=approved,
        patches_rejected=rejected,
        # Of the patches a human actually decided on, how many were accepted.
        fix_acceptance_rate=round((approved / reviewed) * 100, 1) if reviewed else 0.0,
    )


def _build_audit(session: Session, limit: int) -> list[AdminAuditRow]:
    entries = list(
        session.exec(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit))
    )
    actors: dict[str, User] = {}
    for entry in entries:
        if entry.user_id and entry.user_id not in actors:
            user = session.get(User, entry.user_id)
            if user is not None:
                actors[entry.user_id] = user

    return [
        AdminAuditRow(
            id=entry.id,
            action=entry.action,
            entity_type=entry.entity_type,
            entity_id=entry.entity_id,
            actor_login=actors[entry.user_id].login if entry.user_id in actors else None,
            actor_email=actors[entry.user_id].email if entry.user_id in actors else None,
            ip_address=entry.ip_address,
            created_at=entry.created_at,
        )
        for entry in entries
    ]


@router.get(
    "/overview",
    response_model=AdminOverview,
    summary="System-wide users, repositories, analyses, findings and audit trail",
)
def admin_overview(
    admin: AdminUser,
    session: SessionDep,
    limit: int = Query(default=50, ge=1, le=200, description="Rows per section"),
) -> AdminOverview:
    logger.info("admin.overview_read", admin_id=admin.id)
    totals = AdminTotals(
        users=_count(session, User),
        repositories=_count(session, Repository),
        analyses=_count(session, Analysis),
        findings=_count(session, Finding),
        patches=_count(session, Patch),
        pull_requests=_count(session, PullRequest),
    )
    return AdminOverview(
        totals=totals,
        users=_build_users(session, limit),
        repositories=_build_repositories(session, limit),
        analyses=_build_analyses(session, limit),
        findings=_build_finding_stats(session),
        audit=_build_audit(session, limit),
    )
