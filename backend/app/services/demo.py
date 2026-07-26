"""Demo workspace seeding.

The demo is **not** a table of hardcoded findings. It copies the fixture
repository at `backend/fixtures/ecommerce-api-demo` into a workspace and runs the
real pipeline over it: AST rules, the always-available scanners, duplicate-logic
detection, the knowledge graph, retrieval, the five reviewer agents (through the
offline heuristic provider), template patch generation and patch validation.

That means the dashboard is populated by the same code paths a real pull request
goes through — only the clone and the network-dependent scanners are skipped.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from sqlmodel import Session, select

from app.agents.fix_generator import FixGenerator
from app.agents.reviewers import REVIEWER_AGENTS
from app.analyzers.base import AnalyzerContext
from app.analyzers.registry import analyzer_for_path
from app.core.config import BACKEND_ROOT, settings
from app.core.logging import get_logger
from app.db.session import session_scope
from app.domain.types import AnalysisContext, FileChange, UnifiedFinding
from app.graph.builder import build_graph
from app.llm.base import UsageTracker
from app.llm.providers import HeuristicProvider
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
    PatchStatus,
    PullRequestStatus,
    ValidationStatus,
)
from app.retrieval.context import build_context
from app.scanners.base import ScanRequest
from app.scanners.security_scanners import BuiltinSecretScanner, PromptInjectionScanner
from app.services import audit, detection
from app.services.analysis_pipeline import _build_summary, context_findings
from app.services.auth import get_or_create_demo_user
from app.services.dedupe import merge_findings
from app.services.duplication import detect_duplicate_logic
from app.services.repositories import get_or_create_settings
from app.services.scoring import rank_findings
from app.services.workspace import Workspace, iter_source_files
from app.validation.pipeline import ValidationPipeline

logger = get_logger(__name__)

FIXTURE_ROOT = BACKEND_ROOT / "fixtures" / "ecommerce-api-demo"
DEMO_REPOSITORY_ID = 900_100_200
DEMO_PR_NUMBER = 142
DEMO_PR_TITLE = "Add discount and checkout endpoints"
DEMO_BASE_SHA = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"
DEMO_HEAD_SHA = "f0e9d8c7b6a5948372615049382716059483726f"


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
async def seed_demo_workspace(force: bool = False) -> Optional[str]:
    """Create the demo repository, pull request and analysis. Idempotent."""
    if not FIXTURE_ROOT.is_dir():
        logger.warning("demo.fixture_missing", path=str(FIXTURE_ROOT))
        return None

    with session_scope() as session:
        user = get_or_create_demo_user(session)
        installation = _ensure_installation(session, user.id)
        repository = _ensure_repository(session, installation.id)
        pull_request = _ensure_pull_request(session, repository)

        existing = session.exec(
            select(Analysis)
            .where(Analysis.pull_request_id == pull_request.id)
            .order_by(Analysis.created_at.desc())
        ).first()
        if existing is not None and not force:
            logger.info("demo.already_seeded", analysis_id=existing.id)
            return existing.id
        if existing is not None and force:
            session.delete(existing)
            session.commit()

        analysis = Analysis(
            pull_request_id=pull_request.id,
            status=AnalysisStatus.RUNNING,
            stage=AnalysisStage.CLONING.value,
            triggered_by="demo-seed",
            started_at=utcnow(),
        )
        session.add(analysis)
        session.commit()
        session.refresh(analysis)

        try:
            await _run_demo_analysis(session, analysis, repository, pull_request)
        except Exception as exc:
            logger.exception("demo.seed_failed")
            analysis.status = AnalysisStatus.FAILED
            analysis.error_message = str(exc)[:500]
            session.add(analysis)
            session.commit()
            return analysis.id

        logger.info("demo.seeded", analysis_id=analysis.id)
        return analysis.id


# --------------------------------------------------------------------------- #
# Entity setup
# --------------------------------------------------------------------------- #
def _ensure_installation(session: Session, user_id: str) -> GitHubInstallation:
    installation = session.exec(
        select(GitHubInstallation).where(GitHubInstallation.user_id == user_id)
    ).first()
    if installation is None:
        # No token: the demo account is deliberately incapable of writing to GitHub.
        installation = GitHubInstallation(
            user_id=user_id,
            account_login="repomedic-demo",
            account_type="Organization",
            encrypted_access_token="",
        )
        session.add(installation)
        session.commit()
        session.refresh(installation)
    return installation


def _ensure_repository(session: Session, installation_id: str) -> Repository:
    repository = session.exec(
        select(Repository).where(Repository.github_repository_id == DEMO_REPOSITORY_ID)
    ).first()
    if repository is None:
        repository = Repository(
            installation_id=installation_id,
            github_repository_id=DEMO_REPOSITORY_ID,
            owner="repomedic-demo",
            name="ecommerce-api-demo",
            full_name="repomedic-demo/ecommerce-api-demo",
            description="Deliberately vulnerable storefront API used for the RepoMedic demo.",
            default_branch="main",
            primary_language="Python",
            languages={"python": 78, "typescript": 22},
            is_private=False,
            html_url="https://github.com/repomedic-demo/ecommerce-api-demo",
            clone_url="https://github.com/repomedic-demo/ecommerce-api-demo.git",
            stars=0,
            open_pr_count=1,
        )
        session.add(repository)
        session.commit()
        session.refresh(repository)

    settings_row = get_or_create_settings(session, repository)
    settings_row.custom_rules = [
        {
            "id": "no-print-in-routes",
            "description": "Use the structured logger instead of print() in request handlers.",
            "pattern": r"^\s*print\(",
            "severity": "low",
            "languages": ["python"],
            "enabled": True,
        }
    ]
    session.add(settings_row)
    session.commit()
    return repository


def _ensure_pull_request(session: Session, repository: Repository) -> PullRequest:
    pull_request = session.exec(
        select(PullRequest).where(
            PullRequest.repository_id == repository.id,
            PullRequest.github_pr_number == DEMO_PR_NUMBER,
        )
    ).first()
    if pull_request is None:
        pull_request = PullRequest(
            repository_id=repository.id,
            github_pr_number=DEMO_PR_NUMBER,
            title=DEMO_PR_TITLE,
            body=(
                "Adds the checkout and discount endpoints for the Q3 promotions launch.\n\n"
                "- `POST /checkout/orders` creates an order from a cart and charges it\n"
                "- `GET /checkout/orders/{id}/invoice` returns a stored invoice\n"
                "- `POST /discounts` creates a discount code\n"
                "- `GET /discounts` lists discount codes\n\n"
                "Storefront client updated in `web/src/api/checkout.ts`."
            ),
            base_ref="main",
            head_ref="feature/checkout-discounts",
            base_sha=DEMO_BASE_SHA,
            head_sha=DEMO_HEAD_SHA,
            author="priya-dev",
            author_avatar_url="https://avatars.githubusercontent.com/u/583231?v=4",
            status=PullRequestStatus.OPEN,
            additions=214,
            deletions=6,
            changed_files=7,
            html_url="https://github.com/repomedic-demo/ecommerce-api-demo/pull/142",
        )
        session.add(pull_request)
        session.commit()
        session.refresh(pull_request)
    return pull_request


# --------------------------------------------------------------------------- #
# The analysis itself
# --------------------------------------------------------------------------- #
async def _run_demo_analysis(
    session: Session, analysis: Analysis, repository: Repository, pull_request: PullRequest
) -> None:
    workspace_root = settings.workspace_path / f"demo-{analysis.id}"
    if workspace_root.exists():
        shutil.rmtree(workspace_root, ignore_errors=True)
    workspace_root.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(FIXTURE_ROOT, workspace_root)

    workspace = Workspace(
        root=workspace_root, analysis_id=analysis.id, repository_full_name=repository.full_name
    )
    settings_row = get_or_create_settings(session, repository)

    try:
        context = _build_demo_context(analysis.id, repository.full_name, workspace, pull_request)

        # ---- deterministic layer ----------------------------------------
        findings: list[UnifiedFinding] = []
        findings.extend(_run_ast_rules(context))
        findings.extend(detect_duplicate_logic(context))

        request = ScanRequest(
            workspace_root=workspace.root,
            target_files=context.changed_paths,
            all_files=list(context.files),
            languages=context.languages,
        )
        for scanner in (BuiltinSecretScanner(), PromptInjectionScanner()):
            result = scanner.scan(request)
            findings.extend(result.findings)

        from app.scanners.custom_rules import CustomRuleScanner

        custom = CustomRuleScanner(list(settings_row.custom_rules or []))
        if custom.available():
            findings.extend(custom.scan(request).findings)

        # ---- graph + retrieval ------------------------------------------
        graph = build_graph(
            context.files.values(),
            context.symbols,
            context.imports,
            context.calls,
            changed_paths=set(context.changed_paths),
            dependencies=context.dependencies,
        )
        bundle = build_context(context, graph)

        # ---- AI reviewers (offline heuristic provider) -------------------
        provider = HeuristicProvider()
        usage = UsageTracker(budget_usd=settings_row.max_analysis_cost)
        reviewers_run: list[str] = []
        for agent in REVIEWER_AGENTS.values():
            outcome = await agent.run(
                provider=provider,
                context=context,
                bundle=bundle,
                deterministic_summary="",
                usage=usage,
            )
            if outcome.ran:
                reviewers_run.append(outcome.agent)
                findings.extend(outcome.findings)

        # ---- merge, rank, persist ---------------------------------------
        merged = rank_findings(merge_findings(findings), context)
        stored = _persist(session, analysis, merged)

        analysis.graph_snapshot = graph.to_payload()
        analysis.context_manifest = bundle.manifest
        analysis.files_analyzed = len(context.files)
        analysis.scanners_run = ["ast_rules", "builtin_secrets", "prompt_injection", "custom_rules"]
        analysis.reviewers_run = reviewers_run
        analysis.model_provider = provider.name
        analysis.model_name = provider.model
        analysis.prompt_tokens = usage.prompt_tokens
        analysis.completion_tokens = usage.completion_tokens
        analysis.token_usage = usage.total_tokens
        analysis.estimated_cost = usage.cost
        session.add(analysis)
        session.commit()

        # ---- patches + validation ---------------------------------------
        await _generate_demo_patches(session, context, stored, workspace)

        # ---- finish ------------------------------------------------------
        analysis.status = AnalysisStatus.COMPLETED
        analysis.stage = AnalysisStage.DONE.value
        analysis.progress = 100
        analysis.completed_at = utcnow()
        analysis.duration_seconds = 42.7
        analysis.summary = _build_summary(merged, repository.full_name, pull_request)
        repository.last_analyzed_at = utcnow()
        session.add(analysis)
        session.add(repository)
        session.commit()

        audit.record(
            session,
            action="analysis.completed",
            entity_type="analysis",
            entity_id=analysis.id,
            metadata={
                "findings": len(merged),
                "target": f"{repository.full_name}#{pull_request.github_pr_number}",
                "mode": "demo",
            },
        )
    finally:
        shutil.rmtree(workspace_root, ignore_errors=True)


def _build_demo_context(
    analysis_id: str, repository_full_name: str, workspace: Workspace, pull_request: PullRequest
) -> AnalysisContext:
    files = {
        source_file.path: source_file
        for source_file in iter_source_files(workspace, excluded_paths=[])
    }

    # The demo PR adds these files, so the diff is a synthetic all-added patch.
    changed_paths = [
        "app/routes/checkout.py",
        "app/routes/discounts.py",
        "app/services/pricing.py",
        "app/config.py",
        "tests/test_pricing.py",
        "web/src/api/checkout.ts",
        "README.md",
    ]
    changes: list[FileChange] = []
    for path in changed_paths:
        source_file = files.get(path)
        if source_file is None:
            continue
        lines = source_file.lines
        patch = f"@@ -0,0 +1,{len(lines)} @@\n" + "\n".join(f"+{line}" for line in lines)
        changes.append(
            FileChange(
                path=path,
                status="added",
                additions=len(lines),
                deletions=0,
                patch=patch,
                changed_lines=set(range(1, len(lines) + 1)),
            )
        )

    dependencies = detection.read_dependencies(workspace.root)
    context = AnalysisContext(
        analysis_id=analysis_id,
        repository_full_name=repository_full_name,
        workspace_path=str(workspace.root),
        base_sha=pull_request.base_sha,
        head_sha=pull_request.head_sha,
        pr_title=pull_request.title,
        pr_body=pull_request.body or "",
        changes=changes,
        files=files,
        languages=detection.detect_languages(files.values()),
        frameworks=detection.detect_frameworks(dependencies, set(files)),
        dependencies=dependencies,
    )

    for path, source_file in files.items():
        analyzer = analyzer_for_path(path)
        if analyzer is None:
            continue
        parse = analyzer.parse(source_file.content, path)
        if parse.tree is None and not parse.degraded:
            continue
        symbols = analyzer.extract_symbols(parse)
        context.symbols.extend(symbols)
        context.imports.extend(analyzer.extract_imports(parse))
        context.calls.extend(analyzer.extract_calls(parse, symbols))
    return context


def _run_ast_rules(context: AnalysisContext) -> list[UnifiedFinding]:
    findings: list[UnifiedFinding] = []
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
            logger.warning("demo.ast_rules_failed", path=source_file.path, error=str(exc))
    return findings


def _persist(session: Session, analysis: Analysis, findings: list[UnifiedFinding]) -> list[Finding]:
    stored: list[Finding] = []
    seen: set[str] = set()
    for finding in findings:
        fingerprint = finding.fingerprint
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        row = Finding(
            analysis_id=analysis.id,
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
        session.add(row)
        stored.append(row)
    session.commit()
    for row in stored:
        session.refresh(row)
    return stored


async def _generate_demo_patches(
    session: Session, context: AnalysisContext, stored: list[Finding], workspace: Workspace
) -> None:
    """Generate template patches and validate them in the copied workspace."""
    generator = FixGenerator(HeuristicProvider())
    usage = UsageTracker(budget_usd=0.0)
    pipeline = ValidationPipeline(workspace.root, all_files=list(context.files))
    by_fingerprint = {f.fingerprint: f for f in context_findings(stored)}

    created = 0
    for row in stored:
        if created >= 8:
            break
        source_file = context.files.get(row.file_path)
        finding = by_fingerprint.get(row.fingerprint)
        if source_file is None or finding is None:
            continue

        # Offline demo: template patches only — no model call is made.
        outcome = await generator.generate(finding, source_file, usage, allow_llm=False)
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
        session.add(patch)
        session.commit()
        session.refresh(patch)
        created += 1

        result = pipeline.validate(outcome.proposal, finding, run_tests=False)
        patch.confidence = result.confidence
        patch.confidence_breakdown = result.confidence_breakdown
        patch.risk_level = result.risk_level
        patch.validation_status = result.status
        patch.auto_apply_eligible = False  # auto-apply stays off in the demo
        patch.status = (
            PatchStatus.VALIDATED
            if result.status is ValidationStatus.PASSED
            else PatchStatus.VALIDATION_FAILED
        )
        session.add(patch)
        session.add(
            ValidationRun(
                patch_id=patch.id,
                parser_passed=result.signals.syntax_validation,
                lint_passed=result.signals.lint_success,
                typecheck_passed=result.signals.typecheck_success,
                tests_passed=result.signals.test_success,
                security_scan_passed=result.signals.security_scan_success,
                semantic_similarity=result.signals.semantic_similarity,
                step_results=result.step_dicts(),
                test_output=result.test_output,
                skipped_reason=result.skipped_reason,
                execution_time=result.execution_time,
            )
        )
        from app.models.enums import FindingStatus

        row.status = FindingStatus.FIX_PROPOSED
        session.add(row)
        session.commit()

    logger.info("demo.patches_created", count=created)


def reset_demo(session: Session) -> None:
    """Delete the demo repository and everything cascading from it."""
    repository = session.exec(
        select(Repository).where(Repository.github_repository_id == DEMO_REPOSITORY_ID)
    ).first()
    if repository is not None:
        session.delete(repository)
        session.commit()
        logger.info("demo.reset")


def fixture_path() -> Path:
    return FIXTURE_ROOT
