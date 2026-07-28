"""Structural embeddings, graph convolution, KNN and centrality.

What this is
------------
Every node in the knowledge graph gets a fixed-length feature vector, which is
then smoothed over the graph so a node's representation absorbs its neighbours'.
That smoothing step is exactly the propagation a GCN or GraphSAGE layer performs
at inference:

    H = D^-1/2 (A + I) D^-1/2 · H        repeated ``hops`` times

With the learned weight matrix omitted this is Simple Graph Convolution
(Wu et al., 2019, arXiv:1902.07153), which showed that for many graph tasks the
non-linearities contribute little and the propagation carries the signal. That
matters here: a *trained* GCN would need a labelled corpus of code graphs, which
does not exist for this problem, plus PyTorch, which does not fit the deployment
footprint. Untrained propagation needs neither and is deterministic — the same
repository always yields the same embedding, so results are reproducible and
explainable.

What it is not: there is no training, no learned weights, and no gradient. Any
claim that this is a trained neural network would be false.

Everything is pure Python. Graphs are capped at 1200 nodes upstream, so exact
KNN is a few million float operations — fast enough that an index would be
premature.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass, field

from app.core.logging import get_logger
from app.graph.builder import KnowledgeGraph, Node

logger = get_logger(__name__)

# Node roles get their own dimensions so structurally similar nodes of different
# kinds (a route vs the model it reads) stay distinguishable.
NODE_TYPES = (
    "file",
    "module",
    "class",
    "function",
    "route",
    "model",
    "test",
    "dependency",
    "constant",
)

# Relationship kinds counted separately per direction: importing something is a
# very different signal from being imported by it.
EDGE_TYPES = ("imports", "calls", "extends", "implements", "tests", "reads", "writes", "contains", "depends_on")

# Width of the hashed lexical block. The hashing trick avoids building and
# persisting a vocabulary, which would otherwise change between runs.
LEXICAL_DIMS = 32

_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9]*")


@dataclass(slots=True)
class GraphEmbedding:
    """Embeddings plus the derived rankings, keyed by node id."""

    vectors: dict[str, list[float]] = field(default_factory=dict)
    centrality: dict[str, float] = field(default_factory=dict)
    dimensions: int = 0
    hops: int = 0

    def similar(self, node_id: str, *, k: int = 5, min_score: float = 0.25) -> list[tuple[str, float]]:
        """K nearest neighbours by cosine similarity, excluding the node itself."""
        anchor = self.vectors.get(node_id)
        if not anchor:
            return []
        scored = [
            (other_id, _cosine(anchor, vector))
            for other_id, vector in self.vectors.items()
            if other_id != node_id
        ]
        scored = [pair for pair in scored if pair[1] >= min_score]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:k]

    def ranked_nodes(self, *, limit: int = 20) -> list[tuple[str, float]]:
        return sorted(self.centrality.items(), key=lambda pair: pair[1], reverse=True)[:limit]


# --------------------------------------------------------------------------- #
# Features
# --------------------------------------------------------------------------- #
def _tokenise(text: str) -> list[str]:
    """Split identifiers on camelCase, snake_case and path separators."""
    parts: list[str] = []
    for chunk in re.split(r"[/._\-\s]+", text):
        for match in _TOKEN.finditer(chunk):
            token = match.group(0)
            parts.extend(re.findall(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])", token) or [token])
    return [p.lower() for p in parts if p]


def _lexical_block(node: Node) -> list[float]:
    """Hashed bag of identifier tokens, L2-normalised.

    Names carry real signal — ``auth``, ``payment``, ``test`` — and hashing keeps
    it stable across runs without storing a vocabulary.
    """
    block = [0.0] * LEXICAL_DIMS
    tokens = _tokenise(f"{node.label} {node.file_path}")
    for token in tokens:
        # Python's hash() is salted per process; use a stable digest instead so
        # embeddings are reproducible between runs.
        bucket = _stable_hash(token) % LEXICAL_DIMS
        block[bucket] += 1.0
    norm = math.sqrt(sum(v * v for v in block))
    return [v / norm for v in block] if norm else block


def _stable_hash(text: str) -> int:
    """FNV-1a — small, fast, and identical across processes and platforms."""
    value = 0x811C9DC5
    for byte in text.encode("utf-8"):
        value ^= byte
        value = (value * 0x01000193) & 0xFFFFFFFF
    return value


def _base_features(graph: KnowledgeGraph, node: Node) -> list[float]:
    """Role, structure and lexical signal for one node, before propagation."""
    outgoing = graph._out.get(node.id, [])
    incoming = graph._in.get(node.id, [])

    role = [1.0 if node.type == t else 0.0 for t in NODE_TYPES]

    out_by_type: dict[str, int] = defaultdict(int)
    in_by_type: dict[str, int] = defaultdict(int)
    for edge in outgoing:
        out_by_type[edge.type] += 1
    for edge in incoming:
        in_by_type[edge.type] += 1

    # Degrees are log-compressed: one file importing 200 modules should not
    # dominate every other dimension.
    structure = [
        _log1p_scaled(len(outgoing)),
        _log1p_scaled(len(incoming)),
        _log1p_scaled(node.end_line - node.start_line),
        1.0 if node.changed else 0.0,
        1.0 if node.metrics.get("is_test") else 0.0,
        _log1p_scaled(float(node.metrics.get("finding_count", 0) or 0)),
    ]
    edges = [_log1p_scaled(out_by_type[t]) for t in EDGE_TYPES]
    edges += [_log1p_scaled(in_by_type[t]) for t in EDGE_TYPES]

    return role + structure + edges + _lexical_block(node)


def _log1p_scaled(value: float) -> float:
    """log1p keeps heavy-tailed counts comparable to the 0/1 flags."""
    return math.log1p(max(0.0, float(value))) / 5.0


# --------------------------------------------------------------------------- #
# Propagation, KNN and centrality
# --------------------------------------------------------------------------- #
def _neighbours(graph: KnowledgeGraph) -> dict[str, set[str]]:
    """Undirected adjacency. Direction is already encoded in the features, and
    smoothing works better when influence flows both ways."""
    adjacency: dict[str, set[str]] = {node_id: set() for node_id in graph.nodes}
    for edge in graph.edges.values():
        if edge.source in adjacency and edge.target in adjacency:
            adjacency[edge.source].add(edge.target)
            adjacency[edge.target].add(edge.source)
    return adjacency


def _propagate(
    vectors: dict[str, list[float]], adjacency: dict[str, set[str]], hops: int
) -> dict[str, list[float]]:
    """Symmetric-normalised neighbourhood averaging, ``hops`` times.

    This is the GCN/GraphSAGE aggregation step with identity weights. The +1 in
    each degree is the self-loop, so a node never loses its own signal.
    """
    degree = {node_id: len(neighbours) + 1 for node_id, neighbours in adjacency.items()}
    current = vectors

    for _ in range(hops):
        updated: dict[str, list[float]] = {}
        for node_id, vector in current.items():
            d_self = degree[node_id]
            # Self-loop term.
            accumulated = [v / d_self for v in vector]
            for neighbour in adjacency.get(node_id, ()):  # symmetric normalisation
                weight = 1.0 / math.sqrt(d_self * degree[neighbour])
                neighbour_vector = current[neighbour]
                for i, value in enumerate(neighbour_vector):
                    accumulated[i] += value * weight
            updated[node_id] = accumulated
        current = updated

    return {node_id: _l2(vector) for node_id, vector in current.items()}


def _pagerank(
    adjacency: dict[str, set[str]], *, damping: float = 0.85, iterations: int = 30
) -> dict[str, float]:
    """Which nodes the graph actually revolves around.

    Ranks importance structurally rather than by counting direct references, so
    a module reached through many indirect paths scores highly even with few
    direct importers.
    """
    if not adjacency:
        return {}
    count = len(adjacency)
    rank = {node_id: 1.0 / count for node_id in adjacency}
    base = (1.0 - damping) / count

    for _ in range(iterations):
        updated = {node_id: base for node_id in adjacency}
        dangling = 0.0
        for node_id, neighbours in adjacency.items():
            if not neighbours:
                dangling += rank[node_id]
                continue
            share = damping * rank[node_id] / len(neighbours)
            for neighbour in neighbours:
                updated[neighbour] += share
        if dangling:
            spread = damping * dangling / count
            for node_id in updated:
                updated[node_id] += spread
        rank = updated

    peak = max(rank.values()) or 1.0
    return {node_id: value / peak for node_id, value in rank.items()}


def _cosine(a: list[float], b: list[float]) -> float:
    # Inputs are already L2-normalised, so the dot product is the cosine.
    return sum(x * y for x, y in zip(a, b, strict=False))


def _l2(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vector))
    return [v / norm for v in vector] if norm else vector


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def embed_graph(graph: KnowledgeGraph, *, hops: int = 2) -> GraphEmbedding:
    """Embed every node, then derive centrality.

    ``hops`` is the receptive field: 2 means a node sees its neighbours and
    their neighbours, which for import graphs covers the practical blast radius
    without over-smoothing everything into one indistinguishable blur.
    """
    if not graph.nodes:
        return GraphEmbedding()

    base = {node_id: _base_features(graph, node) for node_id, node in graph.nodes.items()}
    adjacency = _neighbours(graph)
    vectors = _propagate({k: _l2(v) for k, v in base.items()}, adjacency, hops)
    centrality = _pagerank(adjacency)

    dimensions = len(next(iter(vectors.values()))) if vectors else 0
    logger.info(
        "graph.embedded", nodes=len(vectors), dimensions=dimensions, hops=hops
    )
    return GraphEmbedding(
        vectors=vectors, centrality=centrality, dimensions=dimensions, hops=hops
    )
