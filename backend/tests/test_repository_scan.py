"""Whole-repository scans: the synthetic target, scan mode, and the endpoint."""

from __future__ import annotations

from app.services.analysis_pipeline import REPOSITORY_SCAN_TRIGGER
from app.services.repository_scan import (
    SCAN_PR_NUMBER,
    create_scan,
    get_or_create_scan_target,
    is_scan_running,
    latest_scan,
)


def _repository(session):
    from sqlmodel import select

    from app.models.entities import Repository

    return session.exec(select(Repository)).first()


# --------------------------------------------------------------------------- #
# Synthetic scan target
# --------------------------------------------------------------------------- #
def test_scan_target_is_created_once_and_tracks_the_default_branch(authed_client):
    from app.db.session import session_scope

    with session_scope() as session:
        repository = _repository(session)
        assert repository is not None, "fixture seeding produced no repository"

        first = get_or_create_scan_target(session, repository)
        second = get_or_create_scan_target(session, repository)

        assert first.id == second.id, "a repository must have exactly one scan target"
        assert first.github_pr_number == SCAN_PR_NUMBER
        # Branching and the fix PR both key off head_ref.
        assert first.head_ref == repository.default_branch
        assert first.base_ref == repository.default_branch


def test_scan_target_follows_a_renamed_default_branch(authed_client):
    from app.db.session import session_scope

    with session_scope() as session:
        repository = _repository(session)
        original = repository.default_branch

        repository.default_branch = "trunk"
        session.add(repository)
        session.commit()
        try:
            target = get_or_create_scan_target(session, repository)
            assert target.head_ref == "trunk"
            assert target.base_ref == "trunk"
        finally:
            repository.default_branch = original
            session.add(repository)
            session.commit()


def test_scan_target_never_collides_with_a_real_pull_request(authed_client):
    """Real pull requests are numbered from 1, so 0 is a safe sentinel."""
    from sqlmodel import select

    from app.db.session import session_scope
    from app.models.entities import PullRequest

    with session_scope() as session:
        repository = _repository(session)
        get_or_create_scan_target(session, repository)

        numbers = [
            pr.github_pr_number
            for pr in session.exec(
                select(PullRequest).where(PullRequest.repository_id == repository.id)
            )
        ]

    assert numbers.count(SCAN_PR_NUMBER) == 1
    assert all(n > 0 for n in numbers if n != SCAN_PR_NUMBER)


# --------------------------------------------------------------------------- #
# Scan mode
# --------------------------------------------------------------------------- #
def test_scan_analysis_is_marked_as_a_full_scan(authed_client):
    from app.db.session import session_scope
    from app.services.analysis_pipeline import AnalysisPipeline

    with session_scope() as session:
        repository = _repository(session)
        analysis = create_scan(session, repository)

        assert analysis.triggered_by == REPOSITORY_SCAN_TRIGGER
        assert AnalysisPipeline(session, analysis).is_full_scan is True


def test_pull_request_analysis_is_not_a_full_scan(authed_client, demo_analysis):
    from app.db.session import session_scope
    from app.models.entities import Analysis
    from app.services.analysis_pipeline import AnalysisPipeline

    with session_scope() as session:
        analysis = session.get(Analysis, demo_analysis["analysis_id"])

        assert AnalysisPipeline(session, analysis).is_full_scan is False


def test_latest_scan_tracks_the_newest_scan(authed_client):
    from app.db.session import session_scope

    with session_scope() as session:
        repository = _repository(session)
        create_scan(session, repository)
        newest = create_scan(session, repository)

        assert latest_scan(session, repository).id == newest.id
        assert is_scan_running(newest) is True


# --------------------------------------------------------------------------- #
# Endpoint
# --------------------------------------------------------------------------- #
def test_scan_endpoint_requires_authentication(client):
    # The TestClient is session-scoped, so its cookies are restored afterwards
    # rather than left cleared for whichever test runs next.
    saved = dict(client.cookies)
    client.cookies.clear()
    try:
        assert client.post("/api/v1/repositories/does-not-exist/scan").status_code == 401
    finally:
        for name, value in saved.items():
            client.cookies.set(name, value)


def test_scan_endpoint_rejects_a_repository_the_caller_does_not_own(authed_client):
    response = authed_client.post("/api/v1/repositories/not-a-real-id/scan")

    assert response.status_code == 404
