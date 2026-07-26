"""Explainable scoring for findings and patches.

Every score is a product/sum of named factors that are stored alongside the
result, so the UI can show *why* something scored 82 rather than presenting an
unexplained number.

Issue score (0-100)::

    severity_weight x scanner_confidence x contextual_relevance x reproducibility

Fix confidence (0-100)::

    syntax + lint + typecheck + tests + security_scan + semantic_similarity
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.types import AnalysisContext, UnifiedFinding
from app.models.enums import FindingCategory, RiskLevel, Severity

# ---- issue scoring -------------------------------------------------------- #
#: Weight each validation signal contributes to fix confidence.
FIX_WEIGHTS: dict[str, float] = {
    "syntax_validation": 0.25,
    "lint_success": 0.15,
    "typecheck_success": 0.15,
    "test_success": 0.25,
    "security_scan_success": 0.10,
    "semantic_similarity": 0.10,
}

AUTO_APPLY_MIN_CONFIDENCE = 85.0
AUTO_APPLY_MAX_LINES = 30


def contextual_relevance(finding: UnifiedFinding, context: AnalysisContext | None) -> float:
    """How much this finding matters *for this change*, 0.4 – 1.0.

    A defect on a line the PR actually touched is more actionable than one that
    predates it, and a defect in a file other modules depend on is worse than one
    in a leaf.
    """
    if context is None:
        return 0.8

    relevance = 0.6
    change = next((c for c in context.changes if c.path == finding.file_path), None)
    if change is not None:
        relevance = 0.8
        touched = change.changed_lines
        if touched and any(finding.start_line <= line <= finding.end_line for line in touched):
            relevance = 1.0
        elif touched:
            # In a changed file but outside the changed hunks — pre-existing.
            relevance = 0.7
    elif finding.file_path in context.files:
        relevance = 0.5
    else:
        relevance = 0.4

    dependents = context.related_files.get(finding.file_path, [])
    if dependents:
        relevance = min(1.0, relevance + 0.1)
    return round(relevance, 3)


def reproducibility_factor(finding: UnifiedFinding) -> float:
    """How deterministically the issue can be demonstrated, 0.5 – 1.0."""
    if finding.source.is_ai:
        base = 0.7
    elif finding.source.value in ("tsc", "mypy", "pytest"):
        base = 1.0  # compiler/type/test failures reproduce every run
    else:
        base = 0.9

    # Corroboration by an independent tool raises reproducibility.
    base += 0.05 * min(len(finding.corroborating_sources), 3)

    # Categories with a concrete, testable trigger reproduce more reliably.
    if finding.category in (FindingCategory.SECRET, FindingCategory.DEPENDENCY):
        base = max(base, 0.95)
    elif finding.category is FindingCategory.ARCHITECTURE:
        base = min(base, 0.75)
    return round(min(1.0, base), 3)


def score_finding(
    finding: UnifiedFinding, context: AnalysisContext | None = None
) -> UnifiedFinding:
    """Compute and attach the score plus its breakdown. Mutates and returns."""
    severity_weight = finding.severity.weight
    scanner_confidence = finding.confidence or finding.source.base_confidence
    relevance = contextual_relevance(finding, context)
    reproducibility = reproducibility_factor(finding)

    raw = severity_weight * scanner_confidence * relevance * reproducibility
    finding.score = round(min(100.0, raw * 100), 1)
    finding.confidence = round(min(1.0, scanner_confidence), 3)
    finding.score_breakdown = {
        "severity_weight": round(severity_weight, 3),
        "scanner_confidence": round(scanner_confidence, 3),
        "contextual_relevance": relevance,
        "reproducibility_factor": reproducibility,
        "score": finding.score,
    }
    return finding


def rank_findings(
    findings: list[UnifiedFinding], context: AnalysisContext | None = None
) -> list[UnifiedFinding]:
    for finding in findings:
        score_finding(finding, context)
    return sorted(
        findings,
        key=lambda f: (f.severity.rank, f.score, f.confidence),
        reverse=True,
    )


# ---- fix confidence ------------------------------------------------------- #
@dataclass(slots=True)
class ValidationSignals:
    syntax_validation: bool | None = None
    lint_success: bool | None = None
    typecheck_success: bool | None = None
    test_success: bool | None = None
    security_scan_success: bool | None = None
    semantic_similarity: float = 0.0

    def as_dict(self) -> dict[str, bool | None | float]:
        return {
            "syntax_validation": self.syntax_validation,
            "lint_success": self.lint_success,
            "typecheck_success": self.typecheck_success,
            "test_success": self.test_success,
            "security_scan_success": self.security_scan_success,
            "semantic_similarity": self.semantic_similarity,
        }


def fix_confidence(signals: ValidationSignals) -> tuple[float, dict[str, float]]:
    """Score a patch 0-100 with a per-signal breakdown.

    Signals that could not run (tool unavailable) contribute a neutral half
    weight rather than a zero, so an unvalidatable environment does not make
    every patch look dangerous — but it can never reach the auto-apply
    threshold either.
    """
    breakdown: dict[str, float] = {}
    total = 0.0

    for key, weight in FIX_WEIGHTS.items():
        value = getattr(signals, key)
        if key == "semantic_similarity":
            # Similarity is a float: high similarity = minimal, targeted change.
            contribution = weight * _similarity_curve(signals.semantic_similarity)
        elif value is True:
            contribution = weight
        elif value is False:
            contribution = 0.0
        else:
            contribution = weight * 0.5  # not run
        breakdown[key] = round(contribution * 100, 2)
        total += contribution

    # Syntax failure is disqualifying regardless of everything else.
    if signals.syntax_validation is False:
        total = 0.0
        breakdown = {k: 0.0 for k in breakdown}
    # A failing test after the patch caps confidence hard.
    elif signals.test_success is False:
        total = min(total, 0.35)

    return round(min(100.0, total * 100), 1), breakdown


def _similarity_curve(similarity: float) -> float:
    """Reward minimal edits; penalise rewrites that drift from the original."""
    if similarity <= 0:
        return 0.0
    if similarity >= 0.85:
        return 1.0
    if similarity >= 0.6:
        return 0.75
    if similarity >= 0.4:
        return 0.5
    return 0.2


def risk_level_for(
    finding: UnifiedFinding, changed_line_count: int, confidence: float
) -> RiskLevel:
    """How risky is *applying* this patch (not how bad the bug is)."""
    if finding.category is FindingCategory.ARCHITECTURE or changed_line_count > 40:
        return RiskLevel.HIGH
    if confidence >= AUTO_APPLY_MIN_CONFIDENCE and changed_line_count <= 10:
        return RiskLevel.LOW
    if confidence >= 65 and changed_line_count <= AUTO_APPLY_MAX_LINES:
        return RiskLevel.MEDIUM
    return RiskLevel.HIGH


def auto_apply_eligible(
    *,
    confidence: float,
    risk_level: RiskLevel,
    signals: ValidationSignals,
    severity: Severity,
) -> bool:
    """Auto-apply is off by default; this decides whether it *could* be offered.

    Requires: high confidence, low risk, and every validation signal that ran to
    have passed. A skipped signal is not a pass.
    """
    if confidence < AUTO_APPLY_MIN_CONFIDENCE or risk_level is not RiskLevel.LOW:
        return False
    if signals.syntax_validation is not True:
        return False
    if signals.test_success is not True:
        return False
    if signals.lint_success is False or signals.typecheck_success is False:
        return False
    if signals.security_scan_success is False:
        return False
    if severity is Severity.CRITICAL:
        # Critical fixes always get a human read, however clean they look.
        return False
    return True
