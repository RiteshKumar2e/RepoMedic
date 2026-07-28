"""The analysis orchestrator.

Runs the full repository-aware review for one pull request and persists the
result. Each stage publishes a progress event so the UI can stream it, and every
stage is individually failure-isolated: a broken scanner or an unreachable LLM
degrades the report, it does not abort the analysis.

Stages
------
clone → diff → detect languages → parse → build graph → retrieve context →
run scanners → AI review → merge/rank → generate patches → validate → persist
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlmodel import Session, select

from app.agents.fix_generator import FixGenerator
from app.agents.reviewers import REVIEWER_AGENTS, ReviewOutcome
from app.analyzers.base import AnalyzerContext
from app.analyzers.registry import analyzer_for_path
from app.core.config import settings
from app.core.logging import get_logger
from app.domain.types import (
    AnalysisContext,
    FileChange,
    SourceFile,
    UnifiedFinding,
)
from app.github import service as github_service
from app.graph.builder import KnowledgeGraph, build_graph
from app.llm.base import UsageTracker
from app.llm.registry import get_provider
from app.models.entities import (
    Analysis,
    Finding,
    GitHubInstallation,
    Patch,
    PullRequest,
    Repository,
    ValidationRun,
    utcnow,
)
from app.models.enums import (
    AnalysisStage,
    AnalysisStatus,
    FindingCategory,
    FindingSource,
    FindingStatus,
    PatchStatus,
    Severity,
    ValidationStatus,
)
from app.retrieval.context import build_context, diff_only_context
from app.scanners.base import ScanRequest
from app.scanners.registry import run_scanners
from app.services import audit, detection, events
from app.services import workspace as workspace_service
from app.services.dedupe import merge_findings
from app.services.duplication import detect_duplicate_logic
from app.services.repositories import get_or_create_settings
from app.services.scoring import rank_findings
from app.validation.pipeline import ValidationPipeline

logger = get_logger(__name__)

MAX_PATCHES_PER_ANALYSIS = 12
MAX_FILES_TO_PARSE = 1200

# Marks an analysis as a whole-repository scan rather than a pull-request review.
REPOSITORY_SCAN_TRIGGER = "repository_scan"


@dataclass
class PipelineResult:
    analysis_id: str
    findings: list[UnifiedFinding] = field(default_factory=list)
    patches_created: int = 0
    patches_validated: int = 0
    error: str | None = None


class AnalysisPipeline:
    def __init__(self, session: Session, analysis: Analysis) -> None:
        self.session = session
        self.analysis = analysis
        self.pull_request: PullRequest = session.get(PullRequest, analysis.pull_request_id)
        self.repository: Repository = session.get(Repository, self.pull_request.repository_id)
        self.settings_row = get_or_create_settings(session, self.repository)
        self.workspace: workspace_service.Workspace | None = None
        self.usage = UsageTracker(
            budget_usd=min(self.settings_row.max_analysis_cost, settings.max_analysis_cost_usd)
        )
        self.graph: KnowledgeGraph | None = None
        self._stage_started = time.perf_counter()

    @property
    def is_full_scan(self) -> bool:
        """A whole-repository scan rather than a review of one pull request.

        Every downstream stage keys off ``context.changes``, so a scan simply
        declares the entire tree as changed instead of a diff.
        """
        return self.analysis.triggered_by == REPOSITORY_SCAN_TRIGGER

    # ---- progress --------------------------------------------------------
    def _stage(self, stage: AnalysisStage, message: str, **extra) -> None:
        elapsed = time.perf_counter() - self._stage_started
        self._stage_started = time.perf_counter()
        timings = dict(self.analysis.stage_timings or {})
        timings[self.analysis.stage] = round(elapsed, 3)

        self.analysis.stage = stage.value
        self.analysis.progress = stage.progress
        self.analysis.stage_timings = timings
        self.session.add(self.analysis)
        self.session.commit()

        events.publish(
            self.analysis.id,
            "progress",
            {"stage": stage.value, "progress": stage.progress, "message": message, **extra},
        )
        logger.info("pipeline.stage", analysis_id=self.analysis.id, stage=stage.value, message=message)

    # ---- entry point -----------------------------------------------------
    async def run(self) -> PipelineResult:
        result = PipelineResult(analysis_id=self.analysis.id)
        self.analysis.status = AnalysisStatus.RUNNING
        self.analysis.started_at = utcnow()
        self.session.add(self.analysis)
        self.session.commit()

        started_message = (
            f"Scanning {self.repository.full_name}"
            if self.is_full_scan
            else f"Analysing PR #{self.pull_request.github_pr_number}"
        )
        events.publish(
            self.analysis.id,
            "started",
            {"stage": AnalysisStage.QUEUED.value, "progress": 0, "message": started_message},
        )

        try:
            context = await self._prepare_context()
            deterministic = self._run_deterministic(context)
            ai_findings = await self._run_reviewers(context, deterministic)

            self._stage(AnalysisStage.MERGING, "Merging and ranking findings")
            all_findings = merge_findings(deterministic + ai_findings)
            all_findings = self._apply_threshold(rank_findings(all_findings, context))
            all_findings = self._add_impact_findings(context, all_findings)
            result.findings = all_findings

            stored = self._persist_findings(all_findings)
            events.publish(
                self.analysis.id,
                "findings",
                {"count": len(stored), "by_severity": _severity_counts(all_findings)},
            )

            patches, validated = await self._generate_and_validate(context, stored)
            result.patches_created = patches
            result.patches_validated = validated

            self._stage(AnalysisStage.PERSISTING, "Finalising report")
            self._complete(all_findings)
            events.publish(
                self.analysis.id,
                "completed",
                {
                    "stage": AnalysisStage.DONE.value,
                    "progress": 100,
                    "findings": len(all_findings),
                    "patches": patches,
                    "estimated_cost": round(self.usage.cost, 4),
                },
            )
        except Exception as exc:
            logger.exception("pipeline.failed", analysis_id=self.analysis.id)
            result.error = str(exc)
            self._fail(str(exc))
            events.publish(self.analysis.id, "failed", {"error": str(exc)[:500], "progress": 100})
        finally:
            if self.workspace is not None:
                self.workspace.cleanup()
        return result

    # ---- stage 1-6: context ---------------------------------------------
    async def _prepare_context(self) -> AnalysisContext:
        self._stage(AnalysisStage.CLONING, "Cloning repository into an isolated workspace")

        installation = self.session.get(GitHubInstallation, self.repository.installation_id)
        token = ""
        if installation is not None:
            try:
                token = await github_service.resolve_token(self.session, installation)
            except Exception as exc:
                logger.info("pipeline.no_github_token", reason=str(exc))

        self.workspace = workspace_service.create_workspace(
            self.analysis.id, self.repository.full_name
        )
        clone_url = self.repository.clone_url or f"https://github.com/{self.repository.full_name}.git"
        workspace_service.clone_pull_request(
            self.workspace,
            clone_url,
            token=token,
            base_sha=self.pull_request.base_sha,
            head_sha=self.pull_request.head_sha,
            head_ref=self.pull_request.head_ref,
        )

        if self.is_full_scan:
            self._stage(AnalysisStage.DIFFING, "Scanning the whole repository")
            changes = []
        else:
            self._stage(AnalysisStage.DIFFING, "Computing changed files and diffs")
            changes = await self._collect_changes(token)

        self._stage(AnalysisStage.DETECTING, "Detecting languages and frameworks")
        excluded = list(self.settings_row.excluded_paths or [])
        files: dict[str, SourceFile] = {}
        for source_file in workspace_service.iter_source_files(
            self.workspace, excluded_paths=excluded, max_files=MAX_FILES_TO_PARSE
        ):
            files[source_file.path] = source_file

        if self.is_full_scan:
            # No diff exists, so every analysable file counts as in scope. This
            # has to happen after enumeration, which is what knows the tree.
            changes = [
                FileChange(path=path, status="modified", patch="", changed_lines=set())
                for path in files
            ]

        languages = detection.detect_languages(files.values())
        dependencies = detection.read_dependencies(self.workspace.root)
        frameworks = detection.detect_frameworks(dependencies, set(files))

        context = AnalysisContext(
            analysis_id=self.analysis.id,
            repository_full_name=self.repository.full_name,
            workspace_path=str(self.workspace.root),
            base_sha=self.pull_request.base_sha,
            head_sha=self.pull_request.head_sha,
            pr_title=self.pull_request.title,
            pr_body=self.pull_request.body or "",
            changes=changes,
            files=files,
            languages=languages,
            frameworks=frameworks,
            dependencies=dependencies,
            excluded_paths=excluded,
            settings={"severity_threshold": self.settings_row.severity_threshold.value},
        )

        self._stage(
            AnalysisStage.PARSING,
            f"Parsing {len(files)} files with AST analyzers",
            languages=list(languages)[:6],
        )
        self._parse_repository(context)

        self._stage(AnalysisStage.GRAPHING, "Building the repository knowledge graph")
        self.graph = build_graph(
            files.values(),
            context.symbols,
            context.imports,
            context.calls,
            changed_paths=set(context.changed_paths),
            dependencies=dependencies,
        )
        self.analysis.graph_snapshot = self.graph.to_payload()

        self._stage(AnalysisStage.RETRIEVING, "Selecting the most relevant repository context")
        bundle = build_context(context, self.graph)
        self._bundle = bundle
        self.analysis.context_manifest = bundle.manifest
        self.analysis.files_analyzed = len(files)
        self.session.add(self.analysis)
        self.session.commit()
        return context

    async def _collect_changes(self, token: str) -> list[FileChange]:
        """Prefer the GitHub file list; fall back to local git diff."""
        if token and self.pull_request.github_pr_number:
            try:
                return await github_service.fetch_pull_request_changes(
                    token,
                    self.repository.owner,
                    self.repository.name,
                    self.pull_request.github_pr_number,
                )
            except Exception as exc:
                logger.info("pipeline.github_diff_failed", error=str(exc))

        assert self.workspace is not None
        changes: list[FileChange] = []
        for status, path in workspace_service.diff_name_status(
            self.workspace, self.pull_request.base_sha, self.pull_request.head_sha
        ):
            patch = workspace_service.unified_diff(
                self.workspace, self.pull_request.base_sha, self.pull_request.head_sha, path
            )
            from app.domain.types import changed_lines_from_patch

            changes.append(
                FileChange(
                    path=path,
                    status={"A": "added", "M": "modified", "D": "removed", "R": "renamed"}.get(status, "modified"),
                    patch=patch,
                    changed_lines=changed_lines_from_patch(patch),
                )
            )
        return changes

    def _parse_repository(self, context: AnalysisContext) -> None:
        """Parse every analyzable file, collecting symbols, imports and calls."""
        for path, source_file in context.files.items():
            analyzer = analyzer_for_path(path)
            if analyzer is None:
                continue
            parse = analyzer.parse(source_file.content, path)
            if not parse.ok and parse.tree is None:
                continue
            symbols = analyzer.extract_symbols(parse)
            context.symbols.extend(symbols)
            context.imports.extend(analyzer.extract_imports(parse))
            context.calls.extend(analyzer.extract_calls(parse, symbols))

    # ---- stage 7: deterministic analysis --------------------------------
    def _run_deterministic(self, context: AnalysisContext) -> list[UnifiedFinding]:
        assert self.workspace is not None
        self._stage(AnalysisStage.SCANNING, "Running deterministic scanners and AST rules")

        findings: list[UnifiedFinding] = []

        # 7a. AST rules — always available, no external tooling required.
        changed_lookup = {c.path: c for c in context.changes}
        for source_file in context.changed_source_files():
            analyzer = analyzer_for_path(source_file.path)
            if analyzer is None:
                continue
            parse = analyzer.parse(source_file.content, source_file.path)
            change = changed_lookup.get(source_file.path)
            analyzer_context = AnalyzerContext(
                file=source_file,
                parse=parse,
                symbols=[s for s in context.symbols if s.file_path == source_file.path],
                imports=[i for i in context.imports if i.file_path == source_file.path],
                calls=[c for c in context.calls if c.file_path == source_file.path],
                changed_lines=change.changed_lines if change else set(),
                dependencies=context.dependencies,
                frameworks=context.frameworks,
                all_paths=list(context.files),
            )
            try:
                findings.extend(analyzer.detect_issues(analyzer_context))
            except Exception as exc:
                logger.warning("pipeline.ast_rules_failed", path=source_file.path, error=str(exc))

        # 7b. Cross-file duplicate logic (structural, not textual).
        try:
            findings.extend(detect_duplicate_logic(context))
        except Exception as exc:
            logger.warning("pipeline.duplication_failed", error=str(exc))

        # 7c. External scanners.
        request = ScanRequest(
            workspace_root=self.workspace.root,
            target_files=[p for p in context.changed_paths if (self.workspace.root / p).is_file()],
            all_files=list(context.files),
            languages=context.languages,
            excluded_paths=context.excluded_paths,
            timeout=settings.scanner_timeout_seconds,
        )
        ran: list[str] = []

        def _on_result(scan_result) -> None:
            if scan_result.ran:
                ran.append(scan_result.scanner)
            events.publish(
                self.analysis.id,
                "scanner",
                {
                    "scanner": scan_result.scanner,
                    "ran": scan_result.ran,
                    "findings": len(scan_result.findings),
                    "skipped_reason": scan_result.skipped_reason,
                },
            )

        results = run_scanners(
            request,
            enabled=list(self.settings_row.enabled_scanners or []),
            families=detection.language_families(context.languages),
            custom_rules=list(self.settings_row.custom_rules or []),
            on_result=_on_result,
        )
        for scan_result in results:
            findings.extend(scan_result.findings)

        self.analysis.scanners_run = sorted(set([*ran, "ast_rules"]))
        self.session.add(self.analysis)
        self.session.commit()
        logger.info("pipeline.deterministic_complete", findings=len(findings), scanners=ran)
        return findings

    # ---- stage 8: AI review ---------------------------------------------
    async def _run_reviewers(
        self, context: AnalysisContext, deterministic: list[UnifiedFinding]
    ) -> list[UnifiedFinding]:
        enabled = list(self.settings_row.enabled_reviewers or [])
        agents = [REVIEWER_AGENTS[name] for name in enabled if name in REVIEWER_AGENTS]
        if not agents:
            return []

        self._stage(
            AnalysisStage.REVIEWING,
            f"Running {len(agents)} AI reviewers",
            reviewers=[a.name for a in agents],
        )

        provider = get_provider(
            self.settings_row.preferred_llm_provider, self.settings_row.preferred_llm_model
        )
        self.analysis.model_provider = provider.name
        self.analysis.model_name = provider.model
        self.session.add(self.analysis)
        self.session.commit()

        bundle = getattr(self, "_bundle", None) or diff_only_context(context.changes)
        summary = _summarise_for_prompt(deterministic)

        findings: list[UnifiedFinding] = []
        ran: list[str] = []

        # Agents run concurrently but cannot invoke one another — the orchestrator
        # is the only thing that sequences work, which bounds cost and latency.
        outcomes: list[ReviewOutcome] = await asyncio.gather(
            *[
                agent.run(
                    provider=provider,
                    context=context,
                    bundle=bundle,
                    deterministic_summary=summary,
                    usage=self.usage,
                )
                for agent in agents
            ],
            return_exceptions=False,
        )

        for outcome in outcomes:
            events.publish(
                self.analysis.id,
                "reviewer",
                {
                    "reviewer": outcome.agent,
                    "ran": outcome.ran,
                    "findings": len(outcome.findings),
                    "skipped_reason": outcome.skipped_reason,
                },
            )
            if outcome.ran:
                ran.append(outcome.agent)
                findings.extend(outcome.findings)

        self.analysis.reviewers_run = ran
        self._record_usage()
        return findings

    # ---- impact / breaking-change findings ------------------------------
    def _add_impact_findings(
        self, context: AnalysisContext, findings: list[UnifiedFinding]
    ) -> list[UnifiedFinding]:
        """Graph-derived findings: circular imports and unverified blast radius."""
        if self.graph is None:
            return findings

        for cycle in self.graph.circular_imports()[:3]:
            if not any(path in context.changed_paths for path in cycle):
                continue
            entry = cycle[0]
            findings.append(
                UnifiedFinding(
                    title="Circular import cycle involving changed files",
                    description=(
                        "These modules import each other in a cycle: "
                        + " → ".join([*cycle, cycle[0]])
                        + ". Cycles make import order significant, break isolated testing, and "
                        "produce partially-initialised modules at runtime."
                    ),
                    category=FindingCategory.ARCHITECTURE,
                    severity=Severity.MEDIUM,
                    file_path=entry,
                    start_line=1,
                    end_line=1,
                    source=FindingSource.GRAPH,
                    rule_id="graph.circular-import",
                    confidence=0.9,
                    risk="Import-order-dependent failures that appear only in certain entry points.",
                    recommendation=(
                        "Extract the shared types into a leaf module both sides import, or invert "
                        "one dependency behind an interface."
                    ),
                    related_files=cycle[1:],
                )
            )

        # High-fan-in changed files with no covering tests.
        for path in context.changed_paths:
            dependents = self.graph.dependents_of(path)
            if len(dependents) < 3:
                continue
            if self.graph.tests_covering(path):
                continue
            findings.append(
                UnifiedFinding(
                    title=f"High-impact file changed without test coverage ({len(dependents)} dependents)",
                    description=(
                        f"`{path}` is imported by {len(dependents)} other modules but no test file in "
                        "the repository imports it. A regression here propagates to every consumer "
                        "with nothing to catch it."
                    ),
                    category=FindingCategory.TESTING,
                    severity=Severity.MEDIUM if len(dependents) < 8 else Severity.HIGH,
                    file_path=path,
                    start_line=1,
                    end_line=1,
                    source=FindingSource.GRAPH,
                    rule_id="graph.untested-high-impact",
                    confidence=0.8,
                    risk=f"A defect reaches {len(dependents)} dependent modules undetected.",
                    recommendation="Add tests for the changed behaviour before merging.",
                    related_files=dependents[:8],
                )
            )
        return rank_findings(findings, context)

    def _apply_threshold(self, findings: list[UnifiedFinding]) -> list[UnifiedFinding]:
        allowed = Severity.at_least(self.settings_row.severity_threshold)
        return [f for f in findings if f.severity in allowed]

    # ---- persistence -----------------------------------------------------
    def _persist_findings(self, findings: list[UnifiedFinding]) -> list[Finding]:
        stored: list[Finding] = []
        seen: set[str] = set()
        for finding in findings:
            fingerprint = finding.fingerprint
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            row = Finding(
                analysis_id=self.analysis.id,
                category=finding.category,
                severity=finding.severity,
                confidence=finding.confidence,
                score=finding.score,
                title=finding.title,
                description=finding.description,
                risk=finding.risk,
                recommendation=finding.recommendation,
                file_path=finding.file_path,
                start_line=finding.start_line,
                end_line=finding.end_line,
                code_snippet=finding.code_snippet[:4000],
                source=finding.source,
                corroborating_sources=finding.corroborating_sources,
                rule_id=finding.rule_id,
                cwe=finding.cwe,
                fingerprint=fingerprint,
                related_files=finding.related_files,
                score_breakdown=finding.score_breakdown,
            )
            self.session.add(row)
            stored.append(row)
        self.session.commit()
        for row in stored:
            self.session.refresh(row)
        return stored

    # ---- stages 10-11: patches ------------------------------------------
    async def _generate_and_validate(
        self, context: AnalysisContext, stored: list[Finding]
    ) -> tuple[int, int]:
        assert self.workspace is not None
        self._stage(AnalysisStage.PATCHING, "Generating fixes for actionable findings")

        provider = get_provider(
            self.settings_row.preferred_llm_provider, self.settings_row.preferred_llm_model
        )
        generator = FixGenerator(provider)
        by_fingerprint = {f.fingerprint: f for f in context_findings(stored)}

        candidates = [
            row for row in stored
            if row.severity.rank >= Severity.LOW.rank and row.file_path in context.files
        ][:MAX_PATCHES_PER_ANALYSIS]

        pipeline = ValidationPipeline(self.workspace.root, all_files=list(context.files))
        created = 0
        validated = 0

        for row in candidates:
            source_file = context.files.get(row.file_path)
            if source_file is None:
                continue
            finding = by_fingerprint.get(row.fingerprint)
            if finding is None:
                continue

            outcome = await generator.generate(finding, source_file, self.usage)
            if outcome.proposal is None:
                continue

            patch = Patch(
                finding_id=row.id,
                file_path=outcome.proposal.file_path,
                original_code=outcome.proposal.original_code,
                suggested_code=outcome.proposal.suggested_code,
                unified_diff=outcome.proposal.unified_diff,
                explanation=outcome.proposal.explanation,
                expected_impact=outcome.proposal.expected_impact,
                side_effects=outcome.proposal.side_effects,
                risk_level=outcome.proposal.risk_level,
                generated_by=outcome.generated_by,
                status=PatchStatus.VALIDATING,
            )
            self.session.add(patch)
            row.status = FindingStatus.FIX_PROPOSED
            self.session.add(row)
            self.session.commit()
            self.session.refresh(patch)
            created += 1

            events.publish(
                self.analysis.id,
                "patch",
                {"patch_id": patch.id, "finding_id": row.id, "file": patch.file_path,
                 "generated_by": outcome.generated_by},
            )

            self._stage(AnalysisStage.VALIDATING, f"Validating fix for {row.file_path}")
            result = pipeline.validate(outcome.proposal, finding)

            patch.confidence = result.confidence
            patch.confidence_breakdown = result.confidence_breakdown
            patch.risk_level = result.risk_level
            patch.validation_status = result.status
            patch.auto_apply_eligible = (
                result.auto_apply_eligible and self.settings_row.auto_apply_enabled
            )
            patch.status = (
                PatchStatus.VALIDATED
                if result.status is ValidationStatus.PASSED
                else PatchStatus.VALIDATION_FAILED
            )
            self.session.add(patch)

            self.session.add(
                ValidationRun(
                    patch_id=patch.id,
                    parser_passed=result.signals.syntax_validation,
                    lint_passed=result.signals.lint_success,
                    typecheck_passed=result.signals.typecheck_success,
                    tests_passed=result.signals.test_success,
                    security_scan_passed=result.signals.security_scan_success,
                    semantic_similarity=result.signals.semantic_similarity,
                    tests_before=result.tests_before,
                    tests_after=result.tests_after,
                    step_results=result.step_dicts(),
                    test_output=result.test_output,
                    skipped_reason=result.skipped_reason,
                    execution_time=result.execution_time,
                )
            )
            self.session.commit()
            if result.status is ValidationStatus.PASSED:
                validated += 1

        self._record_usage()
        return created, validated

    # ---- completion ------------------------------------------------------
    def _record_usage(self) -> None:
        snapshot = self.usage.snapshot()
        self.analysis.prompt_tokens = int(snapshot["prompt_tokens"])
        self.analysis.completion_tokens = int(snapshot["completion_tokens"])
        self.analysis.token_usage = int(snapshot["total_tokens"])
        self.analysis.estimated_cost = float(snapshot["estimated_cost"])
        self.session.add(self.analysis)
        self.session.commit()

    def _complete(self, findings: list[UnifiedFinding]) -> None:
        self.analysis.status = AnalysisStatus.COMPLETED
        self.analysis.stage = AnalysisStage.DONE.value
        self.analysis.progress = 100
        self.analysis.completed_at = utcnow()
        if self.analysis.started_at:
            started = self.analysis.started_at
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            self.analysis.duration_seconds = round(
                (datetime.now(timezone.utc) - started).total_seconds(), 2
            )
        self.analysis.summary = _build_summary(findings, self.repository.full_name, self.pull_request)
        self._record_usage()

        self.repository.last_analyzed_at = utcnow()
        self.session.add(self.repository)
        self.session.commit()

        audit.record(
            self.session,
            action="analysis.completed",
            entity_type="analysis",
            entity_id=self.analysis.id,
            metadata={
                "findings": len(findings),
                "target": f"{self.repository.full_name}#{self.pull_request.github_pr_number}",
                "cost": round(self.usage.cost, 4),
            },
        )

    def _fail(self, message: str) -> None:
        self.analysis.status = AnalysisStatus.FAILED
        self.analysis.error_message = message[:2000]
        self.analysis.completed_at = utcnow()
        self.analysis.progress = 100
        self.session.add(self.analysis)
        self.session.commit()
        audit.record(
            self.session,
            action="analysis.failed",
            entity_type="analysis",
            entity_id=self.analysis.id,
            metadata={"error": message[:200]},
        )


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def context_findings(stored: list[Finding]) -> list[UnifiedFinding]:
    """Rebuild in-memory domain findings from persisted rows, for patch generation."""
    rebuilt: list[UnifiedFinding] = []
    for row in stored:
        rebuilt.append(
            UnifiedFinding(
                title=row.title,
                description=row.description,
                category=row.category,
                severity=row.severity,
                file_path=row.file_path,
                start_line=row.start_line,
                end_line=row.end_line,
                source=row.source,
                rule_id=row.rule_id or "",
                cwe=row.cwe,
                risk=row.risk,
                recommendation=row.recommendation,
                code_snippet=row.code_snippet,
                confidence=row.confidence,
                score=row.score,
                related_files=list(row.related_files or []),
                corroborating_sources=list(row.corroborating_sources or []),
            )
        )
    return rebuilt


def _severity_counts(findings: list[UnifiedFinding]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding.severity.value] = counts.get(finding.severity.value, 0) + 1
    return counts


def _summarise_for_prompt(findings: list[UnifiedFinding], limit: int = 25) -> str:
    if not findings:
        return ""
    lines = [
        f"- [{f.severity.value}] {f.file_path}:{f.start_line} {f.rule_id or f.title} ({f.source.value})"
        for f in sorted(findings, key=lambda f: f.severity.rank, reverse=True)[:limit]
    ]
    if len(findings) > limit:
        lines.append(f"- ...and {len(findings) - limit} more")
    return "\n".join(lines)


def _build_summary(findings: list[UnifiedFinding], repository: str, pr: PullRequest) -> str:
    counts = _severity_counts(findings)
    critical = counts.get("critical", 0)
    high = counts.get("high", 0)

    if critical:
        verdict = f"**Do not merge** — {critical} critical issue(s) require a fix first."
    elif high:
        verdict = f"**Changes requested** — {high} high-severity issue(s) should be resolved."
    elif findings:
        verdict = "**Safe to merge with nits** — no critical or high-severity issues found."
    else:
        verdict = "**No issues found** by the configured reviewers and scanners."

    # A repository scan has no pull-request number to cite.
    heading = (
        f"## RepoMedic repository scan — {repository}"
        if not pr.github_pr_number
        else f"## RepoMedic review — {repository}#{pr.github_pr_number}"
    )
    lines = [
        heading,
        "",
        verdict,
        "",
        "| Severity | Count |",
        "| --- | --- |",
    ]
    for severity in Severity:
        lines.append(f"| {severity.value.title()} | {counts.get(severity.value, 0)} |")

    top = [f for f in findings if f.severity.rank >= Severity.HIGH.rank][:8]
    if top:
        lines += ["", "### Must fix", ""]
        lines += [
            f"- **{f.severity.value.upper()}** `{f.file_path}:{f.start_line}` — {f.title}"
            for f in top
        ]
    return "\n".join(lines)


def create_analysis(session: Session, pull_request: PullRequest, *, triggered_by: str = "manual") -> Analysis:
    """Create a queued analysis row."""
    analysis = Analysis(
        pull_request_id=pull_request.id,
        status=AnalysisStatus.QUEUED,
        stage=AnalysisStage.QUEUED.value,
        triggered_by=triggered_by,
    )
    session.add(analysis)
    session.commit()
    session.refresh(analysis)
    return analysis


def latest_analysis(session: Session, pull_request_id: str) -> Analysis | None:
    return session.exec(
        select(Analysis)
        .where(Analysis.pull_request_id == pull_request_id)
        .order_by(Analysis.created_at.desc())
    ).first()
