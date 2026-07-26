"""Repository knowledge-graph API schemas (consumed by React Flow)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class GraphNode(BaseModel):
    id: str
    label: str
    type: str  # file | module | class | function | route | model | test | dependency
    file_path: str | None = None
    language: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    finding_count: int = 0
    max_severity: str | None = None
    changed: bool = False
    metrics: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    type: str  # imports | calls | extends | implements | tests | reads | writes | depends_on
    weight: float = 1.0


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    generated_at: str | None = None
    truncated: bool = False
    stats: dict[str, int] = Field(default_factory=dict)


class ImpactPath(BaseModel):
    """Dependency path from a finding to the symbols it can break."""

    finding_id: str
    nodes: list[str]
    edges: list[str]
    explanation: str = ""
