"""Scanner contract and severity mapping helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from app.domain.types import UnifiedFinding
from app.models.enums import FindingCategory, FindingSource, Severity


@dataclass(slots=True)
class ScanRequest:
    """Everything a scanner needs; scanners never touch the database."""

    workspace_root: Path
    target_files: list[str]  # repository-relative paths changed by the PR
    all_files: list[str] = field(default_factory=list)
    languages: dict[str, int] = field(default_factory=dict)
    excluded_paths: list[str] = field(default_factory=list)
    timeout: int = 120

    def files_for(self, *suffixes: str) -> list[str]:
        return [p for p in self.target_files if p.endswith(suffixes)]


@dataclass(slots=True)
class ScanResult:
    scanner: str
    findings: list[UnifiedFinding] = field(default_factory=list)
    ran: bool = True
    skipped_reason: str = ""
    duration: float = 0.0
    raw_error: str = ""


@runtime_checkable
class Scanner(Protocol):
    """Deterministic tool adapter."""

    name: str
    source: FindingSource
    families: set[str]  # "python" | "javascript" | "any"

    def available(self) -> bool: ...

    def scan(self, request: ScanRequest) -> ScanResult: ...


# --------------------------------------------------------------------------- #
# Shared normalization helpers
# --------------------------------------------------------------------------- #
_SEVERITY_WORDS = {
    "critical": Severity.CRITICAL,
    "blocker": Severity.CRITICAL,
    "error": Severity.HIGH,
    "high": Severity.HIGH,
    "warning": Severity.MEDIUM,
    "medium": Severity.MEDIUM,
    "moderate": Severity.MEDIUM,
    "low": Severity.LOW,
    "minor": Severity.LOW,
    "note": Severity.INFORMATIONAL,
    "info": Severity.INFORMATIONAL,
    "informational": Severity.INFORMATIONAL,
    "style": Severity.INFORMATIONAL,
}


def map_severity(word: str, default: Severity = Severity.MEDIUM) -> Severity:
    return _SEVERITY_WORDS.get((word or "").strip().lower(), default)


# Rule-prefix → category, applied when a tool does not classify its own output.
_CATEGORY_PREFIXES: list[tuple[tuple[str, ...], FindingCategory]] = [
    (("S", "B", "sec", "security", "CWE"), FindingCategory.SECURITY),
    (("PERF", "C4", "SIM1", "n-plus"), FindingCategory.PERFORMANCE),
    (("ASYNC", "ARG", "TRY", "BLE", "RET"), FindingCategory.RELIABILITY),
    (("PT", "test", "PLR09"), FindingCategory.TESTING),
    (("E", "W", "F", "N", "D", "I", "UP", "C90"), FindingCategory.CODE_QUALITY),
]


def map_category(rule_id: str, default: FindingCategory = FindingCategory.CODE_QUALITY) -> FindingCategory:
    rule = (rule_id or "").strip()
    for prefixes, category in _CATEGORY_PREFIXES:
        if rule.startswith(prefixes):
            return category
    return default


def clamp_line(value: object, fallback: int = 1) -> int:
    try:
        line = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return fallback
    return max(1, line)


def snippet_for(workspace_root: Path, relative_path: str, start: int, end: int, padding: int = 2) -> str:
    """Read a small code excerpt for display; failures degrade to an empty string."""
    try:
        path = (workspace_root / relative_path).resolve()
        path.relative_to(workspace_root.resolve())
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except (OSError, ValueError):
        return ""
    lo = max(0, start - 1 - padding)
    hi = min(len(lines), end + padding)
    return "\n".join(lines[lo:hi])
