"""Python tool adapters: Ruff, Bandit, Mypy and Radon."""

from __future__ import annotations

import json
import time

from app.core.logging import get_logger
from app.domain.types import UnifiedFinding
from app.models.enums import FindingCategory, FindingSource, Severity
from app.scanners.base import (
    ScanRequest,
    ScanResult,
    clamp_line,
    map_category,
    map_severity,
    snippet_for,
)
from app.scanners.runner import run_tool, tool_available

logger = get_logger(__name__)


class RuffScanner:
    """Fast Python linter — style, bugs, security (flake8-bandit `S` rules)."""

    name = "ruff"
    source = FindingSource.RUFF
    families = {"python"}

    def available(self) -> bool:
        return tool_available("ruff")

    def scan(self, request: ScanRequest) -> ScanResult:
        targets = request.files_for(".py")
        if not targets:
            return ScanResult(self.name, ran=False, skipped_reason="no Python files changed")
        if not self.available():
            return ScanResult(self.name, ran=False, skipped_reason="ruff is not installed")

        started = time.perf_counter()
        result = run_tool(
            [
                "ruff", "check", "--output-format", "json", "--no-cache",
                "--select", "E,F,W,B,S,C4,SIM,ASYNC,PERF,RET,TRY,ARG,N,UP",
                *targets,
            ],
            cwd=request.workspace_root,
            timeout=request.timeout,
        )
        if not result.available:
            return ScanResult(self.name, ran=False, skipped_reason=result.skipped_reason)

        findings: list[UnifiedFinding] = []
        try:
            payload = json.loads(result.stdout or "[]")
        except json.JSONDecodeError:
            return ScanResult(
                self.name, ran=False, skipped_reason="ruff produced unparsable output",
                raw_error=result.stderr[:400],
            )

        for item in payload:
            rule = item.get("code") or "RUFF"
            start = clamp_line(item.get("location", {}).get("row"))
            end = clamp_line(item.get("end_location", {}).get("row"), start)
            category = FindingCategory.SECURITY if rule.startswith("S") else map_category(rule)
            severity = _ruff_severity(rule)
            path = _relative(item.get("filename", ""), request)
            findings.append(
                UnifiedFinding(
                    title=f"{rule}: {item.get('message', 'Lint violation')}",
                    description=item.get("message", ""),
                    category=category,
                    severity=severity,
                    file_path=path,
                    start_line=start,
                    end_line=max(start, end),
                    source=self.source,
                    rule_id=rule,
                    risk=_ruff_risk(rule, category),
                    recommendation=(item.get("fix") or {}).get("message", "")
                    or "Apply the linter's suggested correction.",
                    code_snippet=snippet_for(request.workspace_root, path, start, max(start, end)),
                    metadata={"fixable": bool(item.get("fix"))},
                )
            )
        return ScanResult(self.name, findings=findings, duration=time.perf_counter() - started)


class BanditScanner:
    """Python security linter (CWE-tagged)."""

    name = "bandit"
    source = FindingSource.BANDIT
    families = {"python"}

    def available(self) -> bool:
        return tool_available("bandit")

    def scan(self, request: ScanRequest) -> ScanResult:
        targets = request.files_for(".py")
        if not targets:
            return ScanResult(self.name, ran=False, skipped_reason="no Python files changed")
        if not self.available():
            return ScanResult(self.name, ran=False, skipped_reason="bandit is not installed")

        started = time.perf_counter()
        result = run_tool(
            ["bandit", "-f", "json", "-q", *targets],
            cwd=request.workspace_root,
            timeout=request.timeout,
        )
        if not result.available:
            return ScanResult(self.name, ran=False, skipped_reason=result.skipped_reason)

        try:
            payload = json.loads(result.stdout or "{}")
        except json.JSONDecodeError:
            return ScanResult(self.name, ran=False, skipped_reason="bandit produced unparsable output")

        findings: list[UnifiedFinding] = []
        for item in payload.get("results", []):
            start = clamp_line(item.get("line_number"))
            end = clamp_line((item.get("line_range") or [start])[-1], start)
            path = _relative(item.get("filename", ""), request)
            severity = map_severity(item.get("issue_severity", "medium"))
            cwe = (item.get("issue_cwe") or {}).get("id")
            findings.append(
                UnifiedFinding(
                    title=f"{item.get('test_id', 'B000')}: {item.get('test_name', 'Security issue')}",
                    description=item.get("issue_text", ""),
                    category=FindingCategory.SECURITY,
                    severity=severity,
                    file_path=path,
                    start_line=start,
                    end_line=max(start, end),
                    source=self.source,
                    rule_id=item.get("test_id", ""),
                    cwe=f"CWE-{cwe}" if cwe else None,
                    risk="Exploitable security weakness reachable from this code path.",
                    recommendation=item.get("more_info", "") or "Review the flagged construct and use a safe API.",
                    code_snippet=item.get("code", "")
                    or snippet_for(request.workspace_root, path, start, max(start, end)),
                    metadata={"bandit_confidence": item.get("issue_confidence", "MEDIUM")},
                )
            )
        return ScanResult(self.name, findings=findings, duration=time.perf_counter() - started)


class MypyScanner:
    """Static type checker — surfaces real type-safety bugs."""

    name = "mypy"
    source = FindingSource.MYPY
    families = {"python"}

    def available(self) -> bool:
        return tool_available("mypy")

    def scan(self, request: ScanRequest) -> ScanResult:
        targets = request.files_for(".py")
        if not targets:
            return ScanResult(self.name, ran=False, skipped_reason="no Python files changed")
        if not self.available():
            return ScanResult(self.name, ran=False, skipped_reason="mypy is not installed")

        started = time.perf_counter()
        result = run_tool(
            [
                "mypy", "--no-error-summary", "--no-color-output", "--show-error-codes",
                "--ignore-missing-imports", "--follow-imports", "skip", *targets,
            ],
            cwd=request.workspace_root,
            timeout=request.timeout,
        )
        if not result.available:
            return ScanResult(self.name, ran=False, skipped_reason=result.skipped_reason)

        findings: list[UnifiedFinding] = []
        for line in result.stdout.splitlines():
            parsed = _parse_mypy_line(line)
            if parsed is None:
                continue
            path, lineno, level, message, code = parsed
            if level == "note":
                continue
            findings.append(
                UnifiedFinding(
                    title=f"Type error: {message[:110]}",
                    description=message,
                    category=FindingCategory.BUG,
                    severity=Severity.MEDIUM if level == "error" else Severity.LOW,
                    file_path=_relative(path, request),
                    start_line=lineno,
                    end_line=lineno,
                    source=self.source,
                    rule_id=code or "mypy",
                    risk="Type mismatches surface as runtime AttributeError/TypeError in production.",
                    recommendation="Correct the annotation or the call site so the types line up.",
                    code_snippet=snippet_for(request.workspace_root, _relative(path, request), lineno, lineno),
                )
            )
        return ScanResult(self.name, findings=findings, duration=time.perf_counter() - started)


class RadonScanner:
    """Cyclomatic-complexity hotspots — a proxy for maintainability risk."""

    name = "radon"
    source = FindingSource.RADON
    families = {"python"}
    COMPLEXITY_THRESHOLD = 11

    def available(self) -> bool:
        try:
            import radon  # noqa: F401

            return True
        except ImportError:
            return False

    def scan(self, request: ScanRequest) -> ScanResult:
        targets = request.files_for(".py")
        if not targets:
            return ScanResult(self.name, ran=False, skipped_reason="no Python files changed")
        if not self.available():
            return ScanResult(self.name, ran=False, skipped_reason="radon is not installed")

        from radon.complexity import cc_visit

        started = time.perf_counter()
        findings: list[UnifiedFinding] = []
        for relative in targets:
            path = request.workspace_root / relative
            try:
                source = path.read_text(encoding="utf-8", errors="replace")
                blocks = cc_visit(source)
            except (OSError, SyntaxError):
                continue
            for block in blocks:
                if block.complexity < self.COMPLEXITY_THRESHOLD:
                    continue
                severity = Severity.MEDIUM if block.complexity >= 20 else Severity.LOW
                findings.append(
                    UnifiedFinding(
                        title=f"High cyclomatic complexity ({block.complexity}) in {block.name}",
                        description=(
                            f"`{block.name}` has a cyclomatic complexity of {block.complexity}. "
                            "Functions above 10 are hard to test exhaustively and concentrate defects."
                        ),
                        category=FindingCategory.CODE_QUALITY,
                        severity=severity,
                        file_path=relative,
                        start_line=clamp_line(block.lineno),
                        end_line=clamp_line(getattr(block, "endline", block.lineno), block.lineno),
                        source=self.source,
                        rule_id="radon.cc",
                        risk="Complex functions correlate with defect density and low test coverage.",
                        recommendation="Extract cohesive helpers and cover each branch with a test.",
                        code_snippet=snippet_for(request.workspace_root, relative, block.lineno, block.lineno + 3),
                        metadata={"complexity": block.complexity},
                    )
                )
        return ScanResult(self.name, findings=findings, duration=time.perf_counter() - started)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
_HIGH_RISK_RUFF = {"S105", "S106", "S107", "S608", "S301", "S302", "S307", "S324", "S506", "S602", "S605"}


def _ruff_severity(rule: str) -> Severity:
    if rule in _HIGH_RISK_RUFF:
        return Severity.HIGH
    if rule.startswith("S"):
        return Severity.MEDIUM
    if rule.startswith(("F", "B")):
        return Severity.MEDIUM
    if rule.startswith(("E", "W", "N", "UP", "I")):
        return Severity.LOW
    return Severity.LOW


def _ruff_risk(rule: str, category: FindingCategory) -> str:
    if category is FindingCategory.SECURITY:
        return "Security-relevant construct that commonly becomes an exploitable defect."
    if rule.startswith("F"):
        return "Likely runtime error — undefined names and unused imports mask real bugs."
    if rule.startswith("PERF"):
        return "Avoidable overhead on a hot path."
    return "Maintainability cost; increases the chance of future defects."


def _parse_mypy_line(line: str) -> tuple[str, int, str, str, str] | None:
    """Parse ``path:line: level: message  [code]``."""
    parts = line.split(":", 3)
    if len(parts) < 4:
        return None
    path, raw_line, level, remainder = parts
    try:
        lineno = int(raw_line)
    except ValueError:
        return None
    message = remainder.strip()
    code = ""
    if message.endswith("]") and "[" in message:
        head, _, tail = message.rpartition("[")
        code = tail.rstrip("]")
        message = head.strip()
    return path, lineno, level.strip(), message, code


def _relative(path: str, request: ScanRequest) -> str:
    """Normalize a tool-reported path to a repository-relative POSIX path."""
    normalized = path.replace("\\", "/")
    root = request.workspace_root.as_posix()
    if normalized.startswith(root):
        normalized = normalized[len(root) :]
    return normalized.lstrip("./")
