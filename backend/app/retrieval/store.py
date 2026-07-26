"""In-memory vector store scoped to a single analysis.

Per-analysis lifetime is deliberate: repository code is transient, so the index
is built in the worker, queried, and discarded with the workspace. Swapping in a
hosted vector database means implementing the same three methods.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.retrieval.chunking import Chunk
from app.retrieval.embeddings import Embedder, cosine_similarity, get_embedder


@dataclass(slots=True)
class ScoredChunk:
    chunk: Chunk
    score: float
    reasons: list[str] = field(default_factory=list)


class VectorStore:
    def __init__(self, embedder: Optional[Embedder] = None) -> None:
        self._embedder = embedder or get_embedder()
        self._chunks: list[Chunk] = []
        self._vectors: list[list[float]] = []

    def __len__(self) -> int:
        return len(self._chunks)

    def add(self, chunks: list[Chunk]) -> None:
        for chunk in chunks:
            self._chunks.append(chunk)
            self._vectors.append(self._embedder.embed(f"{chunk.header}\n{chunk.content}"))

    def search(
        self,
        query: str,
        *,
        top_k: int = 12,
        exclude_paths: Optional[set[str]] = None,
        min_score: float = 0.05,
    ) -> list[ScoredChunk]:
        if not self._chunks:
            return []
        query_vector = self._embedder.embed(query)
        exclude_paths = exclude_paths or set()

        scored: list[ScoredChunk] = []
        for chunk, vector in zip(self._chunks, self._vectors):
            if chunk.file_path in exclude_paths:
                continue
            score = cosine_similarity(query_vector, vector)
            if score < min_score:
                continue
            scored.append(ScoredChunk(chunk=chunk, score=score, reasons=["vector similarity"]))

        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:top_k]

    def chunks_for(self, file_path: str) -> list[Chunk]:
        return [chunk for chunk in self._chunks if chunk.file_path == file_path]

    def clear(self) -> None:
        self._chunks.clear()
        self._vectors.clear()
