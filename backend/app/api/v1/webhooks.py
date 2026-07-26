"""GitHub webhook receiver.

Every request is signature-verified before the body is parsed. Unverified
requests are rejected with 401 and never reach any handler.
"""

from __future__ import annotations

from fastapi import APIRouter, Header, Request
from sqlmodel import select

from app.api.deps import SessionDep
from app.core.config import settings
from app.core.errors import AuthenticationError
from app.core.logging import get_logger
from app.core.security import verify_webhook_signature
from app.github.service import upsert_pull_request_from_payload
from app.models.entities import Repository
from app.models.enums import PullRequestStatus
from app.schemas.common import Acknowledgement
from app.services import audit
from app.services.analysis_pipeline import create_analysis
from app.services.repositories import get_or_create_settings
from app.workers.queue import enqueue_analysis

logger = get_logger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])

HANDLED_ACTIONS = {"opened", "synchronize", "reopened", "ready_for_review", "review_requested"}


@router.post("/github", response_model=Acknowledgement, summary="Receive GitHub webhook events")
async def github_webhook(
    request: Request,
    session: SessionDep,
    x_hub_signature_256: str | None = Header(default=None, alias="X-Hub-Signature-256"),
    x_github_event: str = Header(default="", alias="X-GitHub-Event"),
    x_github_delivery: str = Header(default="", alias="X-GitHub-Delivery"),
) -> Acknowledgement:
    body = await request.body()

    if not settings.github_webhook_secret:
        raise AuthenticationError("Webhook processing is disabled: GITHUB_WEBHOOK_SECRET is unset")
    if not verify_webhook_signature(body, x_hub_signature_256):
        logger.warning("webhook.signature_invalid", event=x_github_event, delivery=x_github_delivery)
        raise AuthenticationError("Invalid webhook signature")

    payload = await request.json()
    logger.info("webhook.received", event=x_github_event, action=payload.get("action"))
    audit.record(
        session,
        action="webhook.received",
        entity_type="webhook",
        entity_id=x_github_delivery or None,
        metadata={"event": x_github_event, "action": payload.get("action")},
    )

    if x_github_event == "ping":
        return Acknowledgement(message="pong")
    if x_github_event == "pull_request":
        return await _handle_pull_request(session, payload)
    if x_github_event in ("check_suite", "check_run"):
        return Acknowledgement(message=f"{x_github_event} acknowledged")
    if x_github_event == "installation":
        return Acknowledgement(message="installation event acknowledged")

    return Acknowledgement(message=f"{x_github_event or 'unknown'} event ignored")


async def _handle_pull_request(session, payload: dict) -> Acknowledgement:
    action = payload.get("action", "")
    if action not in HANDLED_ACTIONS:
        return Acknowledgement(message=f"pull_request.{action} ignored")

    repo_payload = payload.get("repository") or {}
    repository = session.exec(
        select(Repository).where(Repository.github_repository_id == repo_payload.get("id"))
    ).first()
    if repository is None:
        logger.info("webhook.unknown_repository", repository=repo_payload.get("full_name"))
        return Acknowledgement(ok=False, message="Repository is not connected to RepoMedic")

    pr = await upsert_pull_request_from_payload(session, repository, payload["pull_request"])

    repo_settings = get_or_create_settings(session, repository)
    if not repo_settings.auto_scan_enabled:
        return Acknowledgement(message="Pull request recorded; auto-scan is disabled")
    if pr.status is PullRequestStatus.DRAFT and action != "ready_for_review":
        return Acknowledgement(message="Draft pull request recorded; analysis deferred")

    analysis = create_analysis(session, pr, triggered_by=f"webhook:{action}")
    enqueue_analysis(analysis.id)
    audit.record(
        session,
        action="analysis.started",
        entity_type="analysis",
        entity_id=analysis.id,
        metadata={"target": f"{repository.full_name}#{pr.github_pr_number}", "trigger": action},
    )
    return Acknowledgement(message=f"Analysis {analysis.id} queued")
