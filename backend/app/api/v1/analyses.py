"""Analysis detail, findings, SSE progress stream, review publishing and fix PRs."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from sqlmodel import select

from app.api.deps import (
    CurrentUser,
    RateLimited,
    SessionDep,
    load_analysis,
)
from app.core.errors import ValidationError
from app.core.logging import get_logger
from app.models.entities import Finding, Patch
from app.models.enums import (
    AnalysisStatus,
    FindingCategory,
    FindingSource,
    FindingStatus,
    Severity,
)
from app.schemas.analysis import (
    AnalysisDetail,
    AnalysisSummary,
    CreateFixPRRequest,
    CreateFixPRResponse,
    FindingRead,
    PatchRead,
    PublishReviewRequest,
    PublishReviewResponse,
)
from app.schemas.graph import GraphResponse
from app.services import analytics, events, github_actions
from app.workers.tasks import cancel_analysis

logger = get_logger(__name__)
router = APIRouter(prefix="/analyses", tags=["analyses"])


@router.get("/{analysis_id}", response_model=AnalysisDetail, summary="Analysis detail")
def get_analysis(analysis_id: str, user: CurrentUser, session: SessionDep) -> AnalysisDetail:
    analysis = load_analysis(analysis_id, session, user)
    detail = AnalysisDetail.model_validate(analysis)
    detail.summary_stats = AnalysisSummary(**analytics.analysis_summary_stats(session, analysis.id))
    return detail


@router.get(
    "/{analysis_id}/findings",
    response_model=list[FindingRead],
    summary="Findings for an analysis, with filters",
)
def list_findings(
    analysis_id: str,
    user: CurrentUser,
    session: SessionDep,
    severity: list[Severity] | None = Query(default=None),
    category: list[FindingCategory] | None = Query(default=None),
    source: list[FindingSource] | None = Query(default=None),
    finding_status: list[FindingStatus] | None = Query(default=None, alias="status"),
    file_path: str | None = Query(default=None),
    min_confidence: float = Query(default=0.0, ge=0.0, le=1.0),
) -> list[FindingRead]:
    analysis = load_analysis(analysis_id, session, user)

    statement = select(Finding).where(Finding.analysis_id == analysis.id)
    if severity:
        statement = statement.where(Finding.severity.in_(severity))
    if category:
        statement = statement.where(Finding.category.in_(category))
    if source:
        statement = statement.where(Finding.source.in_(source))
    if finding_status:
        statement = statement.where(Finding.status.in_(finding_status))
    if file_path:
        statement = statement.where(Finding.file_path == file_path)
    if min_confidence:
        statement = statement.where(Finding.confidence >= min_confidence)

    rows = session.exec(statement.order_by(Finding.score.desc()))
    return [FindingRead.model_validate(row) for row in rows]


@router.get(
    "/{analysis_id}/patches",
    response_model=list[PatchRead],
    summary="All patches produced by an analysis",
)
def list_patches(analysis_id: str, user: CurrentUser, session: SessionDep) -> list[PatchRead]:
    analysis = load_analysis(analysis_id, session, user)
    finding_ids = [
        row.id for row in session.exec(select(Finding).where(Finding.analysis_id == analysis.id))
    ]
    if not finding_ids:
        return []
    rows = session.exec(
        select(Patch).where(Patch.finding_id.in_(finding_ids)).order_by(Patch.confidence.desc())
    )
    return [PatchRead.model_validate(row) for row in rows]


@router.get(
    "/{analysis_id}/graph",
    response_model=GraphResponse,
    summary="Knowledge graph captured during this analysis",
)
def get_analysis_graph(analysis_id: str, user: CurrentUser, session: SessionDep) -> GraphResponse:
    analysis = load_analysis(analysis_id, session, user)
    snapshot = analysis.graph_snapshot or {}
    findings = list(session.exec(select(Finding).where(Finding.analysis_id == analysis.id)))

    counts: dict[str, list[Finding]] = {}
    for finding in findings:
        counts.setdefault(f"file:{finding.file_path}", []).append(finding)

    nodes = []
    for node in snapshot.get("nodes", []):
        node_findings = counts.get(node["id"], [])
        nodes.append(
            {
                **node,
                "finding_count": len(node_findings),
                "max_severity": (
                    max(node_findings, key=lambda f: f.severity.rank).severity.value
                    if node_findings
                    else None
                ),
            }
        )
    return GraphResponse(
        nodes=nodes,
        edges=snapshot.get("edges", []),
        stats=snapshot.get("stats", {}),
        generated_at=analysis.completed_at.isoformat() if analysis.completed_at else None,
        truncated=bool(snapshot.get("stats", {}).get("nodes", 0) >= 1200),
    )


@router.get("/{analysis_id}/events", summary="Server-Sent Events progress stream")
async def stream_events(analysis_id: str, user: CurrentUser, session: SessionDep) -> StreamingResponse:
    """Live pipeline progress.

    Replays everything already emitted, then streams new events until the
    analysis reaches a terminal state. Heartbeats keep proxies from closing idle
    connections.
    """
    analysis = load_analysis(analysis_id, session, user)
    terminal = analysis.status in (
        AnalysisStatus.COMPLETED,
        AnalysisStatus.FAILED,
        AnalysisStatus.CANCELLED,
    )

    async def generator() -> AsyncIterator[bytes]:
        if terminal:
            for message in events.history(analysis.id):
                yield _sse(message)
            yield _sse(
                {
                    "type": analysis.status.value,
                    "analysis_id": analysis.id,
                    "progress": analysis.progress,
                    "stage": analysis.stage,
                }
            )
            return

        try:
            async for message in events.subscribe(analysis.id):
                yield _sse(message)
        except asyncio.CancelledError:  # client disconnected
            return

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/{analysis_id}/cancel",
    response_model=AnalysisDetail,
    dependencies=[RateLimited],
    summary="Cancel a running analysis",
)
def cancel(analysis_id: str, user: CurrentUser, session: SessionDep) -> AnalysisDetail:
    analysis = load_analysis(analysis_id, session, user)
    cancel_analysis(analysis.id, reason=f"cancelled by {user.login or user.id}")
    session.refresh(analysis)
    detail = AnalysisDetail.model_validate(analysis)
    detail.summary_stats = AnalysisSummary(**analytics.analysis_summary_stats(session, analysis.id))
    return detail


@router.post(
    "/{analysis_id}/publish-review",
    response_model=PublishReviewResponse,
    dependencies=[RateLimited],
    summary="Post the AI review on the original pull request",
)
async def publish_review(
    analysis_id: str,
    payload: PublishReviewRequest,
    request: Request,
    user: CurrentUser,
    session: SessionDep,
) -> PublishReviewResponse:
    analysis = load_analysis(analysis_id, session, user)
    if analysis.status is not AnalysisStatus.COMPLETED and not payload.dry_run:
        raise ValidationError("The analysis has not completed yet")
    if user.is_demo and not payload.dry_run:
        raise ValidationError(
            "The demo account cannot write to GitHub. Use `dry_run: true` to preview the review body."
        )

    result = await github_actions.publish_review(
        session,
        analysis,
        min_severity=payload.min_severity,
        include_inline_comments=payload.include_inline_comments,
        dry_run=payload.dry_run,
        user_id=user.id,
    )
    return PublishReviewResponse(**result)


@router.post(
    "/{analysis_id}/create-fix-pr",
    response_model=CreateFixPRResponse,
    dependencies=[RateLimited],
    summary="Open a pull request containing the approved fixes",
)
async def create_fix_pr(
    analysis_id: str,
    payload: CreateFixPRRequest,
    request: Request,
    user: CurrentUser,
    session: SessionDep,
) -> CreateFixPRResponse:
    analysis = load_analysis(analysis_id, session, user)
    if user.is_demo and not payload.dry_run:
        raise ValidationError(
            "The demo account cannot write to GitHub. Use `dry_run: true` to preview the combined diff."
        )

    result = await github_actions.create_fix_pull_request(
        session,
        analysis,
        patch_ids=payload.patch_ids,
        branch_name=payload.branch_name,
        title=payload.title,
        dry_run=payload.dry_run,
        user_id=user.id,
    )
    return CreateFixPRResponse(**result)


def _sse(message: dict) -> bytes:
    event_type = message.get("type", "message")
    return f"event: {event_type}\ndata: {json.dumps(message)}\n\n".encode()
