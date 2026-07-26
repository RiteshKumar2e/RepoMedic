"""Finding detail, status transitions and on-demand fix generation."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlmodel import select

from app.agents.fix_generator import FixGenerator
from app.api.deps import (
    CurrentUser,
    RateLimited,
    SessionDep,
    client_ip,
    load_analysis,
    load_finding,
)
from app.core.errors import ConflictError, ValidationError
from app.core.logging import get_logger
from app.domain.types import Language, SourceFile
from app.github.client import GitHubClient
from app.github.service import resolve_token
from app.llm.base import UsageTracker
from app.llm.registry import get_provider
from app.models.entities import (
    GitHubInstallation,
    Patch,
    PullRequest,
    Repository,
)
from app.models.enums import FindingStatus, PatchStatus, ValidationStatus
from app.schemas.analysis import FindingDetail, PatchRead
from app.services import audit
from app.services.analysis_pipeline import context_findings
from app.services.repositories import get_or_create_settings

logger = get_logger(__name__)
router = APIRouter(prefix="/findings", tags=["findings"])


class FindingStatusUpdate(BaseModel):
    status: FindingStatus
    note: str = Field(default="", max_length=500)


@router.get("/{finding_id}", response_model=FindingDetail, summary="Finding detail with patches")
def get_finding(finding_id: str, user: CurrentUser, session: SessionDep) -> FindingDetail:
    finding = load_finding(finding_id, session, user)
    patches = session.exec(select(Patch).where(Patch.finding_id == finding.id))
    detail = FindingDetail.model_validate(finding)
    detail.patches = [PatchRead.model_validate(p) for p in patches]
    return detail


@router.patch(
    "/{finding_id}/status",
    response_model=FindingDetail,
    dependencies=[RateLimited],
    summary="Triage a finding (acknowledge, dismiss, mark false positive)",
)
def update_status(
    finding_id: str,
    payload: FindingStatusUpdate,
    request: Request,
    user: CurrentUser,
    session: SessionDep,
) -> FindingDetail:
    finding = load_finding(finding_id, session, user)
    finding.status = payload.status
    session.add(finding)
    session.commit()
    session.refresh(finding)

    audit.record(
        session,
        action=f"finding.{payload.status.value}",
        entity_type="finding",
        entity_id=finding.id,
        user_id=user.id,
        metadata={"target": f"{finding.file_path}:{finding.start_line}", "note": payload.note},
        ip_address=client_ip(request),
    )
    detail = FindingDetail.model_validate(finding)
    detail.patches = [
        PatchRead.model_validate(p)
        for p in session.exec(select(Patch).where(Patch.finding_id == finding.id))
    ]
    return detail


@router.post(
    "/{finding_id}/generate-fix",
    response_model=PatchRead,
    dependencies=[RateLimited],
    summary="Generate a fix for a single finding on demand",
)
async def generate_fix(
    finding_id: str, request: Request, user: CurrentUser, session: SessionDep
) -> PatchRead:
    """Generate a patch outside the main pipeline.

    The analysis workspace is deleted once an analysis completes (retention
    policy), so the file is re-fetched from GitHub at the pull request's head
    SHA. Syntax validation runs immediately; the heavier validation steps run
    via `POST /patches/{id}/validate`.
    """
    finding = load_finding(finding_id, session, user)
    existing = session.exec(
        select(Patch).where(
            Patch.finding_id == finding.id, Patch.status != PatchStatus.REJECTED
        )
    ).first()
    if existing is not None:
        raise ConflictError(
            "A patch already exists for this finding",
            details={"patch_id": existing.id, "status": existing.status.value},
        )

    analysis = load_analysis(finding.analysis_id, session, user)
    pull_request = session.get(PullRequest, analysis.pull_request_id)
    repository = session.get(Repository, pull_request.repository_id)
    installation = session.get(GitHubInstallation, repository.installation_id)

    if installation is None or not installation.encrypted_access_token:
        raise ValidationError(
            "On-demand fix generation needs a connected GitHub repository so the current file "
            "contents can be fetched. The demo workspace ships with pre-generated fixes."
        )

    token = await resolve_token(session, installation)
    async with GitHubClient(token) as gh:
        content = await gh.get_file_content(
            repository.owner, repository.name, finding.file_path, pull_request.head_sha
        )

    source_file = SourceFile(
        path=finding.file_path,
        content=content,
        language=Language.from_path(finding.file_path),
        size_bytes=len(content),
    )

    settings_row = get_or_create_settings(session, repository)
    provider = get_provider(settings_row.preferred_llm_provider, settings_row.preferred_llm_model)
    usage = UsageTracker(budget_usd=settings_row.max_analysis_cost)

    domain_finding = context_findings([finding])[0]
    outcome = await FixGenerator(provider).generate(domain_finding, source_file, usage)
    if outcome.proposal is None:
        raise ValidationError(outcome.reason or "No safe automated fix could be generated")

    patch = Patch(
        finding_id=finding.id,
        file_path=outcome.proposal.file_path,
        original_code=outcome.proposal.original_code,
        suggested_code=outcome.proposal.suggested_code,
        unified_diff=outcome.proposal.unified_diff,
        explanation=outcome.proposal.explanation,
        expected_impact=outcome.proposal.expected_impact,
        side_effects=outcome.proposal.side_effects,
        risk_level=outcome.proposal.risk_level,
        generated_by=outcome.generated_by,
        status=PatchStatus.PROPOSED,
        validation_status=ValidationStatus.PENDING,
    )
    session.add(patch)
    finding.status = FindingStatus.FIX_PROPOSED
    session.add(finding)

    analysis.prompt_tokens += usage.prompt_tokens
    analysis.completion_tokens += usage.completion_tokens
    analysis.token_usage += usage.total_tokens
    analysis.estimated_cost += usage.cost
    session.add(analysis)
    session.commit()
    session.refresh(patch)

    audit.record(
        session,
        action="patch.generated",
        entity_type="patch",
        entity_id=patch.id,
        user_id=user.id,
        metadata={"target": f"{finding.file_path}:{finding.start_line}", "by": outcome.generated_by},
        ip_address=client_ip(request),
    )
    return PatchRead.model_validate(patch)
