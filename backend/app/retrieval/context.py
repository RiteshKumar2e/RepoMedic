"""Context assembly for the AI reviewers.

The whole repository is never sent to a model. This module picks the minimum
set of chunks that make a change reviewable:

1. **The diff itself** — always included.
2. **Graph-adjacent files** — importers of and imports from each changed file,
   because that is where breaking changes surface.
3. **Vector-retrieved chunks** — semantically similar code elsewhere in the
   repository (existing validation helpers, similar routes, prior patterns).
4. **Tests** covering the changed files.

Everything is then secret-redacted, injection-scanned and wrapped in data
delimiters, and a manifest records exactly what left the process.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.core.config import settings
from app.core.logging import get_logger
from app.domain.types import AnalysisContext, FileChange
from app.graph.builder import KnowledgeGraph
from app.retrieval.chunking import Chunk, chunk_file, estimate_tokens
from app.retrieval.store import ScoredChunk, VectorStore
from app.security.firewall import DATA_CLOSE, DATA_OPEN, scan_for_injection
from app.security.secrets import redact_secrets

logger = get_logger(__name__)

GRAPH_BONUS = 0.35
TEST_BONUS = 0.2


@dataclass(slots=True)
class ContextBundle:
    """Prompt-ready, sanitised repository context plus a transmission manifest."""

    diff_sections: list[str] = field(default_factory=list)
    related_chunks: list[ScoredChunk] = field(default_factory=list)
    manifest: dict = field(default_factory=dict)
    injection_flags: list[dict] = field(default_factory=list)
    total_tokens: int = 0

    def render(self, *, max_tokens: Optional[int] = None) -> str:
        """Render the context block that goes into the prompt."""
        budget = max_tokens or settings.max_context_tokens
        parts: list[str] = [
            "## Changed code under review",
            "",
            *self.diff_sections,
        ]
        used = estimate_tokens("\n".join(parts))

        if self.related_chunks:
            parts.append("")
            parts.append("## Related repository context (read-only, for reasoning about impact)")
            parts.append("")
            for scored in self.related_chunks:
                block = (
                    f"### {scored.chunk.header} "
                    f"(relevance {scored.score:.2f}: {', '.join(scored.reasons)})\n"
                    f"{DATA_OPEN}\n{scored.chunk.content}\n{DATA_CLOSE}\n"
                )
                block_tokens = estimate_tokens(block)
                if used + block_tokens > budget:
                    break
                parts.append(block)
                used += block_tokens

        return "\n".join(parts)


def build_context(
    context: AnalysisContext,
    graph: Optional[KnowledgeGraph] = None,
    *,
    max_files: Optional[int] = None,
    max_tokens: Optional[int] = None,
) -> ContextBundle:
    max_files = max_files or settings.max_context_files
    max_tokens = max_tokens or settings.max_context_tokens

    bundle = ContextBundle()
    changed_paths = set(context.changed_paths)
    redaction_count = 0

    # ---- 1. the diff -----------------------------------------------------
    for change in context.changes:
        if change.is_deleted or not change.patch:
            continue
        clean_patch, redacted = redact_secrets(change.patch)
        redaction_count += redacted
        report = scan_for_injection(change.patch, source_label=change.path)
        if report.is_suspicious:
            bundle.injection_flags.extend(
                {"file": change.path, "rule": m.rule_id, "line": m.line, "confidence": m.confidence}
                for m in report.matches
            )
        bundle.diff_sections.append(
            f"### {change.path} ({change.status}, +{change.additions}/-{change.deletions})\n"
            f"{DATA_OPEN}\n```diff\n{clean_patch}\n```\n{DATA_CLOSE}\n"
        )

    # ---- 2. index the repository ----------------------------------------
    store = VectorStore()
    all_chunks: list[Chunk] = []
    for path, source_file in context.files.items():
        if not source_file.language.is_analyzable:
            continue
        chunks = chunk_file(source_file, context.symbols, context.imports)
        all_chunks.extend(chunks)
    store.add([c for c in all_chunks if c.file_path not in changed_paths])

    # ---- 3. graph-adjacent files ----------------------------------------
    graph_relevant: dict[str, list[str]] = {}
    if graph is not None:
        for path in changed_paths:
            for dependent in graph.dependents_of(path, max_depth=2)[:6]:
                graph_relevant.setdefault(dependent, []).append(f"imports {path}")
            for dependency in graph.dependencies_of(path, max_depth=1)[:6]:
                graph_relevant.setdefault(dependency, []).append(f"imported by {path}")
            for test_path in graph.tests_covering(path)[:4]:
                graph_relevant.setdefault(test_path, []).append(f"tests {path}")
    context.related_files = {path: reasons for path, reasons in graph_relevant.items()}

    # ---- 4. rank ---------------------------------------------------------
    query = _build_query(context)
    scored: dict[str, ScoredChunk] = {}

    for item in store.search(query, top_k=max_files * 3, exclude_paths=changed_paths):
        scored[item.chunk.id] = item

    for path, reasons in graph_relevant.items():
        for chunk in store.chunks_for(path):
            existing = scored.get(chunk.id)
            bonus = GRAPH_BONUS + (TEST_BONUS if any("tests" in r for r in reasons) else 0.0)
            if existing:
                existing.score += bonus
                existing.reasons.extend(reasons)
            else:
                scored[chunk.id] = ScoredChunk(chunk=chunk, score=bonus, reasons=list(reasons))

    ranked = sorted(scored.values(), key=lambda item: item.score, reverse=True)

    # ---- 5. budget and sanitise -----------------------------------------
    selected: list[ScoredChunk] = []
    files_used: set[str] = set()
    tokens_used = estimate_tokens("\n".join(bundle.diff_sections))

    for item in ranked:
        if len(files_used | {item.chunk.file_path}) > max_files:
            continue
        if tokens_used + item.chunk.tokens > max_tokens:
            continue
        clean, redacted = redact_secrets(item.chunk.content)
        redaction_count += redacted
        report = scan_for_injection(item.chunk.content, source_label=item.chunk.file_path)
        if report.is_suspicious:
            bundle.injection_flags.extend(
                {"file": item.chunk.file_path, "rule": m.rule_id, "line": m.line, "confidence": m.confidence}
                for m in report.matches
            )
            clean = report.sanitized
            clean, extra = redact_secrets(clean)
            redaction_count += extra
        item.chunk.content = clean
        selected.append(item)
        files_used.add(item.chunk.file_path)
        tokens_used += item.chunk.tokens

    bundle.related_chunks = selected
    bundle.total_tokens = tokens_used
    bundle.manifest = {
        "changed_files": sorted(changed_paths),
        "context_files": sorted(files_used),
        "chunks": len(selected),
        "symbols": sorted(
            {item.chunk.symbol_name for item in selected if item.chunk.symbol_name}
        )[:120],
        "estimated_tokens": tokens_used,
        "secrets_redacted": redaction_count,
        "injection_flags": len(bundle.injection_flags),
        "repository_files_indexed": len(store),
        "graph_related_files": {k: v for k, v in list(graph_relevant.items())[:40]},
    }
    logger.info(
        "retrieval.context_built",
        changed=len(changed_paths),
        context_files=len(files_used),
        tokens=tokens_used,
        redactions=redaction_count,
        injection_flags=len(bundle.injection_flags),
    )
    return bundle


def _build_query(context: AnalysisContext) -> str:
    """Query text is the change itself: title, paths, symbols and added lines."""
    parts: list[str] = [context.pr_title]
    for change in context.changes[:20]:
        parts.append(change.path)
        parts.extend(
            line[1:].strip()
            for line in change.patch.splitlines()[:80]
            if line.startswith("+") and not line.startswith("+++")
        )
    changed = set(context.changed_paths)
    parts.extend(
        f"{symbol.name} {symbol.signature}"
        for symbol in context.symbols
        if symbol.file_path in changed
    )
    return "\n".join(p for p in parts if p)[:20_000]


def diff_only_context(changes: list[FileChange]) -> ContextBundle:
    """Minimal bundle used when repository indexing is unavailable."""
    bundle = ContextBundle()
    redactions = 0
    for change in changes:
        if not change.patch:
            continue
        clean, count = redact_secrets(change.patch)
        redactions += count
        bundle.diff_sections.append(
            f"### {change.path} ({change.status})\n{DATA_OPEN}\n```diff\n{clean}\n```\n{DATA_CLOSE}\n"
        )
    bundle.manifest = {
        "changed_files": [c.path for c in changes],
        "context_files": [],
        "chunks": 0,
        "secrets_redacted": redactions,
        "degraded": True,
    }
    return bundle
