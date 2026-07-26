"""Async GitHub REST + GraphQL client.

Handles authentication, retries, secondary rate limits and error translation.
All network access to GitHub goes through this class.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.core.config import settings
from app.core.errors import ExternalServiceError, NotFoundError
from app.core.logging import get_logger

logger = get_logger(__name__)

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_MAX_RETRIES = 3


class GitHubClient:
    """Thin, typed wrapper around the GitHub API.

    Usage::

        async with GitHubClient(token) as gh:
            repos = await gh.list_repositories()
    """

    def __init__(self, token: str, *, base_url: str | None = None) -> None:
        self._token = token
        self._base_url = (base_url or settings.github_api_url).rstrip("/")
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> GitHubClient:
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(30.0, connect=10.0),
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": f"{settings.app_name}/1.0",
            },
        )
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # ---- transport -------------------------------------------------------
    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        if self._client is None:
            raise RuntimeError("GitHubClient must be used as an async context manager")

        last_error: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                response = await self._client.request(method, path, **kwargs)
            except httpx.HTTPError as exc:
                last_error = exc
                await asyncio.sleep(2**attempt * 0.5)
                continue

            if response.status_code == 404:
                raise NotFoundError(f"GitHub resource not found: {path}")
            if response.status_code in _RETRYABLE_STATUS and attempt < _MAX_RETRIES - 1:
                delay = float(response.headers.get("retry-after", 2**attempt))
                logger.warning(
                    "github.retry", path=path, status=response.status_code, delay=delay
                )
                await asyncio.sleep(min(delay, 10.0))
                continue
            if response.status_code >= 400:
                raise ExternalServiceError(
                    f"GitHub API error {response.status_code} on {method} {path}",
                    details={"body": response.text[:500]},
                )
            return response

        raise ExternalServiceError(
            f"GitHub API unreachable for {method} {path}", details={"cause": str(last_error)}
        )

    async def get(self, path: str, **kwargs: Any) -> Any:
        return (await self._request("GET", path, **kwargs)).json()

    async def post(self, path: str, **kwargs: Any) -> Any:
        return (await self._request("POST", path, **kwargs)).json()

    async def put(self, path: str, **kwargs: Any) -> Any:
        return (await self._request("PUT", path, **kwargs)).json()

    async def patch(self, path: str, **kwargs: Any) -> Any:
        return (await self._request("PATCH", path, **kwargs)).json()

    async def paginate(self, path: str, *, limit: int = 200, **kwargs: Any) -> list[dict]:
        """Follow ``Link: rel="next"`` headers until ``limit`` items are collected."""
        results: list[dict] = []
        params = dict(kwargs.pop("params", {}) or {})
        params.setdefault("per_page", 100)
        url = path
        while url and len(results) < limit:
            response = await self._request("GET", url, params=params, **kwargs)
            payload = response.json()
            page = payload if isinstance(payload, list) else payload.get("items", [])
            results.extend(page)
            link = response.headers.get("link", "")
            url = _next_link(link)
            params = {}  # the next URL already carries its query string
        return results[:limit]

    async def graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict:
        payload = {"query": query, "variables": variables or {}}
        data = await self.post("/graphql", json=payload)
        if "errors" in data:
            raise ExternalServiceError("GitHub GraphQL error", details={"errors": data["errors"]})
        return data.get("data", {})

    # ---- viewer / repositories ------------------------------------------
    async def get_authenticated_user(self) -> dict:
        return await self.get("/user")

    async def get_user_emails(self) -> list[dict]:
        try:
            return await self.get("/user/emails")
        except ExternalServiceError:
            return []

    async def list_repositories(self, limit: int = 100) -> list[dict]:
        return await self.paginate(
            "/user/repos", limit=limit, params={"sort": "updated", "affiliation": "owner,collaborator,organization_member"}
        )

    async def list_installation_repositories(self, limit: int = 100) -> list[dict]:
        response = await self.get("/installation/repositories", params={"per_page": 100})
        return list(response.get("repositories", []))[:limit]

    async def get_repository(self, owner: str, repo: str) -> dict:
        return await self.get(f"/repos/{owner}/{repo}")

    async def get_repository_languages(self, owner: str, repo: str) -> dict[str, int]:
        return await self.get(f"/repos/{owner}/{repo}/languages")

    # ---- pull requests ---------------------------------------------------
    async def list_pull_requests(self, owner: str, repo: str, state: str = "open", limit: int = 50) -> list[dict]:
        return await self.paginate(
            f"/repos/{owner}/{repo}/pulls",
            limit=limit,
            params={"state": state, "sort": "updated", "direction": "desc"},
        )

    async def get_pull_request(self, owner: str, repo: str, number: int) -> dict:
        return await self.get(f"/repos/{owner}/{repo}/pulls/{number}")

    async def list_pull_request_files(self, owner: str, repo: str, number: int, limit: int = 300) -> list[dict]:
        return await self.paginate(f"/repos/{owner}/{repo}/pulls/{number}/files", limit=limit)

    async def compare_commits(self, owner: str, repo: str, base: str, head: str) -> dict:
        return await self.get(f"/repos/{owner}/{repo}/compare/{base}...{head}")

    async def get_file_content(self, owner: str, repo: str, path: str, ref: str) -> str:
        """Fetch a single file at a ref, decoded to text."""
        import base64

        data = await self.get(f"/repos/{owner}/{repo}/contents/{path}", params={"ref": ref})
        if isinstance(data, list):
            raise NotFoundError(f"{path} is a directory, not a file")
        content = data.get("content", "")
        if data.get("encoding") == "base64":
            return base64.b64decode(content).decode("utf-8", errors="replace")
        return content

    # ---- review output ---------------------------------------------------
    async def create_issue_comment(self, owner: str, repo: str, number: int, body: str) -> dict:
        return await self.post(f"/repos/{owner}/{repo}/issues/{number}/comments", json={"body": body})

    async def create_review(
        self,
        owner: str,
        repo: str,
        number: int,
        body: str,
        comments: list[dict] | None = None,
        event: str = "COMMENT",
    ) -> dict:
        payload: dict[str, Any] = {"body": body, "event": event}
        if comments:
            payload["comments"] = comments
        return await self.post(f"/repos/{owner}/{repo}/pulls/{number}/reviews", json=payload)

    async def list_review_comments(self, owner: str, repo: str, number: int) -> list[dict]:
        return await self.paginate(f"/repos/{owner}/{repo}/pulls/{number}/comments")

    async def add_labels(self, owner: str, repo: str, number: int, labels: list[str]) -> list[dict]:
        return await self.post(f"/repos/{owner}/{repo}/issues/{number}/labels", json={"labels": labels})

    # ---- branches, commits, PR creation ----------------------------------
    async def get_ref(self, owner: str, repo: str, ref: str) -> dict:
        return await self.get(f"/repos/{owner}/{repo}/git/ref/{ref}")

    async def create_branch(self, owner: str, repo: str, branch: str, from_sha: str) -> dict:
        return await self.post(
            f"/repos/{owner}/{repo}/git/refs",
            json={"ref": f"refs/heads/{branch}", "sha": from_sha},
        )

    async def get_file_sha(self, owner: str, repo: str, path: str, ref: str) -> str | None:
        try:
            data = await self.get(f"/repos/{owner}/{repo}/contents/{path}", params={"ref": ref})
            return data.get("sha") if isinstance(data, dict) else None
        except NotFoundError:
            return None

    async def put_file(
        self,
        owner: str,
        repo: str,
        path: str,
        content: str,
        message: str,
        branch: str,
        sha: str | None = None,
    ) -> dict:
        import base64

        payload: dict[str, Any] = {
            "message": message,
            "content": base64.b64encode(content.encode()).decode(),
            "branch": branch,
        }
        if sha:
            payload["sha"] = sha
        return await self.put(f"/repos/{owner}/{repo}/contents/{path}", json=payload)

    async def create_pull_request(
        self, owner: str, repo: str, title: str, head: str, base: str, body: str, draft: bool = False
    ) -> dict:
        return await self.post(
            f"/repos/{owner}/{repo}/pulls",
            json={"title": title, "head": head, "base": base, "body": body, "draft": draft},
        )

    # ---- checks ----------------------------------------------------------
    async def create_check_run(
        self,
        owner: str,
        repo: str,
        head_sha: str,
        name: str,
        status: str = "in_progress",
        conclusion: str | None = None,
        output: dict | None = None,
    ) -> dict:
        payload: dict[str, Any] = {"name": name, "head_sha": head_sha, "status": status}
        if conclusion:
            payload["conclusion"] = conclusion
            payload["status"] = "completed"
        if output:
            payload["output"] = output
        return await self.post(f"/repos/{owner}/{repo}/check-runs", json=payload)

    async def update_check_run(
        self, owner: str, repo: str, check_run_id: int, **fields: Any
    ) -> dict:
        return await self.patch(f"/repos/{owner}/{repo}/check-runs/{check_run_id}", json=fields)

    async def list_check_runs(self, owner: str, repo: str, ref: str) -> list[dict]:
        data = await self.get(f"/repos/{owner}/{repo}/commits/{ref}/check-runs")
        return list(data.get("check_runs", []))


def _next_link(link_header: str) -> str | None:
    for part in link_header.split(","):
        section = part.split(";")
        if len(section) < 2:
            continue
        if 'rel="next"' in section[1].strip():
            return section[0].strip().strip("<>")
    return None
