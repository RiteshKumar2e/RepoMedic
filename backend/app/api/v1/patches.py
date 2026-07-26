"""Patch detail, revalidation and the human approval workflow."""

from __future__ import annotations

from fastapi import APIRouter, Request
from sqlmodel import select

from app.api.deps import (
    CurrentUser,
    RateLimited,
    SessionDep,
    client_ip,
    load_finding,
    load_patch,
)
from app.core.errors import ConflictError, ValidationError
from app.core.logging import get_logger
from app.domain.types import PatchProposal
from app.github.client import GitHubClient
from app.github.service import resolve_token
from app.models.entities import (
    Analysis,
    Finding,
    GitHubInstallation,
    PullRequest,
    Repository,
    ValidationRun,
    utcnow,
)
from app.models.enums import FindingStatus, PatchStatus, ValidationStatus
from app.schemas.analysis import FindingRead, PatchDetail, RejectPatchRequest, ValidationRunRead
from app.services import audit
from app.services.scoring import ValidationSignals, fix_confidence

logger = get_logger(__name__)
router = APIRouter(prefix="/patches", tags=["patches"])


def _detail(session, patch) -> PatchDetail:
    runs = session.exec(
        select(ValidationRun)
        .where(ValidationRun.patch_id == patch.id)
        .order_by(ValidationRun.created_at.desc())
    )
    detail = PatchDetail.model_validate(patch)
    detail.validation_runs = [ValidationRunRead.model_validate(r) for r in runs]
    finding = session.get(Finding, patch.finding_id)
    if finding is not None:
        detail.finding = FindingRead.model_validate(finding)
    return detail


@router.get("/{patch_id}", response_model=PatchDetail, summary="Patch detail with validation runs")
def get_patch(patch_id: str, user: CurrentUser, session: SessionDep) -> PatchDetail:
    patch = load_patch(patch_id, session, user)
    return _detail(session, patch)


@router.post(
    "/{patch_id}/validate",
    response_model=PatchDetail,
    dependencies=[RateLimited],
    summary="Re-validate a patch against the current file contents",
)
async def validate_patch(
    patch_id: str, request: Request, user: CurrentUser, session: SessionDep
) -> PatchDetail:
    """Re-check the patch against the file as it exists on GitHub right now.

    Full validation (lint, type-check, tests) runs inside the sandboxed
    workspace during an analysis. This endpoint re-verifies that the patch still
    applies and still parses, which is the check that goes stale fastest.
    """
    patch = load_patch(patch_id, session, user)
    finding = load_finding(patch.finding_id, session, user)
    analysis = session.get(Analysis, finding.analysis_id)
    pull_request = session.get(PullRequest, analysis.pull_request_id)
    repository = session.get(Repository, pull_request.repository_id)
    installation = session.get(GitHubInstallation, repository.installation_id)

    if installation is None or not installation.encrypted_access_token:
        raise ValidationError(
            "Re-validation needs a connected GitHub repository so the current file can be fetched."
        )

    token = await resolve_token(session, installation)
    async with GitHubClient(token) as gh:
        content = await gh.get_file_content(
            repository.owner, repository.name, patch.file_path, pull_request.head_sha
        )

    from app.patching.differ import apply_proposal
    from app.retrieval.embeddings import jaccard_similarity

    proposal = PatchProposal(
        file_path=patch.file_path,
        original_code=patch.original_code,
        suggested_code=patch.suggested_code,
        unified_diff=patch.unified_diff,
    )
    updated, error = apply_proposal(content, proposal)

    signals = ValidationSignals(
        syntax_validation=updated is not None,
        semantic_similarity=round(jaccard_similarity(patch.original_code, patch.suggested_code), 3),
    )
    confidence, breakdown = fix_confidence(signals)

    patch.confidence = confidence
    patch.confidence_breakdown = breakdown
    patch.validation_status = (
        ValidationStatus.PASSED if updated is not None else ValidationStatus.FAILED
    )
    patch.status = (
        PatchStatus.VALIDATED if updated is not None else PatchStatus.VALIDATION_FAILED
    )
    session.add(patch)
    session.add(
        ValidationRun(
            patch_id=patch.id,
            parser_passed=updated is not None,
            semantic_similarity=signals.semantic_similarity,
            step_results=[
                {
                    "name": "parse",
                    "status": "passed" if updated is not None else "failed",
                    "detail": error or "Patch applies cleanly to the current file and parses",
                },
                {
                    "name": "lint",
                    "status": "skipped",
                    "detail": "Full tool validation runs inside the sandboxed analysis workspace",
                },
            ],
            skipped_reason="re-validation outside the analysis workspace",
        )
    )
    session.commit()
    session.refresh(patch)

    audit.record(
        session,
        action="patch.validated",
        entity_type="patch",
        entity_id=patch.id,
        user_id=user.id,
        metadata={"target": patch.file_path, "confidence": confidence},
        ip_address=client_ip(request),
    )
    return _detail(session, patch)


@router.post(
    "/{patch_id}/approve",
    response_model=PatchDetail,
    dependencies=[RateLimited],
    summary="Approve a patch for inclusion in a fix pull request",
)
def approve_patch(
    patch_id: str, request: Request, user: CurrentUser, session: SessionDep
) -> PatchDetail:
    patch = load_patch(patch_id, session, user)
    if patch.status is PatchStatus.APPLIED:
        raise ConflictError("This patch has already been applied")
    if patch.validation_status is ValidationStatus.FAILED:
        raise ValidationError(
            "This patch failed validation and cannot be approved. Re-validate it or reject it."
        )

    patch.status = PatchStatus.APPROVED
    patch.approved_at = utcnow()
    patch.approved_by = user.id
    patch.rejected_at = None
    patch.rejection_reason = None
    session.add(patch)

    finding = session.get(Finding, patch.finding_id)
    if finding is not None:
        finding.status = FindingStatus.FIX_APPROVED
        session.add(finding)
    session.commit()
    session.refresh(patch)

    audit.record(
        session,
        action="patch.approved",
        entity_type="patch",
        entity_id=patch.id,
        user_id=user.id,
        metadata={"target": patch.file_path, "confidence": patch.confidence},
        ip_address=client_ip(request),
    )
    return _detail(session, patch)


@router.post(
    "/{patch_id}/reject",
    response_model=PatchDetail,
    dependencies=[RateLimited],
    summary="Reject a patch",
)
def reject_patch(
    patch_id: str,
    payload: RejectPatchRequest,
    request: Request,
    user: CurrentUser,
    session: SessionDep,
) -> PatchDetail:
    patch = load_patch(patch_id, session, user)
    if patch.status is PatchStatus.APPLIED:
        raise ConflictError("This patch has already been applied and cannot be rejected")

    patch.status = PatchStatus.REJECTED
    patch.rejected_at = utcnow()
    patch.rejection_reason = payload.reason
    patch.approved_at = None
    session.add(patch)

    finding = session.get(Finding, patch.finding_id)
    if finding is not None:
        finding.status = FindingStatus.FIX_REJECTED
        session.add(finding)
    session.commit()
    session.refresh(patch)

    audit.record(
        session,
        action="patch.rejected",
        entity_type="patch",
        entity_id=patch.id,
        user_id=user.id,
        metadata={"target": patch.file_path, "reason": payload.reason},
        ip_address=client_ip(request),
    )
    return _detail(session, patch)
