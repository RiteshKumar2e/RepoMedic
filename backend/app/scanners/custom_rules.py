"""Repository-defined custom rules.

Teams add regex rules through Settings; they run alongside the built-in tools
and produce findings in the same unified schema.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from app.core.logging import get_logger
from app.domain.types import Language, UnifiedFinding
from app.models.enums import FindingCategory, FindingSource, Severity
from app.scanners.base import ScanRequest, ScanResult, snippet_for

logger = get_logger(__name__)

MAX_PATTERN_LENGTH = 500
MAX_RULES = 50


@dataclass(slots=True)
class CompiledRule:
    rule_id: str
    description: str
    pattern: re.Pattern[str]
    severity: Severity
    languages: set[str] = field(default_factory=set)


def compile_rules(raw_rules: list[dict]) -> list[CompiledRule]:
    """Compile user rules defensively — a bad regex must never break an analysis."""
    compiled: list[CompiledRule] = []
    for raw in raw_rules[:MAX_RULES]:
        if not raw.get("enabled", True):
            continue
        pattern_text = (raw.get("pattern") or "").strip()
        if not pattern_text or len(pattern_text) > MAX_PATTERN_LENGTH:
            continue
        try:
            pattern = re.compile(pattern_text)
        except re.error as exc:
            logger.warning("custom_rule.invalid_regex", rule=raw.get("id"), error=str(exc))
            continue
        try:
            severity = Severity(raw.get("severity", "medium"))
        except ValueError:
            severity = Severity.MEDIUM
        compiled.append(
            CompiledRule(
                rule_id=str(raw.get("id", "custom")),
                description=str(raw.get("description", "Custom rule matched")),
                pattern=pattern,
                severity=severity,
                languages={str(lang).lower() for lang in raw.get("languages", [])},
            )
        )
    return compiled


class CustomRuleScanner:
    """Applies the repository's own rules to changed files."""

    name = "custom_rules"
    source = FindingSource.CUSTOM_RULE
    families = {"any"}

    def __init__(self, rules: list[dict] | None = None) -> None:
        self._rules = compile_rules(rules or [])

    def available(self) -> bool:
        return bool(self._rules)

    def scan(self, request: ScanRequest) -> ScanResult:
        if not self._rules:
            return ScanResult(self.name, ran=False, skipped_reason="no custom rules configured")

        started = time.perf_counter()
        findings: list[UnifiedFinding] = []
        for relative in request.target_files:
            language = Language.from_path(relative)
            path = request.workspace_root / relative
            try:
                content = path.read_text(encoding="utf-8", errors="strict")
            except (OSError, UnicodeDecodeError):
                continue

            for rule in self._rules:
                if rule.languages and language.value not in rule.languages:
                    continue
                for line_number, line in enumerate(content.splitlines(), start=1):
                    if len(line) > 2000:
                        continue
                    try:
                        matched = rule.pattern.search(line)
                    except re.error:
                        break
                    if not matched:
                        continue
                    findings.append(
                        UnifiedFinding(
                            title=f"Custom rule `{rule.rule_id}` matched",
                            description=rule.description,
                            category=FindingCategory.CODE_QUALITY,
                            severity=rule.severity,
                            file_path=relative,
                            start_line=line_number,
                            end_line=line_number,
                            source=self.source,
                            rule_id=f"custom/{rule.rule_id}",
                            risk="Violates a convention this team has chosen to enforce.",
                            recommendation=rule.description,
                            code_snippet=snippet_for(request.workspace_root, relative, line_number, line_number),
                        )
                    )
        return ScanResult(self.name, findings=findings, duration=time.perf_counter() - started)
