"""Domain-level GitHub operations: synchronising repositories and pull requests.

Keeps the HTTP client (``GitHubClient``) separate from persistence so the API
layer never talks to GitHub directly.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session, select

from app.core.errors import AuthenticationError, NotFoundError
from app.core.logging import get_logger
from app.core.security import decrypt_secret
from app.domain.types import FileChange, changed_lines_from_patch
from app.github.client import GitHubClient
from app.github.oauth import create_installation_token
from app.models.entities import GitHubInstallation, PullRequest, Repository, utcnow
from app.models.enums import PullRequestStatus

logger = get_logger(__name__)


def _parse_dt(value: str | None) -> datetime:
    if not value:
        return utcnow()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return utcnow()


async def resolve_token(session: Session, installation: GitHubInstallation) -> str:
    """Return a usable token, refreshing App installation tokens when expired."""
    token = decrypt_secret(installation.encrypted_access_token)
    expires_at = installation.token_expires_at

    needs_refresh = bool(
        installation.installation_id
        and expires_at
        and expires_at.replace(tzinfo=expires_at.tzinfo or timezone.utc) <= datetime.now(timezone.utc)
    )
    if (not token or needs_refresh) and installation.installation_id:
        from app.core.security import encrypt_secret

        minted = await create_installation_token(installation.installation_id)
        installation.encrypted_access_token = encrypt_secret(minted["token"])
        installation.token_expires_at = minted["expires_at"]
        installation.updated_at = utcnow()
        session.add(installation)
        session.commit()
        return minted["token"]

    if not token:
        raise AuthenticationError("No usable GitHub credential for this installation")
    return token


def get_installation_for_user(session: Session, user_id: str) -> GitHubInstallation:
    installation = session.exec(
        select(GitHubInstallation).where(GitHubInstallation.user_id == user_id)
    ).first()
    if not installation:
        raise AuthenticationError("Connect a GitHub account to continue")
    return installation


async def sync_repositories(session: Session, user_id: str, limit: int = 100) -> list[Repository]:
    """Pull the user's repositories from GitHub and upsert them."""
    installation = get_installation_for_user(session, user_id)
    token = await resolve_token(session, installation)

    async with GitHubClient(token) as gh:
        if installation.installation_id:
            payload = await gh.list_installation_repositories(limit=limit)
        else:
            payload = await gh.list_repositories(limit=limit)

    synced: list[Repository] = []
    for item in payload:
        repo = session.exec(
            select(Repository).where(
                Repository.installation_id == installation.id,
                Repository.github_repository_id == item["id"],
            )
        ).first()
        if repo is None:
            repo = Repository(
                installation_id=installation.id,
                github_repository_id=item["id"],
                owner=item["owner"]["login"],
                name=item["name"],
                full_name=item["full_name"],
            )
        repo.description = item.get("description")
        repo.default_branch = item.get("default_branch") or "main"
        repo.primary_language = item.get("language")
        repo.is_private = bool(item.get("private", True))
        repo.html_url = item.get("html_url")
        repo.clone_url = item.get("clone_url")
        repo.stars = int(item.get("stargazers_count", 0) or 0)
        repo.open_pr_count = int(item.get("open_issues_count", 0) or 0)
        repo.updated_at = utcnow()
        session.add(repo)
        synced.append(repo)

    session.commit()
    for repo in synced:
        session.refresh(repo)
    logger.info("github.repositories_synced", user_id=user_id, count=len(synced))
    return synced


async def sync_pull_requests(
    session: Session, repository: Repository, state: str = "open", limit: int = 50
) -> list[PullRequest]:
    installation = session.get(GitHubInstallation, repository.installation_id)
    if installation is None:
        raise NotFoundError("Installation for repository not found")
    token = await resolve_token(session, installation)

    async with GitHubClient(token) as gh:
        payload = await gh.list_pull_requests(repository.owner, repository.name, state=state, limit=limit)

    synced: list[PullRequest] = []
    for item in payload:
        pr = session.exec(
            select(PullRequest).where(
                PullRequest.repository_id == repository.id,
                PullRequest.github_pr_number == item["number"],
            )
        ).first()
        if pr is None:
            pr = PullRequest(
                repository_id=repository.id,
                github_pr_number=item["number"],
                title=item["title"],
            )
        _apply_pr_payload(pr, item)
        session.add(pr)
        synced.append(pr)

    session.commit()
    for pr in synced:
        session.refresh(pr)
    return synced


def _apply_pr_payload(pr: PullRequest, item: dict) -> None:
    pr.title = item.get("title", pr.title)
    pr.body = item.get("body")
    pr.base_ref = item.get("base", {}).get("ref", pr.base_ref)
    pr.head_ref = item.get("head", {}).get("ref", pr.head_ref)
    pr.base_sha = item.get("base", {}).get("sha", pr.base_sha)
    pr.head_sha = item.get("head", {}).get("sha", pr.head_sha)
    pr.author = item.get("user", {}).get("login", pr.author)
    pr.author_avatar_url = item.get("user", {}).get("avatar_url")
    pr.is_draft = bool(item.get("draft", False))
    pr.additions = int(item.get("additions", 0) or 0)
    pr.deletions = int(item.get("deletions", 0) or 0)
    pr.changed_files = int(item.get("changed_files", 0) or 0)
    pr.html_url = item.get("html_url")
    pr.updated_at = utcnow()
    if item.get("merged_at"):
        pr.status = PullRequestStatus.MERGED
    elif item.get("state") == "closed":
        pr.status = PullRequestStatus.CLOSED
    elif item.get("draft"):
        pr.status = PullRequestStatus.DRAFT
    else:
        pr.status = PullRequestStatus.OPEN


async def fetch_pull_request_changes(
    token: str, owner: str, repo: str, number: int
) -> list[FileChange]:
    """Fetch the PR file list and normalize it into :class:`FileChange` objects."""
    async with GitHubClient(token) as gh:
        files = await gh.list_pull_request_files(owner, repo, number)

    changes: list[FileChange] = []
    for f in files:
        patch = f.get("patch", "") or ""
        changes.append(
            FileChange(
                path=f["filename"],
                status=f.get("status", "modified"),
                additions=int(f.get("additions", 0) or 0),
                deletions=int(f.get("deletions", 0) or 0),
                patch=patch,
                previous_path=f.get("previous_filename"),
                changed_lines=changed_lines_from_patch(patch),
            )
        )
    return changes


async def upsert_pull_request_from_payload(
    session: Session, repository: Repository, payload: dict
) -> PullRequest:
    """Create or update a PR row from a webhook or API payload."""
    pr = session.exec(
        select(PullRequest).where(
            PullRequest.repository_id == repository.id,
            PullRequest.github_pr_number == payload["number"],
        )
    ).first()
    if pr is None:
        pr = PullRequest(
            repository_id=repository.id,
            github_pr_number=payload["number"],
            title=payload.get("title", ""),
            created_at=_parse_dt(payload.get("created_at")),
        )
    _apply_pr_payload(pr, payload)
    session.add(pr)
    session.commit()
    session.refresh(pr)
    return pr
