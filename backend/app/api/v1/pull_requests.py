"""Pull-request detail and analysis triggering."""

from __future__ import annotations

from fastapi import APIRouter, Request, status
from sqlmodel import select

from app.api.deps import (
    CurrentUser,
    RateLimited,
    SessionDep,
    client_ip,
    load_pull_request,
    load_repository,
)
from app.core.errors import ConflictError
from app.core.logging import get_logger
from app.models.entities import Analysis
from app.models.enums import AnalysisStatus
from app.schemas.analysis import AnalysisRead, AnalyzeRequest
from app.schemas.repository import PullRequestDetail, RepositoryRead
from app.services import audit
from app.services.analysis_pipeline import create_analysis, latest_analysis
from app.workers.queue import enqueue_analysis

logger = get_logger(__name__)
router = APIRouter(prefix="/pull-requests", tags=["pull-requests"])


@router.get("/{pull_request_id}", response_model=PullRequestDetail, summary="Pull-request detail")
def get_pull_request(
    pull_request_id: str, user: CurrentUser, session: SessionDep
) -> PullRequestDetail:
    pr = load_pull_request(pull_request_id, session, user)
    repository = load_repository(pr.repository_id, session, user)
    analyses = list(
        session.exec(
            select(Analysis)
            .where(Analysis.pull_request_id == pr.id)
            .order_by(Analysis.created_at.desc())
        )
    )
    detail = PullRequestDetail.model_validate(pr)
    detail.repository = RepositoryRead.model_validate(repository)
    detail.analysis_count = len(analyses)
    detail.latest_analysis_id = analyses[0].id if analyses else None
    return detail


@router.get(
    "/{pull_request_id}/analyses",
    response_model=list[AnalysisRead],
    summary="Analysis history for a pull request",
)
def list_analyses(
    pull_request_id: str, user: CurrentUser, session: SessionDep
) -> list[AnalysisRead]:
    pr = load_pull_request(pull_request_id, session, user)
    rows = session.exec(
        select(Analysis)
        .where(Analysis.pull_request_id == pr.id)
        .order_by(Analysis.created_at.desc())
    )
    return [AnalysisRead.model_validate(row) for row in rows]


@router.post(
    "/{pull_request_id}/analyze",
    response_model=AnalysisRead,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[RateLimited],
    summary="Queue a repository-aware analysis",
)
def analyze_pull_request(
    pull_request_id: str,
    request: Request,
    user: CurrentUser,
    session: SessionDep,
    payload: AnalyzeRequest = AnalyzeRequest(),
) -> AnalysisRead:
    """Queue an analysis and return immediately.

    Progress streams from `GET /analyses/{id}/events`.
    """
    pr = load_pull_request(pull_request_id, session, user)

    existing = latest_analysis(session, pr.id)
    if (
        existing is not None
        and existing.status in (AnalysisStatus.QUEUED, AnalysisStatus.RUNNING)
        and not payload.force
    ):
        raise ConflictError(
            "An analysis is already running for this pull request",
            details={"analysis_id": existing.id, "status": existing.status.value},
        )

    analysis = create_analysis(session, pr, triggered_by="manual")
    backend = enqueue_analysis(analysis.id)

    audit.record(
        session,
        action="analysis.started",
        entity_type="analysis",
        entity_id=analysis.id,
        user_id=user.id,
        metadata={"target": f"PR #{pr.github_pr_number}", "queue": backend},
        ip_address=client_ip(request),
    )
    return AnalysisRead.model_validate(analysis)
