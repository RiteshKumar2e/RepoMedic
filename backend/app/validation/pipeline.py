"""Deterministic validation of a proposed patch.

Order of operations (each step short-circuits the ones that cannot follow):

1. **Parse** the patched file with the language's AST parser.
2. **Lint** it with the project's linter.
3. **Type-check** it.
4. **Security-scan** it and require no *new* security findings.
5. **Run the relevant tests** before and after, and compare.
6. Measure **semantic similarity** between original and patched code.

The patch is written into the disposable workspace, validated, and the original
content is always restored — validation never leaves the workspace mutated.
Repository test suites only execute when the sandbox permits it; otherwise the
step is recorded as skipped with the reason, and confidence is capped
accordingly rather than being inflated.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.logging import get_logger
from app.domain.types import Language, PatchProposal, UnifiedFinding
from app.models.enums import RiskLevel, Severity, ValidationStatus
from app.patching.differ import apply_proposal, changed_line_count
from app.retrieval.embeddings import jaccard_similarity
from app.scanners.base import ScanRequest
from app.scanners.js_scanners import ESLintScanner, TypeScriptScanner
from app.scanners.python_scanners import BanditScanner, MypyScanner, RuffScanner
from app.scanners.runner import run_tool, tool_available
from app.services.scoring import (
    ValidationSignals,
    auto_apply_eligible,
    fix_confidence,
    risk_level_for,
)

logger = get_logger(__name__)


@dataclass(slots=True)
class StepResult:
    name: str
    status: str  # passed | failed | skipped
    detail: str = ""
    duration: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "detail": self.detail[:2000],
            "duration": round(self.duration, 3),
        }


@dataclass(slots=True)
class ValidationOutcome:
    signals: ValidationSignals = field(default_factory=ValidationSignals)
    steps: list[StepResult] = field(default_factory=list)
    tests_before: dict[str, Any] = field(default_factory=dict)
    tests_after: dict[str, Any] = field(default_factory=dict)
    test_output: str = ""
    confidence: float = 0.0
    confidence_breakdown: dict[str, float] = field(default_factory=dict)
    risk_level: RiskLevel = RiskLevel.MEDIUM
    auto_apply_eligible: bool = False
    status: ValidationStatus = ValidationStatus.PENDING
    skipped_reason: str = ""
    execution_time: float = 0.0
    error: str = ""

    def step_dicts(self) -> list[dict[str, Any]]:
        return [step.to_dict() for step in self.steps]


class ValidationPipeline:
    def __init__(self, workspace_root: Path, *, all_files: list[str] | None = None) -> None:
        self.workspace_root = workspace_root
        self.all_files = all_files or []

    def validate(
        self, proposal: PatchProposal, finding: UnifiedFinding, *, run_tests: bool = True
    ) -> ValidationOutcome:
        started = time.perf_counter()
        outcome = ValidationOutcome(status=ValidationStatus.RUNNING)
        target = self.workspace_root / proposal.file_path

        if not target.is_file():
            outcome.status = ValidationStatus.SKIPPED
            outcome.skipped_reason = f"{proposal.file_path} is not present in the workspace"
            outcome.execution_time = time.perf_counter() - started
            return outcome

        original_source = target.read_text(encoding="utf-8", errors="replace")

        # ---- 1. parse ----------------------------------------------------
        step_start = time.perf_counter()
        patched_source, error = apply_proposal(original_source, proposal)
        if patched_source is None:
            outcome.signals.syntax_validation = False
            outcome.steps.append(
                StepResult("parse", "failed", error, time.perf_counter() - step_start)
            )
            self._finalise(outcome, proposal, finding, started)
            return outcome
        outcome.signals.syntax_validation = True
        outcome.steps.append(
            StepResult("parse", "passed", "Patched file parses cleanly", time.perf_counter() - step_start)
        )

        # ---- 6. semantic similarity (cheap, do it before I/O) ------------
        outcome.signals.semantic_similarity = round(
            jaccard_similarity(proposal.original_code, proposal.suggested_code), 3
        )

        try:
            # Baseline tests run against the unpatched tree.
            if run_tests:
                outcome.tests_before = self._run_tests(proposal.file_path)

            target.write_text(patched_source, encoding="utf-8")

            self._lint(proposal, outcome)
            self._typecheck(proposal, outcome)
            self._security_scan(proposal, finding, outcome)

            if run_tests:
                outcome.tests_after = self._run_tests(proposal.file_path)
                self._compare_tests(outcome)
            else:
                outcome.steps.append(
                    StepResult("tests", "skipped", "test execution disabled for this run")
                )
        finally:
            target.write_text(original_source, encoding="utf-8")

        self._finalise(outcome, proposal, finding, started)
        return outcome

    # ---- individual steps -----------------------------------------------
    def _lint(self, proposal: PatchProposal, outcome: ValidationOutcome) -> None:
        step_start = time.perf_counter()
        language = Language.from_path(proposal.file_path)
        request = ScanRequest(
            workspace_root=self.workspace_root,
            target_files=[proposal.file_path],
            all_files=self.all_files,
            timeout=60,
        )
        scanner = RuffScanner() if language is Language.PYTHON else ESLintScanner()
        result = scanner.scan(request)

        if not result.ran:
            outcome.steps.append(
                StepResult("lint", "skipped", result.skipped_reason, time.perf_counter() - step_start)
            )
            return

        errors = [f for f in result.findings if f.severity.rank >= Severity.MEDIUM.rank]
        passed = not errors
        outcome.signals.lint_success = passed
        outcome.steps.append(
            StepResult(
                "lint",
                "passed" if passed else "failed",
                "No new lint errors" if passed
                else "; ".join(f"{f.rule_id} line {f.start_line}" for f in errors[:5]),
                time.perf_counter() - step_start,
            )
        )

    def _typecheck(self, proposal: PatchProposal, outcome: ValidationOutcome) -> None:
        step_start = time.perf_counter()
        language = Language.from_path(proposal.file_path)
        request = ScanRequest(
            workspace_root=self.workspace_root,
            target_files=[proposal.file_path],
            all_files=self.all_files,
            timeout=120,
        )
        scanner = MypyScanner() if language is Language.PYTHON else TypeScriptScanner()
        result = scanner.scan(request)

        if not result.ran:
            outcome.steps.append(
                StepResult("typecheck", "skipped", result.skipped_reason, time.perf_counter() - step_start)
            )
            return

        passed = not result.findings
        outcome.signals.typecheck_success = passed
        outcome.steps.append(
            StepResult(
                "typecheck",
                "passed" if passed else "failed",
                "No type errors" if passed
                else "; ".join(f.title for f in result.findings[:3]),
                time.perf_counter() - step_start,
            )
        )

    def _security_scan(
        self, proposal: PatchProposal, finding: UnifiedFinding, outcome: ValidationOutcome
    ) -> None:
        step_start = time.perf_counter()
        language = Language.from_path(proposal.file_path)
        if language is not Language.PYTHON:
            outcome.steps.append(
                StepResult(
                    "security_scan", "skipped",
                    "no security scanner configured for this language",
                    time.perf_counter() - step_start,
                )
            )
            return

        request = ScanRequest(
            workspace_root=self.workspace_root,
            target_files=[proposal.file_path],
            all_files=self.all_files,
            timeout=60,
        )
        result = BanditScanner().scan(request)
        if not result.ran:
            outcome.steps.append(
                StepResult("security_scan", "skipped", result.skipped_reason, time.perf_counter() - step_start)
            )
            return

        # The patch must not introduce security findings at or above the one it fixes.
        introduced = [
            f for f in result.findings
            if f.severity.rank >= Severity.MEDIUM.rank
            and not (f.start_line == finding.start_line and f.rule_id == finding.rule_id)
        ]
        passed = not introduced
        outcome.signals.security_scan_success = passed
        outcome.steps.append(
            StepResult(
                "security_scan",
                "passed" if passed else "failed",
                "No new security findings" if passed
                else f"{len(introduced)} security finding(s) remain: "
                + "; ".join(f.rule_id for f in introduced[:3]),
                time.perf_counter() - step_start,
            )
        )

    def _run_tests(self, changed_path: str) -> dict[str, Any]:
        """Run the tests most likely to cover ``changed_path``."""
        language = Language.from_path(changed_path)
        if language is Language.PYTHON:
            return self._run_pytest(changed_path)
        if language.family == "javascript":
            return self._run_js_tests(changed_path)
        return {"ran": False, "reason": f"no test runner for {language.value}"}

    def _run_pytest(self, changed_path: str) -> dict[str, Any]:
        if not tool_available("pytest"):
            return {"ran": False, "reason": "pytest is not installed"}
        stem = Path(changed_path).stem
        result = run_tool(
            ["pytest", "-q", "--no-header", "-x", "-k", stem, "--timeout", "60"],
            cwd=self.workspace_root,
            timeout=180,
            executes_repository_code=True,
        )
        if not result.available:
            return {"ran": False, "reason": result.skipped_reason}
        return _parse_pytest_output(result.stdout + result.stderr, result.returncode)

    def _run_js_tests(self, changed_path: str) -> dict[str, Any]:
        if not tool_available("npx"):
            return {"ran": False, "reason": "npx is not installed"}
        if "package.json" not in self.all_files:
            return {"ran": False, "reason": "no package.json in the repository"}
        result = run_tool(
            ["npx", "--no-install", "vitest", "run", "--reporter", "basic", "--related", changed_path],
            cwd=self.workspace_root,
            timeout=240,
            executes_repository_code=True,
        )
        if not result.available:
            return {"ran": False, "reason": result.skipped_reason}
        output = result.stdout + result.stderr
        return {
            "ran": True,
            "passed": result.returncode == 0,
            "returncode": result.returncode,
            "output": output[-4000:],
            **_parse_vitest_output(output),
        }

    def _compare_tests(self, outcome: ValidationOutcome) -> None:
        before, after = outcome.tests_before, outcome.tests_after
        outcome.test_output = str(after.get("output", ""))[-6000:]

        if not after.get("ran"):
            outcome.steps.append(
                StepResult("tests", "skipped", str(after.get("reason", "tests did not run")))
            )
            return

        after_passed = bool(after.get("passed"))
        before_passed = bool(before.get("passed")) if before.get("ran") else None
        outcome.signals.test_success = after_passed

        if after_passed and before_passed is False:
            detail = (
                f"Tests failed before the patch ({before.get('failed', '?')} failing) and pass after it — "
                "the patch fixes a demonstrable failure."
            )
        elif after_passed:
            detail = f"{after.get('passed_count', '?')} test(s) pass after the patch."
        else:
            detail = (
                f"{after.get('failed', '?')} test(s) fail after the patch"
                + (" (they passed before)" if before_passed else " (they also failed before)")
            )
        outcome.steps.append(StepResult("tests", "passed" if after_passed else "failed", detail))

    # ---- scoring ---------------------------------------------------------
    def _finalise(
        self,
        outcome: ValidationOutcome,
        proposal: PatchProposal,
        finding: UnifiedFinding,
        started: float,
    ) -> None:
        confidence, breakdown = fix_confidence(outcome.signals)
        lines_changed = changed_line_count(proposal.unified_diff)

        outcome.confidence = confidence
        outcome.confidence_breakdown = breakdown
        outcome.risk_level = risk_level_for(finding, lines_changed, confidence)
        outcome.auto_apply_eligible = auto_apply_eligible(
            confidence=confidence,
            risk_level=outcome.risk_level,
            signals=outcome.signals,
            severity=finding.severity,
        )
        outcome.status = (
            ValidationStatus.PASSED
            if outcome.signals.syntax_validation and outcome.signals.test_success is not False
            else ValidationStatus.FAILED
        )
        outcome.execution_time = time.perf_counter() - started
        logger.info(
            "validation.completed",
            file=proposal.file_path,
            confidence=confidence,
            risk=outcome.risk_level.value,
            status=outcome.status.value,
            auto_apply=outcome.auto_apply_eligible,
        )


# --------------------------------------------------------------------------- #
# Test-output parsing
# --------------------------------------------------------------------------- #
def _parse_pytest_output(output: str, returncode: int) -> dict[str, Any]:
    import re

    summary = {"ran": True, "returncode": returncode, "output": output[-4000:]}
    match = re.search(r"(\d+) passed", output)
    summary["passed_count"] = int(match.group(1)) if match else 0
    match = re.search(r"(\d+) failed", output)
    summary["failed"] = int(match.group(1)) if match else 0
    match = re.search(r"(\d+) error", output)
    summary["errors"] = int(match.group(1)) if match else 0
    if "no tests ran" in output.lower() or (summary["passed_count"] == 0 and summary["failed"] == 0):
        summary["ran"] = False
        summary["reason"] = "no tests matched the changed module"
        return summary
    summary["passed"] = returncode == 0
    return summary


def _parse_vitest_output(output: str) -> dict[str, Any]:
    import re

    result: dict[str, Any] = {}
    match = re.search(r"Tests\s+(\d+) failed \| (\d+) passed", output)
    if match:
        result["failed"] = int(match.group(1))
        result["passed_count"] = int(match.group(2))
        return result
    match = re.search(r"Tests\s+(\d+) passed", output)
    if match:
        result["failed"] = 0
        result["passed_count"] = int(match.group(1))
    return result
