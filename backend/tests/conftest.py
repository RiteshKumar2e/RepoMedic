"""Shared test fixtures.

The database URL is set **before** any application import so `app.core.config`
binds to a throwaway SQLite file instead of the developer's local database.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

_TMP_DIR = Path(tempfile.mkdtemp(prefix="repomedic-tests-"))

os.environ.setdefault("APP_ENV", "test")
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP_DIR / 'test.db').as_posix()}"
os.environ["WORKSPACE_ROOT"] = str(_TMP_DIR / "workspaces")
os.environ["DEMO_MODE"] = "true"
os.environ["DEFAULT_LLM_PROVIDER"] = "heuristic"
os.environ["REDIS_URL"] = ""
os.environ["JWT_SECRET"] = "test-secret-not-used-in-production"
os.environ["SANDBOX_MODE"] = "subprocess"
os.environ["ALLOW_HOST_TEST_EXECUTION"] = "false"


@pytest.fixture(scope="session")
def client() -> Iterator[TestClient]:  # noqa: F821
    """A TestClient with the lifespan run, so the demo workspace is seeded."""
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def authed_client(client):
    """TestClient carrying a demo session cookie."""
    response = client.post("/api/v1/auth/demo")
    assert response.status_code == 200, response.text
    return client


@pytest.fixture(scope="session")
def demo_analysis(authed_client) -> dict:
    """The seeded demo analysis, with its repository and pull request."""
    repositories = authed_client.get("/api/v1/repositories").json()
    assert repositories, "demo seeding produced no repositories"
    repository = repositories[0]

    pull_requests = authed_client.get(
        f"/api/v1/repositories/{repository['id']}/pull-requests"
    ).json()
    assert pull_requests, "demo seeding produced no pull requests"

    detail = authed_client.get(f"/api/v1/pull-requests/{pull_requests[0]['id']}").json()
    assert detail["latest_analysis_id"], "demo seeding produced no analysis"

    return {
        "repository": repository,
        "pull_request": detail,
        "analysis_id": detail["latest_analysis_id"],
    }


@pytest.fixture(scope="session")
def fixture_repo_path() -> Path:
    from app.services.demo import fixture_path

    return fixture_path()
