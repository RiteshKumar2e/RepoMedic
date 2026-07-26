"""Background task bodies."""

from __future__ import annotations

from app.core.logging import get_logger
from app.db.session import session_scope
from app.models.entities import Analysis
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
