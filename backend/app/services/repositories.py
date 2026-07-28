"""Repository listing and per-repository configuration."""

from __future__ import annotations

from sqlmodel import Session, select

from app.models.entities import (
    GitHubInstallation,
    PullRequest,
    Repository,
    RepositorySettings,
    User,
    utcnow,
)
from app.models.enums import PullRequestStatus

# The pull-request number reserved for the synthetic target that whole-repository
# scans attach to. Real pull requests are numbered from 1, so 0 cannot collide.
# It lives here rather than in services/repository_scan.py to avoid an import
# cycle: repositories → repository_scan → analysis_pipeline → repositories.
SCAN_PR_NUMBER = 0


def installations_for_user(session: Session, user: User) -> list[GitHubInstallation]:
    return list(
        session.exec(select(GitHubInstallation).where(GitHubInstallation.user_id == user.id))
    )


def list_repositories(session: Session, user: User) -> list[Repository]:
    installation_ids = [i.id for i in installations_for_user(session, user)]
    if not installation_ids:
        return []
    return list(
        session.exec(
            select(Repository)
            .where(Repository.installation_id.in_(installation_ids))
            .order_by(Repository.updated_at.desc())
        )
    )


def list_pull_requests(
    session: Session, repository: Repository, status: PullRequestStatus | None = None
) -> list[PullRequest]:
    statement = select(PullRequest).where(
        PullRequest.repository_id == repository.id,
        # Number 0 is the synthetic target that whole-repository scans hang
        # from. It is not a real pull request and must never be listed as one.
        PullRequest.github_pr_number != SCAN_PR_NUMBER,
    )
    if status:
        statement = statement.where(PullRequest.status == status)
    return list(session.exec(statement.order_by(PullRequest.updated_at.desc())))


def get_or_create_settings(session: Session, repository: Repository) -> RepositorySettings:
    """Every repository always has a settings row — created lazily on first read."""
    row = session.exec(
        select(RepositorySettings).where(RepositorySettings.repository_id == repository.id)
    ).first()
    if row is None:
        row = RepositorySettings(repository_id=repository.id)
        session.add(row)
        session.commit()
        session.refresh(row)
    return row


def update_settings(
    session: Session, repository: Repository, changes: dict
) -> RepositorySettings:
    row = get_or_create_settings(session, repository)
    for key, value in changes.items():
        if value is None or not hasattr(row, key):
            continue
        if key == "custom_rules":
            value = [rule if isinstance(rule, dict) else rule.model_dump() for rule in value]
        setattr(row, key, value)
    row.updated_at = utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    return row
