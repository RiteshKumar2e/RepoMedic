"""Graph embeddings: propagation, KNN similarity and centrality.

These are numeric properties rather than API behaviour, so each test states the
property it pins rather than asserting on exact float values.
"""

from __future__ import annotations

import math

from app.graph.builder import Edge, KnowledgeGraph, Node
from app.graph.embeddings import GraphEmbedding, embed_graph


def _graph() -> KnowledgeGraph:
    """Two clusters joined by a single edge.

    auth_a/auth_b/auth_c import each other; billing_a/billing_b do the same.
    One bridge edge connects the clusters, so a correct embedding should still
    separate them.
    """
    graph = KnowledgeGraph()
    for name in ("auth_a", "auth_b", "auth_c", "billing_a", "billing_b", "lonely"):
        graph.add_node(
            Node(
                id=f"file:{name}.py",
                label=f"{name}.py",
                type="file",
                file_path=f"{name}.py",
                language="python",
            )
        )

    def link(source: str, target: str, kind: str = "imports") -> None:
        graph.add_edge(
            Edge(
                id=f"{source}->{target}:{kind}",
                source=f"file:{source}.py",
                target=f"file:{target}.py",
                type=kind,
            )
        )

    link("auth_a", "auth_b")
    link("auth_b", "auth_c")
    link("auth_c", "auth_a")
    link("billing_a", "billing_b")
    link("billing_b", "billing_a")
    link("auth_a", "billing_a")  # the single bridge
    return graph


# --------------------------------------------------------------------------- #
# Shape and determinism
# --------------------------------------------------------------------------- #
def test_every_node_is_embedded_with_a_uniform_dimension():
    embedding = embed_graph(_graph())

    assert len(embedding.vectors) == 6
    widths = {len(v) for v in embedding.vectors.values()}
    assert len(widths) == 1, "all vectors must share one dimensionality"
    assert embedding.dimensions == widths.pop()


def test_vectors_are_l2_normalised():
    """Cosine similarity assumes unit vectors, so this is load-bearing."""
    embedding = embed_graph(_graph())

    for node_id, vector in embedding.vectors.items():
        norm = math.sqrt(sum(v * v for v in vector))
        assert norm == 0 or abs(norm - 1.0) < 1e-9, f"{node_id} has norm {norm}"


def test_embedding_is_deterministic():
    """Reproducibility is why hashing is stable rather than salted."""
    first = embed_graph(_graph())
    second = embed_graph(_graph())

    assert first.vectors == second.vectors
    assert first.centrality == second.centrality


def test_empty_graph_is_handled():
    embedding = embed_graph(KnowledgeGraph())

    assert embedding.vectors == {}
    assert embedding.centrality == {}
    assert embedding.similar("file:missing.py") == []


# --------------------------------------------------------------------------- #
# Propagation
# --------------------------------------------------------------------------- #
def test_propagation_pulls_connected_nodes_together():
    """The point of graph convolution: neighbours end up more alike.

    Compared at 0 hops (features only) versus 2 hops (features + structure).
    """
    graph = _graph()
    flat = embed_graph(graph, hops=0)
    smoothed = embed_graph(graph, hops=2)

    def similarity(embedding: GraphEmbedding, a: str, b: str) -> float:
        va, vb = embedding.vectors[a], embedding.vectors[b]
        return sum(x * y for x, y in zip(va, vb, strict=False))

    before = similarity(flat, "file:auth_a.py", "file:auth_b.py")
    after = similarity(smoothed, "file:auth_a.py", "file:auth_b.py")

    assert after > before, "connected nodes should converge under propagation"


def test_isolated_node_keeps_its_own_signal():
    """The self-loop guarantees a node with no edges is still representable."""
    embedding = embed_graph(_graph(), hops=2)

    vector = embedding.vectors["file:lonely.py"]
    assert any(abs(v) > 1e-9 for v in vector), "isolated node collapsed to zero"


def test_more_hops_never_changes_the_node_set():
    for hops in (0, 1, 3):
        embedding = embed_graph(_graph(), hops=hops)
        assert set(embedding.vectors) == {
            "file:auth_a.py",
            "file:auth_b.py",
            "file:auth_c.py",
            "file:billing_a.py",
            "file:billing_b.py",
            "file:lonely.py",
        }
        assert embedding.hops == hops


# --------------------------------------------------------------------------- #
# KNN
# --------------------------------------------------------------------------- #
def test_knn_prefers_the_same_cluster():
    embedding = embed_graph(_graph(), hops=2)

    neighbours = embedding.similar("file:auth_b.py", k=2, min_score=0.0)
    found = {node_id for node_id, _ in neighbours}

    assert found & {"file:auth_a.py", "file:auth_c.py"}, (
        f"expected an auth sibling, got {found}"
    )


def test_knn_never_returns_the_query_node():
    embedding = embed_graph(_graph(), hops=2)

    neighbours = embedding.similar("file:auth_a.py", k=10, min_score=0.0)

    assert "file:auth_a.py" not in {node_id for node_id, _ in neighbours}


def test_knn_respects_k_and_is_ordered_by_score():
    embedding = embed_graph(_graph(), hops=2)

    neighbours = embedding.similar("file:auth_a.py", k=3, min_score=0.0)

    assert len(neighbours) <= 3
    scores = [score for _, score in neighbours]
    assert scores == sorted(scores, reverse=True), "results must be ranked"


def test_knn_min_score_filters_weak_matches():
    embedding = embed_graph(_graph(), hops=2)

    assert embedding.similar("file:auth_a.py", k=10, min_score=1.01) == []


def test_knn_on_an_unknown_node_is_empty_not_an_error():
    embedding = embed_graph(_graph())

    assert embedding.similar("file:nope.py") == []


# --------------------------------------------------------------------------- #
# Centrality
# --------------------------------------------------------------------------- #
def test_centrality_ranks_a_connected_node_above_an_isolated_one():
    embedding = embed_graph(_graph())

    assert embedding.centrality["file:auth_a.py"] > embedding.centrality["file:lonely.py"]


def test_centrality_is_normalised_to_a_zero_one_range():
    embedding = embed_graph(_graph())

    values = list(embedding.centrality.values())
    assert all(0.0 <= v <= 1.0 for v in values)
    assert max(values) == 1.0, "the top node anchors the scale"


def test_ranked_nodes_is_ordered_and_limited():
    embedding = embed_graph(_graph())

    ranked = embedding.ranked_nodes(limit=3)

    assert len(ranked) == 3
    scores = [score for _, score in ranked]
    assert scores == sorted(scores, reverse=True)
