"""Core value objects for the analysis pipeline.

Deliberately dependency-free (no SQLModel, no FastAPI) so analyzers, scanners
and agents can be unit-tested without a database or an HTTP stack.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from app.models.enums import FindingCategory, FindingSource, RiskLevel, Severity


class Language(str, Enum):
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    TSX = "tsx"
    JSON = "json"
    YAML = "yaml"
    MARKDOWN = "markdown"
    UNKNOWN = "unknown"

    @classmethod
    def from_path(cls, path: str) -> "Language":
        suffix = path.rsplit(".", 1)[-1].lower() if "." in path else ""
        return {
            "py": cls.PYTHON,
            "pyi": cls.PYTHON,
            "js": cls.JAVASCRIPT,
            "jsx": cls.JAVASCRIPT,
            "mjs": cls.JAVASCRIPT,
            "cjs": cls.JAVASCRIPT,
            "ts": cls.TYPESCRIPT,
            "mts": cls.TYPESCRIPT,
            "cts": cls.TYPESCRIPT,
            "tsx": cls.TSX,
            "json": cls.JSON,
            "yml": cls.YAML,
            "yaml": cls.YAML,
            "md": cls.MARKDOWN,
        }.get(suffix, cls.UNKNOWN)

    @property
    def is_analyzable(self) -> bool:
        return self in (Language.PYTHON, Language.JAVASCRIPT, Language.TYPESCRIPT, Language.TSX)

    @property
    def family(self) -> str:
        if self is Language.PYTHON:
            return "python"
        if self in (Language.JAVASCRIPT, Language.TYPESCRIPT, Language.TSX):
            return "javascript"
        return "other"


class SymbolKind(str, Enum):
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    ROUTE = "route"
    MODEL = "model"
    TEST = "test"
    CONSTANT = "constant"
    COMPONENT = "component"


@dataclass(slots=True)
class Symbol:
    name: str
    kind: SymbolKind
    file_path: str
    start_line: int
    end_line: int
    signature: str = ""
    docstring: str = ""
    parent: Optional[str] = None
    decorators: list[str] = field(default_factory=list)
    is_async: bool = False
    complexity: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def qualified_name(self) -> str:
        return f"{self.file_path}::{self.parent + '.' if self.parent else ''}{self.name}"


@dataclass(slots=True)
class ImportRef:
    module: str
    names: list[str] = field(default_factory=list)
    file_path: str = ""
    line: int = 1
    is_relative: bool = False
    resolved_path: Optional[str] = None


@dataclass(slots=True)
class CallRef:
    caller: str
    callee: str
    file_path: str
    line: int
    is_awaited: bool = False


@dataclass(slots=True)
class SourceFile:
    path: str
    content: str
    language: Language
    size_bytes: int = 0
    is_test: bool = False
    is_binary: bool = False

    @property
    def lines(self) -> list[str]:
        return self.content.splitlines()

    def excerpt(self, start_line: int, end_line: int, padding: int = 2) -> str:
        lines = self.lines
        lo = max(0, start_line - 1 - padding)
        hi = min(len(lines), end_line + padding)
        return "\n".join(lines[lo:hi])


@dataclass(slots=True)
class FileChange:
    """A file touched by the pull request."""

    path: str
    status: str  # added | modified | removed | renamed
    additions: int = 0
    deletions: int = 0
    patch: str = ""
    previous_path: Optional[str] = None
    changed_lines: set[int] = field(default_factory=set)

    @property
    def language(self) -> Language:
        return Language.from_path(self.path)

    @property
    def is_deleted(self) -> bool:
        return self.status == "removed"


_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def changed_lines_from_patch(patch: str) -> set[int]:
    """Extract the new-file line numbers added or modified by a unified diff."""
    lines: set[int] = set()
    current = 0
    for raw in patch.splitlines():
        match = _HUNK_RE.match(raw)
        if match:
            current = int(match.group(1))
            continue
        if raw.startswith("+") and not raw.startswith("+++"):
            lines.add(current)
            current += 1
        elif raw.startswith("-") and not raw.startswith("---"):
            continue
        elif raw.startswith(" ") or raw == "":
            current += 1
    return lines


def fingerprint_finding(
    *, file_path: str, rule_id: str, title: str, start_line: int, category: str
) -> str:
    """Stable identity for a finding.

    Line numbers are bucketed so a one-line drift from an unrelated edit does not
    create a "new" finding, while genuinely different locations stay distinct.
    """
    bucket = start_line // 10
    normalized_title = re.sub(r"\W+", "-", title.lower()).strip("-")[:60]
    raw = f"{file_path}|{category}|{rule_id or normalized_title}|{bucket}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


@dataclass(slots=True)
class UnifiedFinding:
    """The single normalized issue shape every producer emits."""

    title: str
    description: str
    category: FindingCategory
    severity: Severity
    file_path: str
    start_line: int
    end_line: int
    source: FindingSource
    rule_id: str = ""
    cwe: Optional[str] = None
    risk: str = ""
    recommendation: str = ""
    code_snippet: str = ""
    confidence: float = 0.0
    score: float = 0.0
    related_files: list[str] = field(default_factory=list)
    corroborating_sources: list[str] = field(default_factory=list)
    score_breakdown: dict[str, float] = field(default_factory=dict)
    suggested_patch: Optional["PatchProposal"] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def fingerprint(self) -> str:
        return fingerprint_finding(
            file_path=self.file_path,
            rule_id=self.rule_id,
            title=self.title,
            start_line=self.start_line,
            category=self.category.value,
        )


@dataclass(slots=True)
class PatchProposal:
    """A candidate code change, before validation."""

    file_path: str
    original_code: str
    suggested_code: str
    unified_diff: str = ""
    explanation: str = ""
    expected_impact: str = ""
    side_effects: list[str] = field(default_factory=list)
    start_line: int = 1
    end_line: int = 1
    risk_level: RiskLevel = RiskLevel.MEDIUM
    generated_by: str = "fix_generator"
    confidence: float = 0.0
    confidence_breakdown: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class AnalysisContext:
    """Everything the pipeline knows about one pull request under review."""

    analysis_id: str
    repository_full_name: str
    workspace_path: str
    base_sha: str
    head_sha: str
    pr_title: str = ""
    pr_body: str = ""
    changes: list[FileChange] = field(default_factory=list)
    files: dict[str, SourceFile] = field(default_factory=dict)
    symbols: list[Symbol] = field(default_factory=list)
    imports: list[ImportRef] = field(default_factory=list)
    calls: list[CallRef] = field(default_factory=list)
    languages: dict[str, int] = field(default_factory=dict)
    frameworks: list[str] = field(default_factory=list)
    dependencies: dict[str, str] = field(default_factory=dict)
    related_files: dict[str, list[str]] = field(default_factory=dict)
    excluded_paths: list[str] = field(default_factory=list)
    settings: dict[str, Any] = field(default_factory=dict)

    @property
    def changed_paths(self) -> list[str]:
        return [c.path for c in self.changes if not c.is_deleted]

    def file(self, path: str) -> Optional[SourceFile]:
        return self.files.get(path)

    def changed_source_files(self) -> list[SourceFile]:
        return [f for p in self.changed_paths if (f := self.files.get(p)) and f.language.is_analyzable]
