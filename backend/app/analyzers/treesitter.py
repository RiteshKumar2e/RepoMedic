"""Tree-sitter grammar loading with graceful degradation.

Tree-sitter wheels are not available on every platform/Python combination. When
a grammar cannot be loaded the JS/TS analyzer falls back to a lexical parser and
marks its results ``degraded=True``, which lowers the confidence of any finding
derived from them. Nothing silently pretends to be an AST.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Optional

from app.core.logging import get_logger

logger = get_logger(__name__)

_GRAMMAR_LOADERS = {
    "python": ("tree_sitter_python", "language"),
    "javascript": ("tree_sitter_javascript", "language"),
    "typescript": ("tree_sitter_typescript", "language_typescript"),
    "tsx": ("tree_sitter_typescript", "language_tsx"),
}


@lru_cache(maxsize=8)
def get_parser(language: str) -> Optional[Any]:
    """Return a configured ``tree_sitter.Parser``, or ``None`` if unavailable."""
    entry = _GRAMMAR_LOADERS.get(language)
    if entry is None:
        return None
    module_name, factory_name = entry

    try:
        from tree_sitter import Language as TSLanguage, Parser as TSParser
    except ImportError:
        logger.info("treesitter.unavailable", reason="tree_sitter package not installed")
        return None

    try:
        module = __import__(module_name)
        factory = getattr(module, factory_name)
        ts_language = TSLanguage(factory())
    except Exception as exc:
        logger.info("treesitter.grammar_unavailable", language=language, error=str(exc))
        return None

    try:
        return TSParser(ts_language)
    except TypeError:
        # tree-sitter < 0.22 used the setter API.
        parser = TSParser()
        parser.set_language(ts_language)
        return parser


def treesitter_available(language: str) -> bool:
    return get_parser(language) is not None


def node_text(node: Any, source: bytes) -> str:
    try:
        return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
    except (AttributeError, TypeError):
        return ""


def walk(node: Any):
    """Depth-first traversal over a tree-sitter node."""
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(reversed(current.children))


def find_children(node: Any, *types: str) -> list[Any]:
    return [child for child in node.children if child.type in types]


def first_child(node: Any, *types: str) -> Optional[Any]:
    for child in node.children:
        if child.type in types:
            return child
    return None
