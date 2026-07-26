"""Append-only audit trail.

Every state-changing action (analysis start, patch approval, GitHub write)
records an entry so the platform can answer "who changed what, when, and why".
"""

from __future__ import annotations

from typing import Any

from sqlmodel import Session, select

from app.core.logging import get_logger
from app.models.entities import AuditLog

logger = get_logger(__name__)


def record(
    session: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    user_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    ip_address: str | None = None,
    commit: bool = True,
) -> AuditLog:
    entry = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        metadata_json=metadata or {},
        ip_address=ip_address,
    )
    session.add(entry)
    if commit:
        session.commit()
        session.refresh(entry)
    logger.info("audit", action=action, entity_type=entity_type, entity_id=entity_id)
    return entry


def recent(session: Session, *, limit: int = 20, user_id: str | None = None) -> list[AuditLog]:
    statement = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    if user_id:
        statement = (
            select(AuditLog)
            .where(AuditLog.user_id == user_id)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
    return list(session.exec(statement))


def humanize(entry: AuditLog) -> str:
    """Readable one-liner for the activity feed."""
    meta = entry.metadata_json or {}
    templates = {
        "analysis.started": "Analysis started on {target}",
        "analysis.completed": "Analysis completed with {findings} findings",
        "analysis.failed": "Analysis failed: {error}",
        "patch.generated": "Fix proposed for {target}",
        "patch.approved": "Fix approved for {target}",
        "patch.rejected": "Fix rejected for {target}",
        "patch.validated": "Fix validated for {target}",
        "review.published": "AI review published on {target}",
        "fix_pr.created": "Fix pull request opened: {target}",
        "repository.synced": "Synced {count} repositories from GitHub",
        "auth.login": "Signed in via {method}",
        "webhook.received": "GitHub webhook received: {event}",
    }
    template = templates.get(entry.action, entry.action.replace(".", " ").replace("_", " ").capitalize())
    try:
        return template.format(
            target=meta.get("target", entry.entity_id or "resource"),
            findings=meta.get("findings", 0),
            error=meta.get("error", "unknown error"),
            count=meta.get("count", 0),
            method=meta.get("method", "GitHub"),
            event=meta.get("event", "event"),
        )
    except (KeyError, IndexError):
        return entry.action
