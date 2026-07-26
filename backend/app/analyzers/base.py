"""The language-adapter contract.

Every supported language implements :class:`LanguageAnalyzer`. Adding Java, Go,
Rust or C++ later means writing one module that satisfies this protocol and
registering it — nothing else in the pipeline changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from app.domain.types import (
    CallRef,
    ImportRef,
    Language,
    PatchProposal,
    SourceFile,
    Symbol,
    UnifiedFinding,
)


@dataclass(slots=True)
class ParseResult:
    """Outcome of parsing one file."""

    path: str
    language: Language
    tree: Any = None
    ok: bool = True
    error: str = ""
    degraded: bool = False  # True when a fallback parser was used
    source: str = ""


@dataclass(slots=True)
class AnalyzerContext:
    """Repository-level context handed to rule checks."""

    file: SourceFile
    parse: ParseResult
    symbols: list[Symbol] = field(default_factory=list)
    imports: list[ImportRef] = field(default_factory=list)
    calls: list[CallRef] = field(default_factory=list)
    changed_lines: set[int] = field(default_factory=set)
    dependencies: dict[str, str] = field(default_factory=dict)
    frameworks: list[str] = field(default_factory=list)
    all_paths: list[str] = field(default_factory=list)

    def touches_changed_lines(self, start: int, end: int) -> bool:
        """Only report issues the pull request actually introduced or touched."""
        if not self.changed_lines:
            return True
        return any(start <= line <= end for line in self.changed_lines)


@runtime_checkable
class LanguageAnalyzer(Protocol):
    """Per-language AST adapter."""

    language: Language
    extensions: tuple[str, ...]

    def parse(self, source_code: str, path: str = "") -> ParseResult: ...

    def extract_symbols(self, tree: ParseResult) -> list[Symbol]: ...

    def extract_imports(self, tree: ParseResult) -> list[ImportRef]: ...

    def extract_calls(self, tree: ParseResult, symbols: list[Symbol]) -> list[CallRef]: ...

    def detect_issues(self, context: AnalyzerContext) -> list[UnifiedFinding]: ...

    def apply_patch(self, source_code: str, patch: PatchProposal) -> str | None: ...

    def validate_syntax(self, source_code: str) -> tuple[bool, str]: ...


def enclosing_symbol(symbols: list[Symbol], line: int) -> Symbol | None:
    """Innermost symbol containing ``line`` — used to attribute findings."""
    candidates = [s for s in symbols if s.start_line <= line <= s.end_line]
    if not candidates:
        return None
    return min(candidates, key=lambda s: s.end_line - s.start_line)
