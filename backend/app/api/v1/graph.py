"""Repository knowledge-graph endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query
from sqlmodel import select

from app.api.deps import CurrentUser, SessionDep, load_finding, load_repository
from app.core.errors import NotFoundError
from app.models.entities import Analysis, Finding, PullRequest
from app.models.enums import AnalysisStatus
from app.schemas.graph import GraphResponse, ImpactPath

router = APIRouter(prefix="/repositories", tags=["graph"])


def _latest_graph_analysis(session, repository_id: str) -> Analysis | None:
    pr_ids = [
        row.id
        for row in session.exec(select(PullRequest).where(PullRequest.repository_id == repository_id))
    ]
    if not pr_ids:
        return None
    for analysis in session.exec(
        select(Analysis)
        .where(Analysis.pull_request_id.in_(pr_ids), Analysis.status == AnalysisStatus.COMPLETED)
        .order_by(Analysis.completed_at.desc())
    ):
        if analysis.graph_snapshot:
            return analysis
    return None


@router.get(
    "/{repository_id}/graph",
    response_model=GraphResponse,
    summary="Knowledge graph for a repository (from its most recent analysis)",
)
def get_repository_graph(
    repository_id: str,
    user: CurrentUser,
    session: SessionDep,
    node_types: list[str] | None = Query(default=None),
    limit: int = Query(default=600, ge=10, le=1200),
) -> GraphResponse:
    repository = load_repository(repository_id, session, user)
    analysis = _latest_graph_analysis(session, repository.id)
    if analysis is None:
        return GraphResponse(nodes=[], edges=[], stats={}, truncated=False)

    snapshot = analysis.graph_snapshot or {}
    findings = list(session.exec(select(Finding).where(Finding.analysis_id == analysis.id)))
    by_file: dict[str, list[Finding]] = {}
    for finding in findings:
        by_file.setdefault(finding.file_path, []).append(finding)

    nodes = []
    for node in snapshot.get("nodes", []):
        if node_types and node.get("type") not in node_types:
            continue
        file_findings = by_file.get(node.get("file_path", ""), [])
        nodes.append(
            {
                **node,
                "finding_count": len(file_findings),
                "max_severity": (
                    max(file_findings, key=lambda f: f.severity.rank).severity.value
                    if file_findings
                    else None
                ),
            }
        )

    truncated = len(nodes) > limit
    nodes = sorted(nodes, key=lambda n: (n["finding_count"], n.get("changed", False)), reverse=True)[:limit]
    node_ids = {n["id"] for n in nodes}
    edges = [e for e in snapshot.get("edges", []) if e["source"] in node_ids and e["target"] in node_ids]

    return GraphResponse(
        nodes=nodes,
        edges=edges,
        stats=snapshot.get("stats", {}),
        generated_at=analysis.completed_at.isoformat() if analysis.completed_at else None,
        truncated=truncated,
    )


@router.get(
    "/{repository_id}/graph/impact",
    response_model=ImpactPath,
    summary="Dependency path affected by a finding",
)
def get_impact_path(
    repository_id: str,
    finding_id: str,
    user: CurrentUser,
    session: SessionDep,
) -> ImpactPath:
    """Highlight the nodes and edges a finding can propagate through."""
    load_repository(repository_id, session, user)
    finding = load_finding(finding_id, session, user)
    analysis = session.get(Analysis, finding.analysis_id)
    snapshot = (analysis.graph_snapshot if analysis else None) or {}
    if not snapshot:
        raise NotFoundError("No knowledge graph is available for this analysis")

    origin = f"file:{finding.file_path}"
    node_ids = {origin}
    edge_ids: list[str] = []

    # Walk incoming import/call edges outward — these are the modules a defect
    # in this file can reach.
    frontier = {origin}
    for _ in range(2):
        next_frontier: set[str] = set()
        for edge in snapshot.get("edges", []):
            if edge["target"] in frontier and edge["type"] in ("imports", "calls", "tests"):
                node_ids.add(edge["source"])
                edge_ids.append(edge["id"])
                next_frontier.add(edge["source"])
        frontier = next_frontier
        if not frontier:
            break

    for related in finding.related_files or []:
        node_ids.add(f"file:{related}")

    return ImpactPath(
        finding_id=finding.id,
        nodes=sorted(node_ids),
        edges=edge_ids,
        explanation=(
            f"{len(node_ids) - 1} module(s) depend on `{finding.file_path}` within two hops, "
            "so a regression here propagates to each of them."
        ),
    )
