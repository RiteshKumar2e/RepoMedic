"""JavaScript / TypeScript tool adapters: ESLint, tsc and npm audit."""

from __future__ import annotations

import json
import re
import time

from app.core.logging import get_logger
from app.domain.types import UnifiedFinding
from app.models.enums import FindingCategory, FindingSource, Severity
from app.scanners.base import ScanRequest, ScanResult, clamp_line, map_category, snippet_for
from app.scanners.runner import run_tool, tool_available

logger = get_logger(__name__)

JS_SUFFIXES = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts")
TS_SUFFIXES = (".ts", ".tsx", ".mts", ".cts")

# ESLint rules whose violations are genuinely security- or bug-relevant.
_SECURITY_RULES = {
    "no-eval", "no-implied-eval", "no-new-func", "no-script-url",
    "react/no-danger", "react/no-danger-with-children",
    "security/detect-object-injection", "security/detect-non-literal-fs-filename",
    "security/detect-child-process",
}
_BUG_RULES = {
    "no-undef", "no-unreachable", "no-dupe-keys", "no-cond-assign",
    "no-constant-condition", "require-atomic-updates", "no-await-in-loop",
    "@typescript-eslint/no-floating-promises", "@typescript-eslint/await-thenable",
}


class ESLintScanner:
    """Runs the repository's own ESLint config — respects project conventions."""

    name = "eslint"
    source = FindingSource.ESLINT
    families = {"javascript"}

    def available(self) -> bool:
        return tool_available("npx") or tool_available("eslint")

    def scan(self, request: ScanRequest) -> ScanResult:
        targets = request.files_for(*JS_SUFFIXES)
        if not targets:
            return ScanResult(self.name, ran=False, skipped_reason="no JS/TS files changed")
        if not _has_eslint_config(request):
            return ScanResult(
                self.name, ran=False, skipped_reason="repository has no ESLint configuration"
            )
        if not self.available():
            return ScanResult(self.name, ran=False, skipped_reason="eslint/npx is not installed")

        started = time.perf_counter()
        argv = (
            ["eslint", "--format", "json", "--no-color", *targets]
            if tool_available("eslint")
            else ["npx", "--no-install", "eslint", "--format", "json", "--no-color", *targets]
        )
        result = run_tool(argv, cwd=request.workspace_root, timeout=request.timeout)
        if not result.available:
            return ScanResult(self.name, ran=False, skipped_reason=result.skipped_reason)

        try:
            payload = json.loads(_first_json_array(result.stdout) or "[]")
        except json.JSONDecodeError:
            return ScanResult(
                self.name, ran=False, skipped_reason="eslint produced unparsable output",
                raw_error=result.stderr[:400],
            )

        findings: list[UnifiedFinding] = []
        for file_result in payload:
            path = _relative(file_result.get("filePath", ""), request)
            for message in file_result.get("messages", []):
                rule = message.get("ruleId") or "eslint"
                start = clamp_line(message.get("line"))
                end = clamp_line(message.get("endLine"), start)
                severity = Severity.MEDIUM if message.get("severity") == 2 else Severity.LOW
                if rule in _SECURITY_RULES:
                    category, severity = FindingCategory.SECURITY, Severity.HIGH
                elif rule in _BUG_RULES:
                    category = FindingCategory.BUG
                else:
                    category = map_category(rule, FindingCategory.CODE_QUALITY)
                findings.append(
                    UnifiedFinding(
                        title=f"{rule}: {message.get('message', 'Lint violation')}",
                        description=message.get("message", ""),
                        category=category,
                        severity=severity,
                        file_path=path,
                        start_line=start,
                        end_line=max(start, end),
                        source=self.source,
                        rule_id=rule,
                        risk=(
                            "Security-relevant JavaScript pattern."
                            if category is FindingCategory.SECURITY
                            else "Lint violation that commonly precedes a runtime defect."
                        ),
                        recommendation=(message.get("fix") or {}).get("text", "")
                        or "Follow the ESLint rule guidance for this pattern.",
                        code_snippet=snippet_for(request.workspace_root, path, start, max(start, end)),
                        metadata={"fixable": bool(message.get("fix"))},
                    )
                )
        return ScanResult(self.name, findings=findings, duration=time.perf_counter() - started)


class TypeScriptScanner:
    """`tsc --noEmit` — the strongest deterministic signal available for TS."""

    name = "tsc"
    source = FindingSource.TSC
    families = {"javascript"}

    def available(self) -> bool:
        return tool_available("npx") or tool_available("tsc")

    def scan(self, request: ScanRequest) -> ScanResult:
        if not request.files_for(*TS_SUFFIXES):
            return ScanResult(self.name, ran=False, skipped_reason="no TypeScript files changed")
        if "tsconfig.json" not in request.all_files:
            return ScanResult(self.name, ran=False, skipped_reason="repository has no tsconfig.json")
        if not self.available():
            return ScanResult(self.name, ran=False, skipped_reason="tsc/npx is not installed")

        started = time.perf_counter()
        argv = (
            ["tsc", "--noEmit", "--pretty", "false"]
            if tool_available("tsc")
            else ["npx", "--no-install", "tsc", "--noEmit", "--pretty", "false"]
        )
        result = run_tool(argv, cwd=request.workspace_root, timeout=max(request.timeout, 180))
        if not result.available:
            return ScanResult(self.name, ran=False, skipped_reason=result.skipped_reason)

        changed = set(request.target_files)
        findings: list[UnifiedFinding] = []
        for line in (result.stdout + "\n" + result.stderr).splitlines():
            parsed = _parse_tsc_line(line)
            if parsed is None:
                continue
            path, lineno, code, message = parsed
            path = _relative(path, request)
            # tsc checks the whole project; only report on files this PR touched.
            if path not in changed:
                continue
            findings.append(
                UnifiedFinding(
                    title=f"TS{code}: {message[:110]}",
                    description=message,
                    category=FindingCategory.BUG,
                    severity=Severity.HIGH,
                    file_path=path,
                    start_line=lineno,
                    end_line=lineno,
                    source=self.source,
                    rule_id=f"TS{code}",
                    risk="The project will not compile; this breaks the build for everyone.",
                    recommendation="Fix the type error before merging.",
                    code_snippet=snippet_for(request.workspace_root, path, lineno, lineno),
                )
            )
        return ScanResult(self.name, findings=findings, duration=time.perf_counter() - started)


class NpmAuditScanner:
    """Dependency vulnerability audit from the lockfile."""

    name = "npm_audit"
    source = FindingSource.NPM_AUDIT
    families = {"javascript"}

    def available(self) -> bool:
        return tool_available("npm")

    def scan(self, request: ScanRequest) -> ScanResult:
        manifest_touched = any(
            f.endswith(("package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock"))
            for f in request.target_files
        )
        if not manifest_touched:
            return ScanResult(self.name, ran=False, skipped_reason="no dependency manifest changed")
        if "package-lock.json" not in request.all_files:
            return ScanResult(self.name, ran=False, skipped_reason="no package-lock.json to audit")
        if not self.available():
            return ScanResult(self.name, ran=False, skipped_reason="npm is not installed")

        started = time.perf_counter()
        # Auditing requires reaching the advisory registry.
        result = run_tool(
            ["npm", "audit", "--json", "--audit-level", "low", "--package-lock-only"],
            cwd=request.workspace_root,
            timeout=max(request.timeout, 180),
            allow_network=True,
            executes_repository_code=False,
        )
        if not result.available:
            return ScanResult(self.name, ran=False, skipped_reason=result.skipped_reason)

        try:
            payload = json.loads(result.stdout or "{}")
        except json.JSONDecodeError:
            return ScanResult(self.name, ran=False, skipped_reason="npm audit produced unparsable output")

        findings: list[UnifiedFinding] = []
        for package, advisory in (payload.get("vulnerabilities") or {}).items():
            severity = {
                "critical": Severity.CRITICAL,
                "high": Severity.HIGH,
                "moderate": Severity.MEDIUM,
                "low": Severity.LOW,
            }.get(str(advisory.get("severity", "low")).lower(), Severity.LOW)
            via = advisory.get("via") or []
            titles = [v.get("title") for v in via if isinstance(v, dict) and v.get("title")]
            detail = titles[0] if titles else f"{package} has a known vulnerability"
            findings.append(
                UnifiedFinding(
                    title=f"Vulnerable dependency: {package}",
                    description=f"{detail}. Affected range: {advisory.get('range', 'unknown')}.",
                    category=FindingCategory.DEPENDENCY,
                    severity=severity,
                    file_path="package.json",
                    start_line=1,
                    end_line=1,
                    source=self.source,
                    rule_id=f"npm-audit/{package}",
                    risk="A known-exploitable vulnerability ships with the application bundle.",
                    recommendation=(
                        f"Upgrade `{package}` to a patched release"
                        + (" (`npm audit fix`)." if advisory.get("fixAvailable") else ".")
                    ),
                    metadata={"fix_available": bool(advisory.get("fixAvailable"))},
                )
            )
        return ScanResult(self.name, findings=findings, duration=time.perf_counter() - started)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
_TSC_RE = re.compile(r"^(?P<path>[^(]+)\((?P<line>\d+),(?P<col>\d+)\): error TS(?P<code>\d+): (?P<message>.+)$")
_ESLINT_CONFIGS = (
    ".eslintrc", ".eslintrc.js", ".eslintrc.cjs", ".eslintrc.json", ".eslintrc.yml",
    ".eslintrc.yaml", "eslint.config.js", "eslint.config.mjs", "eslint.config.cjs",
)


def _has_eslint_config(request: ScanRequest) -> bool:
    if any(name in request.all_files for name in _ESLINT_CONFIGS):
        return True
    package_json = request.workspace_root / "package.json"
    if package_json.is_file():
        try:
            return "eslintConfig" in json.loads(package_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
    return False


def _parse_tsc_line(line: str) -> tuple[str, int, str, str] | None:
    match = _TSC_RE.match(line.strip())
    if not match:
        return None
    return (
        match.group("path"),
        clamp_line(match.group("line")),
        match.group("code"),
        match.group("message"),
    )


def _first_json_array(text: str) -> str:
    """ESLint sometimes prefixes warnings; extract the JSON payload."""
    start = text.find("[")
    return text[start:] if start >= 0 else ""


def _relative(path: str, request: ScanRequest) -> str:
    normalized = path.replace("\\", "/")
    root = request.workspace_root.as_posix()
    if normalized.startswith(root):
        normalized = normalized[len(root) :]
    return normalized.lstrip("./")
