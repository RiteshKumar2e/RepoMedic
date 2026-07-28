"""Background task bodies."""

from __future__ import annotations

from sqlmodel import select

from app.core.logging import get_logger
from app.db.session import session_scope
from app.models.entities import Analysis, utcnow
from app.models.enums import AnalysisStatus
from app.services import events
from app.services.analysis_pipeline import AnalysisPipeline
from app.services.workspace import sweep_stale_workspaces
from app.workers.queue import run_coroutine

logger = get_logger(__name__)


def run_analysis_sync(analysis_id: str) -> None:
    """Entry point used by both the Dramatiq actor and the thread executor."""
    with session_scope() as session:
        analysis = session.get(Analysis, analysis_id)
        if analysis is None:
            logger.warning("task.analysis_missing", analysis_id=analysis_id)
            return
        if analysis.status not in (AnalysisStatus.QUEUED, AnalysisStatus.RUNNING):
            logger.info("task.analysis_already_finished", analysis_id=analysis_id)
            return

        pipeline = AnalysisPipeline(session, analysis)
        run_coroutine(pipeline.run())


def recover_interrupted_analyses() -> int:
    """Fail analyses left mid-flight by a previous process.

    Analyses run in a daemon thread (or a Dramatiq worker), and their working
    files live in a workspace that is swept on boot. When the process dies —
    a deploy, an idle-instance restart, an out-of-memory kill — anything still
    QUEUED or RUNNING is unrecoverable: the workspace is gone and the thread
    with it.

    Without this they stay QUEUED forever, which surfaces as a scan that never
    finishes and a knowledge graph that never appears. Marking them failed is
    honest and lets the user retry; silently requeuing would loop indefinitely
    if the cause was an out-of-memory kill.
    """
    stale = 0
    with session_scope() as session:
        rows = session.exec(
            select(Analysis).where(
                Analysis.status.in_([AnalysisStatus.QUEUED, AnalysisStatus.RUNNING])
            )
        )
        for analysis in rows:
            analysis.status = AnalysisStatus.FAILED
            analysis.progress = 100
            analysis.error_message = (
                "Interrupted by a server restart before it could finish. Run it again."
            )
            analysis.completed_at = utcnow()
            session.add(analysis)
            stale += 1

    if stale:
        logger.warning("task.recovered_interrupted_analyses", count=stale)
    return stale


def cleanup_workspaces() -> int:
    """Delete workspaces past the retention window."""
    return sweep_stale_workspaces()


def cancel_analysis(analysis_id: str, reason: str = "cancelled by user") -> None:
    with session_scope() as session:
        analysis = session.get(Analysis, analysis_id)
        if analysis is None or analysis.status in (AnalysisStatus.COMPLETED, AnalysisStatus.FAILED):
            return
        analysis.status = AnalysisStatus.CANCELLED
        analysis.error_message = reason
        analysis.progress = 100
        session.add(analysis)
    events.publish(analysis_id, "cancelled", {"reason": reason, "progress": 100})
