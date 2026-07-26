"""Embeddings with a dependency-free local default.

The default :class:`HashingEmbedder` is deterministic, offline, and needs no
model download — it uses the hashing trick over code-aware tokens (identifiers,
dotted paths, operators) with sub-token shingles. That is enough for
*retrieval ranking within a single repository*, which is the job here.

Swap in a hosted or local neural embedder by implementing :class:`Embedder`.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol, Sequence

DIMENSIONS = 512

_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|[0-9]+|[^\sA-Za-z0-9_]")
_CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


class Embedder(Protocol):
    dimensions: int

    def embed(self, text: str) -> list[float]: ...

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]: ...


def tokenize_code(text: str) -> list[str]:
    """Code-aware tokenisation: splits identifiers on camelCase and snake_case."""
    tokens: list[str] = []
    for raw in _TOKEN_RE.findall(text[:40_000]):
        lowered = raw.lower()
        tokens.append(lowered)
        if len(raw) > 3 and raw.isidentifier():
            for part in _CAMEL_RE.sub(" ", raw).replace("_", " ").split():
                if len(part) > 2:
                    tokens.append(part.lower())
    return tokens


class HashingEmbedder:
    """Signed hashing-trick embedder with sub-linear term weighting."""

    dimensions = DIMENSIONS

    def __init__(self, dimensions: int = DIMENSIONS) -> None:
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = tokenize_code(text)
        if not tokens:
            return vector

        counts: dict[str, int] = {}
        for token in tokens:
            counts[token] = counts.get(token, 0) + 1
        # Bigrams capture call shapes such as `cursor execute`.
        for first, second in zip(tokens, tokens[1:]):
            bigram = f"{first}~{second}"
            counts[bigram] = counts.get(bigram, 0) + 1

        for token, count in counts.items():
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "little") % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign * (1.0 + math.log(count))

        norm = math.sqrt(sum(value * value for value in vector))
        if norm > 0:
            vector = [value / norm for value in vector]
        return vector

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    # Vectors from HashingEmbedder are already unit length.
    return max(-1.0, min(1.0, dot))


def jaccard_similarity(a: str, b: str) -> float:
    """Token-set overlap — used as a semantic-drift check when validating patches."""
    tokens_a, tokens_b = set(tokenize_code(a)), set(tokenize_code(b))
    if not tokens_a and not tokens_b:
        return 1.0
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


_default_embedder: Embedder = HashingEmbedder()


def get_embedder() -> Embedder:
    return _default_embedder
