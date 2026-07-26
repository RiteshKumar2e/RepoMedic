"""Aggregations for the dashboard and analytics pages."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlmodel import Session, select

from app.models.entities import (
    Analysis,
    Finding,
    Patch,
    PullRequest,
    Repository,
    User,
)
from app.models.enums import AnalysisStatus, PatchStatus, PullRequestStatus, Severity
from app.schemas.analytics import (
    ActivityItem,
    CategoryCount,
    DashboardResponse,
    RepositoryAnalyticsResponse,
    RiskyModule,
    SeverityCount,
    TrendPoint,
)
from app.services import audit
from app.services.repositories import list_repositories


def _severity_counts(findings: list[Finding]) -> list[SeverityCount]:
    counter = Counter(f.severity.value for f in findings)
    return [SeverityCount(severity=s.value, count=counter.get(s.value, 0)) for s in Severity]


def _acceptance_rate(patches: list[Patch]) -> float:
    decided = [p for p in patches if p.status in (PatchStatus.APPROVED, PatchStatus.REJECTED, PatchStatus.APPLIED)]
    if not decided:
        return 0.0
    accepted = sum(1 for p in decided if p.status in (PatchStatus.APPROVED, PatchStatus.APPLIED))
    return round(accepted / len(decided) * 100, 1)


def _trend(findings: list[Finding], days: int = 14) -> list[TrendPoint]:
    today = datetime.now(timezone.utc).date()
    buckets: dict[str, Counter] = defaultdict(Counter)
    for finding in findings:
        created = finding.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        buckets[created.date().isoformat()][finding.severity.value] += 1

    points: list[TrendPoint] = []
    for offset in range(days - 1, -1, -1):
        day = (today - timedelta(days=offset)).isoformat()
        counter = buckets.get(day, Counter())
        points.append(
            TrendPoint(
                date=day,
                critical=counter.get("critical", 0),
                high=counter.get("high", 0),
                medium=counter.get("medium", 0),
                low=counter.get("low", 0),
                informational=counter.get("informational", 0),
                total=sum(counter.values()),
            )
        )
    return points


def _findings_for_repositories(session: Session, repository_ids: list[str]) -> list[Finding]:
    if not repository_ids:
        return []
    pr_ids = [
        row.id
        for row in session.exec(select(PullRequest).where(PullRequest.repository_id.in_(repository_ids)))
    ]
    if not pr_ids:
        return []
    analysis_ids = [
        row.id for row in session.exec(select(Analysis).where(Analysis.pull_request_id.in_(pr_ids)))
    ]
    if not analysis_ids:
        return []
    return list(session.exec(select(Finding).where(Finding.analysis_id.in_(analysis_ids))))


def _patches_for_findings(session: Session, finding_ids: list[str]) -> list[Patch]:
    if not finding_ids:
        return []
    return list(session.exec(select(Patch).where(Patch.finding_id.in_(finding_ids))))


def dashboard(session: Session, user: User) -> DashboardResponse:
    repositories = list_repositories(session, user)
    repository_ids = [r.id for r in repositories]

    pull_requests = (
        list(session.exec(select(PullRequest).where(PullRequest.repository_id.in_(repository_ids))))
        if repository_ids
        else []
    )
    pr_ids = [pr.id for pr in pull_requests]
    analyses = (
        list(session.exec(select(Analysis).where(Analysis.pull_request_id.in_(pr_ids))))
        if pr_ids
        else []
    )
    findings = _findings_for_repositories(session, repository_ids)
    patches = _patches_for_findings(session, [f.id for f in findings])

    durations = [a.duration_seconds for a in analyses if a.duration_seconds]
    activity = [
        ActivityItem(
            id=entry.id,
            action=entry.action,
            entity_type=entry.entity_type,
            entity_id=entry.entity_id,
            summary=audit.humanize(entry),
            created_at=entry.created_at.isoformat(),
        )
        for entry in audit.recent(session, limit=12)
    ]

    return DashboardResponse(
        repository_count=len(repositories),
        open_pull_requests=sum(1 for pr in pull_requests if pr.status is PullRequestStatus.OPEN),
        active_analyses=sum(
            1 for a in analyses if a.status in (AnalysisStatus.QUEUED, AnalysisStatus.RUNNING)
        ),
        total_findings=len(findings),
        findings_by_severity=_severity_counts(findings),
        fix_acceptance_rate=_acceptance_rate(patches),
        average_review_seconds=round(sum(durations) / len(durations), 1) if durations else 0.0,
        patches_pending_review=sum(
            1 for p in patches if p.status in (PatchStatus.VALIDATED, PatchStatus.PROPOSED)
        ),
        recent_activity=activity,
        trend=_trend(findings),
    )


def repository_analytics(session: Session, repository: Repository) -> RepositoryAnalyticsResponse:
    findings = _findings_for_repositories(session, [repository.id])
    patches = _patches_for_findings(session, [f.id for f in findings])

    pr_ids = [
        row.id
        for row in session.exec(select(PullRequest).where(PullRequest.repository_id == repository.id))
    ]
    analyses = (
        list(session.exec(select(Analysis).where(Analysis.pull_request_id.in_(pr_ids))))
        if pr_ids
        else []
    )
    durations = [a.duration_seconds for a in analyses if a.duration_seconds]

    by_file: dict[str, list[Finding]] = defaultdict(list)
    for finding in findings:
        by_file[finding.file_path].append(finding)

    riskiest = sorted(
        (
            RiskyModule(
                file_path=path,
                finding_count=len(items),
                max_severity=max(items, key=lambda f: f.severity.rank).severity.value,
                score=round(sum(f.score for f in items), 1),
            )
            for path, items in by_file.items()
        ),
        key=lambda m: m.score,
        reverse=True,
    )[:10]

    category_counter = Counter(f.category.value for f in findings)
    source_counter = Counter(f.source.value for f in findings)

    security_findings = [f for f in findings if f.category.value in ("security", "secret", "dependency")]
    weighted = sum(f.severity.weight for f in security_findings)
    posture = round(max(0.0, 100.0 - weighted * 12), 1)

    return RepositoryAnalyticsResponse(
        repository_id=repository.id,
        analyses_run=len(analyses),
        total_findings=len(findings),
        findings_by_severity=_severity_counts(findings),
        findings_by_category=[
            CategoryCount(category=name, count=count) for name, count in category_counter.most_common()
        ],
        findings_by_source=[
            CategoryCount(category=name, count=count) for name, count in source_counter.most_common()
        ],
        fix_acceptance_rate=_acceptance_rate(patches),
        average_review_seconds=round(sum(durations) / len(durations), 1) if durations else 0.0,
        defect_trend=_trend(findings, days=30),
        riskiest_modules=riskiest,
        security_posture_score=posture,
        language_distribution=dict(repository.languages or {}),
        total_estimated_cost=round(sum(a.estimated_cost for a in analyses), 4),
    )


def analysis_summary_stats(session: Session, analysis_id: str) -> dict:
    findings = list(session.exec(select(Finding).where(Finding.analysis_id == analysis_id)))
    patches = _patches_for_findings(session, [f.id for f in findings])
    return {
        "total_findings": len(findings),
        "by_severity": dict(Counter(f.severity.value for f in findings)),
        "by_category": dict(Counter(f.category.value for f in findings)),
        "by_source": dict(Counter(f.source.value for f in findings)),
        "patches_proposed": len(patches),
        "patches_validated": sum(1 for p in patches if p.status is PatchStatus.VALIDATED),
        "patches_approved": sum(
            1 for p in patches if p.status in (PatchStatus.APPROVED, PatchStatus.APPLIED)
        ),
        "files_with_findings": len({f.file_path for f in findings}),
    }
