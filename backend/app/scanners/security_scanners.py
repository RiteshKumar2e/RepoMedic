"""Security tool adapters: Semgrep, Gitleaks, OSV-Scanner, Trivy.

Two of these have zero external dependencies and therefore always run:
:class:`BuiltinSecretScanner` and :class:`PromptInjectionScanner`. The rest
degrade gracefully with an explicit ``skipped_reason`` when the binary is absent.
"""

from __future__ import annotations

import json
import time

from app.core.logging import get_logger
from app.domain.types import UnifiedFinding
from app.models.enums import FindingCategory, FindingSource, Severity
from app.scanners.base import ScanRequest, ScanResult, clamp_line, map_severity, snippet_for
from app.scanners.runner import run_tool, tool_available
from app.security.firewall import scan_for_injection
from app.security.secrets import detect_secrets

logger = get_logger(__name__)


class SemgrepScanner:
    """Multi-language semantic pattern matching with curated security rulesets."""

    name = "semgrep"
    source = FindingSource.SEMGREP
    families = {"python", "javascript"}

    def available(self) -> bool:
        return tool_available("semgrep")

    def scan(self, request: ScanRequest) -> ScanResult:
        targets = request.files_for(".py", ".js", ".jsx", ".ts", ".tsx")
        if not targets:
            return ScanResult(self.name, ran=False, skipped_reason="no supported files changed")
        if not self.available():
            return ScanResult(self.name, ran=False, skipped_reason="semgrep is not installed")

        started = time.perf_counter()
        result = run_tool(
            ["semgrep", "--config", "auto", "--json", "--quiet", "--metrics", "off",
             "--timeout", "30", *targets],
            cwd=request.workspace_root,
            timeout=max(request.timeout, 180),
            allow_network=True,  # `--config auto` resolves rules from the registry
        )
        if not result.available:
            return ScanResult(self.name, ran=False, skipped_reason=result.skipped_reason)

        try:
            payload = json.loads(result.stdout or "{}")
        except json.JSONDecodeError:
            return ScanResult(self.name, ran=False, skipped_reason="semgrep produced unparsable output")

        findings: list[UnifiedFinding] = []
        for item in payload.get("results", []):
            extra = item.get("extra", {})
            metadata = extra.get("metadata", {})
            start = clamp_line(item.get("start", {}).get("line"))
            end = clamp_line(item.get("end", {}).get("line"), start)
            path = _relative(item.get("path", ""), request)
            rule_id = item.get("check_id", "semgrep")
            cwe_values = metadata.get("cwe") or []
            cwe = cwe_values[0] if isinstance(cwe_values, list) and cwe_values else metadata.get("cwe")
            findings.append(
                UnifiedFinding(
                    title=f"{rule_id.rsplit('.', 1)[-1]}: {extra.get('message', '')[:110]}",
                    description=extra.get("message", ""),
                    category=_semgrep_category(metadata),
                    severity=map_severity(extra.get("severity", "WARNING"), Severity.MEDIUM),
                    file_path=path,
                    start_line=start,
                    end_line=max(start, end),
                    source=self.source,
                    rule_id=rule_id,
                    cwe=str(cwe) if cwe else None,
                    risk=metadata.get("impact", "") or "Matched a known insecure or defective code pattern.",
                    recommendation=metadata.get("fix", "") or extra.get("fix", "")
                    or "Replace the pattern with the safe alternative documented by the rule.",
                    code_snippet=extra.get("lines", "")
                    or snippet_for(request.workspace_root, path, start, max(start, end)),
                    metadata={"owasp": metadata.get("owasp"), "references": metadata.get("references", [])},
                )
            )
        return ScanResult(self.name, findings=findings, duration=time.perf_counter() - started)


class GitleaksScanner:
    """Committed-secret detection across the working tree."""

    name = "gitleaks"
    source = FindingSource.GITLEAKS
    families = {"any"}

    def available(self) -> bool:
        return tool_available("gitleaks")

    def scan(self, request: ScanRequest) -> ScanResult:
        if not self.available():
            return ScanResult(self.name, ran=False, skipped_reason="gitleaks is not installed")

        started = time.perf_counter()
        report_path = request.workspace_root / ".repomedic-gitleaks.json"
        result = run_tool(
            ["gitleaks", "detect", "--no-git", "--redact", "--report-format", "json",
             "--report-path", report_path.name, "--exit-code", "0"],
            cwd=request.workspace_root,
            timeout=request.timeout,
            writable=True,
        )
        if not result.available:
            return ScanResult(self.name, ran=False, skipped_reason=result.skipped_reason)

        try:
            payload = json.loads(report_path.read_text(encoding="utf-8") or "[]")
        except (OSError, json.JSONDecodeError):
            payload = []
        finally:
            report_path.unlink(missing_ok=True)

        changed = set(request.target_files)
        findings: list[UnifiedFinding] = []
        for item in payload:
            path = _relative(item.get("File", ""), request)
            if changed and path not in changed:
                continue
            line = clamp_line(item.get("StartLine"))
            findings.append(
                UnifiedFinding(
                    title=f"Exposed secret: {item.get('RuleID', 'unknown rule')}",
                    description=item.get("Description", "A credential was committed to the repository."),
                    category=FindingCategory.SECRET,
                    severity=Severity.CRITICAL,
                    file_path=path,
                    start_line=line,
                    end_line=clamp_line(item.get("EndLine"), line),
                    source=self.source,
                    rule_id=item.get("RuleID", "gitleaks"),
                    cwe="CWE-798",
                    risk="A committed credential is compromised the moment it lands in history.",
                    recommendation="Revoke and rotate the credential, then load it from the environment.",
                    code_snippet="<redacted by gitleaks>",
                )
            )
        return ScanResult(self.name, findings=findings, duration=time.perf_counter() - started)


class OSVScanner:
    """Dependency vulnerabilities from the OSV database (multi-ecosystem)."""

    name = "osv"
    source = FindingSource.OSV
    families = {"any"}

    def available(self) -> bool:
        return tool_available("osv-scanner")

    def scan(self, request: ScanRequest) -> ScanResult:
        manifests = [
            f for f in request.target_files
            if f.endswith(("requirements.txt", "package-lock.json", "pnpm-lock.yaml",
                           "poetry.lock", "yarn.lock", "Pipfile.lock", "go.sum"))
        ]
        if not manifests:
            return ScanResult(self.name, ran=False, skipped_reason="no dependency lockfile changed")
        if not self.available():
            return ScanResult(self.name, ran=False, skipped_reason="osv-scanner is not installed")

        started = time.perf_counter()
        result = run_tool(
            ["osv-scanner", "--format", "json", "--recursive", "."],
            cwd=request.workspace_root,
            timeout=max(request.timeout, 180),
            allow_network=True,
        )
        if not result.available:
            return ScanResult(self.name, ran=False, skipped_reason=result.skipped_reason)

        try:
            payload = json.loads(result.stdout or "{}")
        except json.JSONDecodeError:
            return ScanResult(self.name, ran=False, skipped_reason="osv-scanner produced unparsable output")

        findings: list[UnifiedFinding] = []
        for source_result in payload.get("results", []):
            manifest = _relative(source_result.get("source", {}).get("path", ""), request)
            for package in source_result.get("packages", []):
                info = package.get("package", {})
                for vuln in package.get("vulnerabilities", []):
                    findings.append(
                        UnifiedFinding(
                            title=f"{vuln.get('id', 'OSV')} in {info.get('name', 'dependency')}",
                            description=vuln.get("summary") or vuln.get("details", "")[:600],
                            category=FindingCategory.DEPENDENCY,
                            severity=_osv_severity(vuln),
                            file_path=manifest or "requirements.txt",
                            start_line=1,
                            end_line=1,
                            source=self.source,
                            rule_id=vuln.get("id", "OSV"),
                            risk="A dependency with a published advisory is reachable from this build.",
                            recommendation=(
                                f"Upgrade `{info.get('name')}` beyond the affected range "
                                f"(currently {info.get('version', 'unknown')})."
                            ),
                            metadata={"aliases": vuln.get("aliases", [])},
                        )
                    )
        return ScanResult(self.name, findings=findings, duration=time.perf_counter() - started)


class TrivyScanner:
    """Filesystem scan for vulnerable packages, misconfigurations and secrets."""

    name = "trivy"
    source = FindingSource.TRIVY
    families = {"any"}

    def available(self) -> bool:
        return tool_available("trivy")

    def scan(self, request: ScanRequest) -> ScanResult:
        if not self.available():
            return ScanResult(self.name, ran=False, skipped_reason="trivy is not installed")

        started = time.perf_counter()
        result = run_tool(
            ["trivy", "fs", "--format", "json", "--quiet", "--scanners", "vuln,misconfig", "."],
            cwd=request.workspace_root,
            timeout=max(request.timeout, 240),
            allow_network=True,
        )
        if not result.available:
            return ScanResult(self.name, ran=False, skipped_reason=result.skipped_reason)

        try:
            payload = json.loads(result.stdout or "{}")
        except json.JSONDecodeError:
            return ScanResult(self.name, ran=False, skipped_reason="trivy produced unparsable output")

        findings: list[UnifiedFinding] = []
        for target in payload.get("Results", []):
            path = _relative(target.get("Target", ""), request)
            for vuln in target.get("Vulnerabilities") or []:
                findings.append(
                    UnifiedFinding(
                        title=f"{vuln.get('VulnerabilityID')} in {vuln.get('PkgName')}",
                        description=vuln.get("Description", "")[:600],
                        category=FindingCategory.DEPENDENCY,
                        severity=map_severity(vuln.get("Severity", "MEDIUM")),
                        file_path=path or "Dockerfile",
                        start_line=1,
                        end_line=1,
                        source=self.source,
                        rule_id=vuln.get("VulnerabilityID", "trivy"),
                        risk="Known vulnerability present in the resolved dependency tree.",
                        recommendation=f"Upgrade to {vuln.get('FixedVersion') or 'a patched release'}.",
                    )
                )
            for misconfig in target.get("Misconfigurations") or []:
                findings.append(
                    UnifiedFinding(
                        title=f"{misconfig.get('ID')}: {misconfig.get('Title', '')}",
                        description=misconfig.get("Description", ""),
                        category=FindingCategory.SECURITY,
                        severity=map_severity(misconfig.get("Severity", "MEDIUM")),
                        file_path=path,
                        start_line=clamp_line((misconfig.get("CauseMetadata") or {}).get("StartLine")),
                        end_line=clamp_line((misconfig.get("CauseMetadata") or {}).get("EndLine")),
                        source=self.source,
                        rule_id=misconfig.get("ID", "trivy-misconfig"),
                        risk=misconfig.get("Message", "Insecure configuration."),
                        recommendation=misconfig.get("Resolution", "Apply the recommended hardening."),
                    )
                )
        return ScanResult(self.name, findings=findings, duration=time.perf_counter() - started)


class BuiltinSecretScanner:
    """Dependency-free secret detection — always runs, even with no tooling."""

    name = "builtin_secrets"
    source = FindingSource.GITLEAKS
    families = {"any"}

    def available(self) -> bool:
        return True

    def scan(self, request: ScanRequest) -> ScanResult:
        started = time.perf_counter()
        findings: list[UnifiedFinding] = []
        for relative in request.target_files:
            path = request.workspace_root / relative
            try:
                content = path.read_text(encoding="utf-8", errors="strict")
            except (OSError, UnicodeDecodeError):
                continue
            for match in detect_secrets(content, relative):
                findings.append(
                    UnifiedFinding(
                        title=f"Hardcoded {match.label}",
                        description=(
                            f"A {match.label.lower()} appears to be hardcoded at {relative}:{match.line} "
                            f"(masked: `{match.preview}`, Shannon entropy {match.entropy})."
                        ),
                        category=FindingCategory.SECRET,
                        severity=Severity.CRITICAL if match.rule_id != "generic-assignment" else Severity.HIGH,
                        file_path=relative,
                        start_line=match.line,
                        end_line=match.line,
                        source=self.source,
                        rule_id=f"secret/{match.rule_id}",
                        cwe="CWE-798",
                        confidence=match.confidence,
                        risk=(
                            "Anyone with repository read access — and anyone who ever clones it — "
                            "holds this credential. Git history keeps it after deletion."
                        ),
                        recommendation=(
                            "Revoke and rotate the credential immediately, then read it from an "
                            "environment variable or secret manager."
                        ),
                        code_snippet=f"line {match.line}: <redacted {match.label.lower()}>",
                    )
                )
        return ScanResult(self.name, findings=findings, duration=time.perf_counter() - started)


class PromptInjectionScanner:
    """Flags prompt-injection payloads hidden in repository content."""

    name = "prompt_injection"
    source = FindingSource.FIREWALL
    families = {"any"}

    def available(self) -> bool:
        return True

    def scan(self, request: ScanRequest) -> ScanResult:
        started = time.perf_counter()
        findings: list[UnifiedFinding] = []
        for relative in request.target_files:
            path = request.workspace_root / relative
            try:
                content = path.read_text(encoding="utf-8", errors="strict")
            except (OSError, UnicodeDecodeError):
                continue
            report = scan_for_injection(content, source_label=relative)
            for match in report.matches:
                findings.append(
                    UnifiedFinding(
                        title=f"Prompt injection attempt ({match.technique}): {match.rule_id}",
                        description=(
                            f"{match.description}. RepoMedic treats repository text as data and never "
                            f"executes instructions found inside it, but this content is designed to "
                            f"manipulate AI review tooling.\n\nExcerpt: `{match.excerpt}`"
                        ),
                        category=FindingCategory.PROMPT_INJECTION,
                        severity=Severity.HIGH if match.confidence >= 0.85 else Severity.MEDIUM,
                        file_path=relative,
                        start_line=match.line,
                        end_line=match.line,
                        source=self.source,
                        rule_id=f"firewall/{match.rule_id}",
                        confidence=match.confidence,
                        cwe="CWE-77",
                        risk=(
                            "Downstream AI tooling without an input firewall can be steered into "
                            "suppressing findings or leaking context."
                        ),
                        recommendation="Remove the embedded directives and review who introduced them.",
                        code_snippet=match.excerpt,
                    )
                )
        return ScanResult(self.name, findings=findings, duration=time.perf_counter() - started)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _semgrep_category(metadata: dict) -> FindingCategory:
    category = str(metadata.get("category", "")).lower()
    if category == "security" or metadata.get("cwe") or metadata.get("owasp"):
        return FindingCategory.SECURITY
    if category == "performance":
        return FindingCategory.PERFORMANCE
    if category == "correctness":
        return FindingCategory.BUG
    return FindingCategory.CODE_QUALITY


def _osv_severity(vuln: dict) -> Severity:
    for entry in vuln.get("severity", []) or []:
        score = str(entry.get("score", ""))
        if score.startswith("CVSS:"):
            # Take the base score from the vector when present.
            for part in score.split("/"):
                if part.startswith("AV:") and "N" in part:
                    return Severity.HIGH
    database = (vuln.get("database_specific") or {}).get("severity", "")
    return map_severity(str(database), Severity.MEDIUM)


def _relative(path: str, request: ScanRequest) -> str:
    normalized = path.replace("\\", "/")
    root = request.workspace_root.as_posix()
    if normalized.startswith(root):
        normalized = normalized[len(root) :]
    return normalized.lstrip("./")
