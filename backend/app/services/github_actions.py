"""Write-side GitHub operations: review publishing and fix pull requests.

Safety rules enforced here:

* Fixes are **never** committed to the default branch — always a new branch.
* Only patches a human explicitly approved are applied.
* Every patch is re-validated against the *current* file content before the
  commit; if the file moved on, the patch is skipped and reported, not forced.
* Every action is written to the audit log.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlmodel import Session, select

from app.core.errors import ConflictError, ValidationError
from app.core.logging import get_logger
from app.domain.types import PatchProposal
from app.github.client import GitHubClient
from app.github.service import resolve_token
from app.models.entities import (
    Analysis,
    Finding,
    GitHubInstallation,
    Patch,
    PullRequest,
    Repository,
    ReviewComment,
    utcnow,
)
from app.models.enums import FindingStatus, PatchStatus, Severity
from app.patching.differ import apply_proposal
from app.services import audit

logger = get_logger(__name__)

REVIEW_MARKER = "<!-- repomedic-review -->"
MAX_INLINE_COMMENTS = 20


# --------------------------------------------------------------------------- #
# Review publishing
# --------------------------------------------------------------------------- #
def build_review_body(analysis: Analysis, findings: list[Finding], repository: Repository) -> str:
    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding.severity.value] = counts.get(finding.severity.value, 0) + 1

    critical, high = counts.get("critical", 0), counts.get("high", 0)
    if critical:
        verdict = f"🔴 **{critical} critical issue(s) found.** These should block the merge."
    elif high:
        verdict = f"🟠 **{high} high-severity issue(s) found.** Worth resolving before merge."
    elif findings:
        verdict = "🟡 No critical or high-severity issues. Some improvements suggested."
    else:
        verdict = "🟢 No issues found by the configured reviewers and scanners."

    lines = [
        REVIEW_MARKER,
        "## RepoMedic review",
        "",
        verdict,
        "",
        "| Severity | Count |",
        "| --- | ---: |",
    ]
    for severity in Severity:
        count = counts.get(severity.value, 0)
        if count:
            lines.append(f"| {severity.value.title()} | {count} |")

    blocking = [f for f in findings if f.severity.rank >= Severity.HIGH.rank][:10]
    if blocking:
        lines += ["", "### Must fix", ""]
        for finding in blocking:
            lines.append(
                f"- **{finding.severity.value.upper()}** · `{finding.file_path}:{finding.start_line}` — "
                f"{finding.title}"
                + (f" ({finding.cwe})" if finding.cwe else "")
            )

    others = [f for f in findings if f.severity.rank < Severity.HIGH.rank][:10]
    if others:
        lines += ["", "### Also noted", ""]
        for finding in others:
            lines.append(f"- `{finding.file_path}:{finding.start_line}` — {finding.title}")

    lines += [
        "",
        "---",
        f"Scanners: {', '.join(analysis.scanners_run or []) or 'none available'} · "
        f"Reviewers: {', '.join(analysis.reviewers_run or []) or 'none'} · "
        f"Model: {analysis.model_provider or 'n/a'}/{analysis.model_name or 'n/a'} · "
        f"Cost: ${analysis.estimated_cost:.4f}",
        "",
        "_Findings are advisory. Every suggested fix is validated before it can be applied, "
        "and nothing is committed without explicit approval._",
    ]
    return "\n".join(lines)


def _inline_comments(findings: list[Finding], changed_paths: set[str]) -> list[dict]:
    comments: list[dict] = []
    for finding in findings:
        if finding.file_path not in changed_paths:
            continue  # GitHub rejects comments on files outside the diff
        if len(comments) >= MAX_INLINE_COMMENTS:
            break
        body = (
            f"**{finding.severity.value.upper()} · {finding.category.value}** — {finding.title}\n\n"
            f"{finding.description}\n\n"
            f"**Risk:** {finding.risk}\n\n"
            f"**Fix:** {finding.recommendation}\n\n"
            f"<sub>RepoMedic · {finding.source.value} · confidence {finding.confidence:.0%}"
            + (f" · {finding.cwe}" if finding.cwe else "")
            + "</sub>"
        )
        comments.append({"path": finding.file_path, "line": finding.end_line, "side": "RIGHT", "body": body})
    return comments


async def publish_review(
    session: Session,
    analysis: Analysis,
    *,
    min_severity: Severity = Severity.MEDIUM,
    include_inline_comments: bool = True,
    dry_run: bool = False,
    user_id: str | None = None,
) -> dict:
    pull_request = session.get(PullRequest, analysis.pull_request_id)
    repository = session.get(Repository, pull_request.repository_id)
    installation = session.get(GitHubInstallation, repository.installation_id)

    allowed = Severity.at_least(min_severity)
    findings = [
        f for f in session.exec(
            select(Finding).where(Finding.analysis_id == analysis.id).order_by(Finding.score.desc())
        )
        if f.severity in allowed
    ]
    body = build_review_body(analysis, findings, repository)

    if dry_run:
        return {"posted": False, "dry_run_body": body, "inline_comments": 0}

    if installation is None:
        raise ValidationError("This repository has no GitHub credential attached")

    token = await resolve_token(session, installation)
    changed_paths = {f.file_path for f in findings}

    async with GitHubClient(token) as gh:
        files = await gh.list_pull_request_files(
            repository.owner, repository.name, pull_request.github_pr_number
        )
        diff_paths = {f["filename"] for f in files}
        comments = (
            _inline_comments(findings, changed_paths & diff_paths)
            if include_inline_comments
            else []
        )
        review = await gh.create_review(
            repository.owner,
            repository.name,
            pull_request.github_pr_number,
            body=body,
            comments=comments,
            event="COMMENT",
        )

    posted_at = datetime.now(timezone.utc)
    for finding in findings[: len(comments)]:
        session.add(
            ReviewComment(
                finding_id=finding.id,
                github_comment_id=review.get("id"),
                body=body[:2000],
                html_url=review.get("html_url"),
                posted_at=posted_at,
            )
        )
    session.commit()

    audit.record(
        session,
        action="review.published",
        entity_type="analysis",
        entity_id=analysis.id,
        user_id=user_id,
        metadata={
            "target": f"{repository.full_name}#{pull_request.github_pr_number}",
            "findings": len(findings),
            "inline_comments": len(comments),
        },
    )
    return {
        "posted": True,
        "summary_comment_url": review.get("html_url"),
        "inline_comments": len(comments),
    }


# --------------------------------------------------------------------------- #
# Fix pull requests
# --------------------------------------------------------------------------- #
def branch_name_for(analysis: Analysis, pull_request: PullRequest) -> str:
    stamp = utcnow().strftime("%Y%m%d-%H%M%S")
    return f"repomedic/fix-pr{pull_request.github_pr_number}-{stamp}"


def _sanitize_branch(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._/-]", "-", name).strip("-/")
    if not cleaned or cleaned.startswith("-"):
        raise ValidationError("Invalid branch name")
    return cleaned[:200]


async def create_fix_pull_request(
    session: Session,
    analysis: Analysis,
    *,
    patch_ids: list[str] | None = None,
    branch_name: str | None = None,
    title: str | None = None,
    dry_run: bool = False,
    user_id: str | None = None,
) -> dict:
    pull_request = session.get(PullRequest, analysis.pull_request_id)
    repository = session.get(Repository, pull_request.repository_id)
    installation = session.get(GitHubInstallation, repository.installation_id)

    finding_ids = [
        row.id for row in session.exec(select(Finding).where(Finding.analysis_id == analysis.id))
    ]
    statement = select(Patch).where(
        Patch.finding_id.in_(finding_ids), Patch.status == PatchStatus.APPROVED
    )
    if patch_ids:
        statement = statement.where(Patch.id.in_(patch_ids))
    approved = list(session.exec(statement))

    if not approved:
        raise ConflictError(
            "No approved patches to apply. Approve at least one validated fix first."
        )

    branch = _sanitize_branch(branch_name or branch_name_for(analysis, pull_request))
    pr_title = title or f"fix: RepoMedic patches for #{pull_request.github_pr_number}"

    # ---- dry run: build the combined diff without touching GitHub --------
    if dry_run:
        return {
            "created": False,
            "branch": branch,
            "applied_patches": [p.id for p in approved],
            "skipped_patches": [],
            "dry_run_diff": "\n".join(p.unified_diff for p in approved),
        }

    if installation is None:
        raise ValidationError("This repository has no GitHub credential attached")
    token = await resolve_token(session, installation)

    applied: list[str] = []
    skipped: list[dict[str, str]] = []

    async with GitHubClient(token) as gh:
        head_sha = pull_request.head_sha
        if not head_sha:
            ref = await gh.get_ref(repository.owner, repository.name, f"heads/{pull_request.head_ref}")
            head_sha = ref["object"]["sha"]

        # Branch from the PR head so the fixes stack on the author's work,
        # never on the protected default branch.
        await gh.create_branch(repository.owner, repository.name, branch, head_sha)

        # Group by file so multiple patches to one file become one commit each,
        # applied in order against the freshly-fetched content.
        by_file: dict[str, list[Patch]] = {}
        for patch in approved:
            by_file.setdefault(patch.file_path, []).append(patch)

        for file_path, patches in by_file.items():
            try:
                content = await gh.get_file_content(repository.owner, repository.name, file_path, branch)
            except Exception as exc:
                for patch in patches:
                    skipped.append({"patch_id": patch.id, "reason": f"could not read {file_path}: {exc}"})
                continue

            updated = content
            applied_here: list[Patch] = []
            for patch in patches:
                proposal = PatchProposal(
                    file_path=file_path,
                    original_code=patch.original_code,
                    suggested_code=patch.suggested_code,
                    start_line=1,
                    end_line=1,
                )
                candidate, error = apply_proposal(updated, proposal)
                if candidate is None:
                    skipped.append({"patch_id": patch.id, "reason": error})
                    continue
                updated = candidate
                applied_here.append(patch)

            if not applied_here:
                continue

            sha = await gh.get_file_sha(repository.owner, repository.name, file_path, branch)
            message = _commit_message(session, applied_here, file_path)
            commit = await gh.put_file(
                repository.owner, repository.name, file_path, updated, message, branch, sha
            )
            commit_sha = (commit.get("commit") or {}).get("sha")

            for patch in applied_here:
                patch.status = PatchStatus.APPLIED
                patch.applied_commit_sha = commit_sha
                session.add(patch)
                finding = session.get(Finding, patch.finding_id)
                if finding is not None:
                    finding.status = FindingStatus.RESOLVED
                    session.add(finding)
                applied.append(patch.id)
            session.commit()

        if not applied:
            raise ConflictError(
                "None of the approved patches could be applied — the files changed since "
                "the fixes were generated. Re-run the analysis."
            )

        body = _fix_pr_body(session, analysis, pull_request, applied, skipped)
        created = await gh.create_pull_request(
            repository.owner,
            repository.name,
            title=pr_title,
            head=branch,
            base=pull_request.head_ref or repository.default_branch,
            body=body,
        )
        try:
            await gh.add_labels(
                repository.owner, repository.name, created["number"], ["repomedic", "automated-fix"]
            )
        except Exception as exc:
            logger.info("github.label_failed", error=str(exc))

    audit.record(
        session,
        action="fix_pr.created",
        entity_type="analysis",
        entity_id=analysis.id,
        user_id=user_id,
        metadata={
            "target": created.get("html_url", branch),
            "branch": branch,
            "applied": len(applied),
            "skipped": len(skipped),
        },
    )
    return {
        "created": True,
        "branch": branch,
        "pull_request_url": created.get("html_url"),
        "pull_request_number": created.get("number"),
        "applied_patches": applied,
        "skipped_patches": skipped,
    }


def _commit_message(session: Session, patches: list[Patch], file_path: str) -> str:
    findings = [session.get(Finding, p.finding_id) for p in patches]
    findings = [f for f in findings if f is not None]
    primary = max(findings, key=lambda f: f.severity.rank) if findings else None

    kind = "fix"
    if primary and primary.category.value in ("performance",):
        kind = "perf"
    elif primary and primary.category.value in ("code_quality", "architecture"):
        kind = "refactor"

    subject = (
        f"{kind}({file_path.split('/')[-1]}): {primary.title[:60]}"
        if primary
        else f"{kind}: apply RepoMedic patches to {file_path}"
    )
    body_lines = ["", ""]
    for finding in findings:
        body_lines.append(
            f"- {finding.severity.value.upper()} {finding.rule_id or finding.category.value}: "
            f"{finding.title} ({file_path}:{finding.start_line})"
        )
    body_lines += ["", "Generated and validated by RepoMedic. Reviewed and approved by a human."]
    return subject + "\n".join(body_lines)


def _fix_pr_body(
    session: Session,
    analysis: Analysis,
    pull_request: PullRequest,
    applied: list[str],
    skipped: list[dict[str, str]],
) -> str:
    lines = [
        f"Automated fixes for the findings in #{pull_request.github_pr_number}.",
        "",
        f"**{len(applied)} patch(es) applied.** Every one was approved by a human reviewer and "
        "passed syntax, lint, type-check, security and test validation before being committed.",
        "",
        "### Applied",
        "",
    ]
    for patch_id in applied:
        patch = session.get(Patch, patch_id)
        if patch is None:
            continue
        finding = session.get(Finding, patch.finding_id)
        title = finding.title if finding else patch.file_path
        lines.append(
            f"- `{patch.file_path}` — {title} "
            f"(confidence {patch.confidence:.0f}/100, risk {patch.risk_level.value})"
        )

    if skipped:
        lines += ["", "### Skipped", ""]
        lines += [f"- `{item['patch_id'][:8]}` — {item['reason']}" for item in skipped]

    lines += [
        "",
        "---",
        f"Analysis `{analysis.id}` · {len(analysis.scanners_run or [])} scanners · "
        f"{len(analysis.reviewers_run or [])} AI reviewers",
    ]
    return "\n".join(lines)


async def update_check_run(
    session: Session, analysis: Analysis, *, status: str, conclusion: str | None = None
) -> dict | None:
    """Report analysis state back to GitHub as a check run."""
    pull_request = session.get(PullRequest, analysis.pull_request_id)
    repository = session.get(Repository, pull_request.repository_id)
    installation = session.get(GitHubInstallation, repository.installation_id)
    if installation is None or not pull_request.head_sha:
        return None

    findings = list(session.exec(select(Finding).where(Finding.analysis_id == analysis.id)))
    critical = sum(1 for f in findings if f.severity is Severity.CRITICAL)
    high = sum(1 for f in findings if f.severity is Severity.HIGH)

    try:
        token = await resolve_token(session, installation)
        async with GitHubClient(token) as gh:
            return await gh.create_check_run(
                repository.owner,
                repository.name,
                pull_request.head_sha,
                name="RepoMedic review",
                status=status,
                conclusion=conclusion or ("failure" if critical else "success" if status == "completed" else None),
                output={
                    "title": f"{len(findings)} finding(s) — {critical} critical, {high} high",
                    "summary": analysis.summary or "Analysis in progress",
                },
            )
    except Exception as exc:
        logger.info("github.check_run_failed", error=str(exc))
        return None
