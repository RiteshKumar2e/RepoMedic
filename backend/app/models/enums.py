"""Shared domain vocabulary.

These enums are the contract between scanners, agents, the API layer and the
frontend. `frontend/types/api.ts` mirrors them exactly.
"""

from __future__ import annotations

from enum import Enum


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"

    @property
    def weight(self) -> float:
        """Severity weight used by the issue-scoring formula (0..1)."""
        return {
            Severity.CRITICAL: 1.0,
            Severity.HIGH: 0.8,
            Severity.MEDIUM: 0.55,
            Severity.LOW: 0.3,
            Severity.INFORMATIONAL: 0.15,
        }[self]

    @property
    def rank(self) -> int:
        """Sortable rank — higher is worse."""
        return {
            Severity.CRITICAL: 5,
            Severity.HIGH: 4,
            Severity.MEDIUM: 3,
            Severity.LOW: 2,
            Severity.INFORMATIONAL: 1,
        }[self]

    @classmethod
    def at_least(cls, threshold: "Severity") -> set["Severity"]:
        return {s for s in cls if s.rank >= threshold.rank}


class FindingCategory(str, Enum):
    SECURITY = "security"
    BUG = "bug"
    PERFORMANCE = "performance"
    ARCHITECTURE = "architecture"
    RELIABILITY = "reliability"
    TESTING = "testing"
    CODE_QUALITY = "code_quality"
    DEPENDENCY = "dependency"
    BREAKING_CHANGE = "breaking_change"
    SECRET = "secret"
    PROMPT_INJECTION = "prompt_injection"


class FindingSource(str, Enum):
    """Which subsystem produced a finding."""

    RUFF = "ruff"
    BANDIT = "bandit"
    MYPY = "mypy"
    SEMGREP = "semgrep"
    RADON = "radon"
    ESLINT = "eslint"
    TSC = "tsc"
    NPM_AUDIT = "npm_audit"
    TRIVY = "trivy"
    GITLEAKS = "gitleaks"
    OSV = "osv"
    PYTEST = "pytest"
    AST_RULES = "ast_rules"
    GRAPH = "graph"
    AI_ARCHITECTURE = "ai_architecture"
    AI_SECURITY = "ai_security"
    AI_PERFORMANCE = "ai_performance"
    AI_RELIABILITY = "ai_reliability"
    AI_TESTING = "ai_testing"
    FIREWALL = "firewall"
    CUSTOM_RULE = "custom_rule"

    @property
    def is_ai(self) -> bool:
        return self.value.startswith("ai_")

    @property
    def base_confidence(self) -> float:
        """Prior confidence for the producing tool (0..1).

        Deterministic scanners with low false-positive rates score highest;
        LLM reviewers start lower and are then corroborated by other signals.
        """
        deterministic = {
            FindingSource.GITLEAKS: 0.95,
            FindingSource.OSV: 0.95,
            FindingSource.NPM_AUDIT: 0.9,
            FindingSource.TRIVY: 0.9,
            FindingSource.TSC: 0.95,
            FindingSource.MYPY: 0.85,
            FindingSource.RUFF: 0.85,
            FindingSource.ESLINT: 0.8,
            FindingSource.BANDIT: 0.75,
            FindingSource.SEMGREP: 0.8,
            FindingSource.AST_RULES: 0.8,
            FindingSource.GRAPH: 0.7,
            FindingSource.RADON: 0.7,
            FindingSource.PYTEST: 0.95,
            FindingSource.FIREWALL: 0.85,
            FindingSource.CUSTOM_RULE: 0.75,
        }
        return deterministic.get(self, 0.6)


class FindingStatus(str, Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    FIX_PROPOSED = "fix_proposed"
    FIX_APPROVED = "fix_approved"
    FIX_REJECTED = "fix_rejected"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"
    FALSE_POSITIVE = "false_positive"


class AnalysisStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PullRequestStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    MERGED = "merged"
    DRAFT = "draft"


class PatchStatus(str, Enum):
    PROPOSED = "proposed"
    VALIDATING = "validating"
    VALIDATED = "validated"
    VALIDATION_FAILED = "validation_failed"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"


class ValidationStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ReviewerAgent(str, Enum):
    ARCHITECTURE = "architecture"
    SECURITY = "security"
    PERFORMANCE = "performance"
    RELIABILITY = "reliability"
    TESTING = "testing"

    @property
    def source(self) -> FindingSource:
        return {
            ReviewerAgent.ARCHITECTURE: FindingSource.AI_ARCHITECTURE,
            ReviewerAgent.SECURITY: FindingSource.AI_SECURITY,
            ReviewerAgent.PERFORMANCE: FindingSource.AI_PERFORMANCE,
            ReviewerAgent.RELIABILITY: FindingSource.AI_RELIABILITY,
            ReviewerAgent.TESTING: FindingSource.AI_TESTING,
        }[self]


class AnalysisStage(str, Enum):
    """Ordered pipeline stages streamed to the UI over SSE."""

    QUEUED = "queued"
    CLONING = "cloning"
    DIFFING = "diffing"
    DETECTING = "detecting_languages"
    PARSING = "parsing"
    GRAPHING = "building_graph"
    RETRIEVING = "retrieving_context"
    SCANNING = "running_scanners"
    REVIEWING = "ai_review"
    MERGING = "merging_findings"
    PATCHING = "generating_patches"
    VALIDATING = "validating_patches"
    PERSISTING = "persisting"
    DONE = "done"

    @property
    def progress(self) -> int:
        order = list(AnalysisStage)
        return round((order.index(self) / (len(order) - 1)) * 100)
