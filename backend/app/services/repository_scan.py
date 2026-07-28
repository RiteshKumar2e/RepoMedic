"""Whole-repository scans.

A scan reviews the default branch instead of a pull request, so RepoMedic can
find issues in code that nobody is currently changing and open a fix PR against
it.

It deliberately reuses :class:`AnalysisPipeline` rather than duplicating the
eighteen stages. The pipeline is driven by ``context.changes``; a scan simply
declares the whole tree as in scope (see ``AnalysisPipeline.is_full_scan``).

To make that work the scan attaches to a synthetic pull-request row: one per
repository, numbered ``0`` to mark it as "not a real pull request". That keeps
every existing foreign key, ownership check and fix-PR path working unchanged —
``create_fix_pull_request`` branches from ``head_ref`` and targets it, which for
a scan is the default branch.
"""

from __future__ import annotations

from sqlmodel import Session, select

from app.core.logging import get_logger
from app.models.entities import Analysis, PullRequest, Repository, utcnow
from app.models.enums import AnalysisStatus, PullRequestStatus
from app.services.analysis_pipeline import REPOSITORY_SCAN_TRIGGER, create_analysis
from app.services.repositories import SCAN_PR_NUMBER

logger = get_logger(__name__)

__all__ = [
    "SCAN_PR_NUMBER",
    "create_scan",
    "get_or_create_scan_target",
    "is_scan_running",
    "latest_scan",
]


def get_or_create_scan_target(session: Session, repository: Repository) -> PullRequest:
    """The synthetic pull request that scan analyses hang from."""
    existing = session.exec(
        select(PullRequest).where(
            PullRequest.repository_id == repository.id,
            PullRequest.github_pr_number == SCAN_PR_NUMBER,
        )
    ).first()

    branch = repository.default_branch or "main"
    if existing is not None:
        # The default branch can be renamed between scans.
        if existing.head_ref != branch or existing.base_ref != branch:
            existing.head_ref = branch
            existing.base_ref = branch
            existing.updated_at = utcnow()
            session.add(existing)
            session.commit()
            session.refresh(existing)
        return existing

    target = PullRequest(
        repository_id=repository.id,
        github_pr_number=SCAN_PR_NUMBER,
        title=f"Repository scan — {repository.full_name}",
        body="Synthetic target for whole-repository scans. Not a real pull request.",
        base_ref=branch,
        head_ref=branch,
        base_sha="",
        head_sha="",
        author=repository.owner,
        status=PullRequestStatus.OPEN,
    )
    session.add(target)
    session.commit()
    session.refresh(target)
    logger.info("scan.target_created", repository=repository.full_name)
    return target


def create_scan(session: Session, repository: Repository) -> Analysis:
    """Queue a whole-repository scan and return its analysis row."""
    target = get_or_create_scan_target(session, repository)
    return create_analysis(session, target, triggered_by=REPOSITORY_SCAN_TRIGGER)


def latest_scan(session: Session, repository: Repository) -> Analysis | None:
    target = session.exec(
        select(PullRequest).where(
            PullRequest.repository_id == repository.id,
            PullRequest.github_pr_number == SCAN_PR_NUMBER,
        )
    ).first()
    if target is None:
        return None
    return session.exec(
        select(Analysis)
        .where(Analysis.pull_request_id == target.id)
        .order_by(Analysis.created_at.desc())
    ).first()


def is_scan_running(analysis: Analysis | None) -> bool:
    return analysis is not None and analysis.status in (
        AnalysisStatus.QUEUED,
        AnalysisStatus.RUNNING,
    )
