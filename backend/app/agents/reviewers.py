"""Specialised reviewer agents.

Each agent is a single, bounded LLM call: one prompt in, a validated finding list
out. Agents cannot call each other and cannot loop — the orchestrator owns
sequencing, budgets and retries. That is what keeps cost and latency predictable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.agents.prompts import REVIEWER_PROMPTS, review_user_message
from app.core.logging import get_logger
from app.domain.types import AnalysisContext, UnifiedFinding
from app.llm.base import ChatMessage, LLMProvider, LLMResponse, LLMUnavailable, UsageTracker
from app.models.enums import FindingCategory, ReviewerAgent, Severity
from app.retrieval.context import ContextBundle

logger = get_logger(__name__)

MAX_FINDINGS_PER_AGENT = 12
MAX_OUTPUT_TOKENS = 4096


@dataclass(slots=True)
class ReviewOutcome:
    agent: str
    findings: list[UnifiedFinding] = field(default_factory=list)
    ran: bool = True
    skipped_reason: str = ""
    response: LLMResponse | None = None
    error: str = ""


class ReviewAgent:
    """One reviewer specialty."""

    def __init__(self, agent: ReviewerAgent) -> None:
        self.agent = agent
        self.name = agent.value
        self.system_prompt = REVIEWER_PROMPTS[agent.value]

    async def run(
        self,
        *,
        provider: LLMProvider,
        context: AnalysisContext,
        bundle: ContextBundle,
        deterministic_summary: str,
        usage: UsageTracker,
    ) -> ReviewOutcome:
        if usage.exhausted:
            return ReviewOutcome(
                self.name, ran=False,
                skipped_reason=f"cost budget of ${usage.budget_usd:.2f} exhausted",
            )
        if not bundle.diff_sections:
            return ReviewOutcome(self.name, ran=False, skipped_reason="no reviewable changes")

        message = review_user_message(
            repository=context.repository_full_name,
            pr_title=context.pr_title,
            pr_body=context.pr_body,
            languages=", ".join(context.languages),
            frameworks=", ".join(context.frameworks),
            context_block=bundle.render(),
            deterministic_summary=deterministic_summary,
        )

        try:
            response = await provider.complete(
                system=self.system_prompt,
                messages=[ChatMessage(role="user", content=message)],
                max_tokens=MAX_OUTPUT_TOKENS,
                temperature=0.0,
            )
        except LLMUnavailable as exc:
            logger.warning("reviewer.llm_unavailable", agent=self.name, error=str(exc))
            return ReviewOutcome(self.name, ran=False, skipped_reason=str(exc), error=str(exc))
        except Exception as exc:  # network hiccup, malformed upstream, etc.
            logger.warning("reviewer.failed", agent=self.name, error=str(exc))
            return ReviewOutcome(self.name, ran=False, skipped_reason=f"agent error: {exc}", error=str(exc))

        usage.record(response)
        findings = self._parse(response, context)
        logger.info(
            "reviewer.completed",
            agent=self.name,
            findings=len(findings),
            tokens=response.total_tokens,
            provider=response.provider,
        )
        return ReviewOutcome(self.name, findings=findings, response=response)

    # ---- parsing ---------------------------------------------------------
    def _parse(self, response: LLMResponse, context: AnalysisContext) -> list[UnifiedFinding]:
        payload = response.json_payload()
        if isinstance(payload, dict):
            raw_findings = payload.get("findings", [])
        elif isinstance(payload, list):
            raw_findings = payload
        else:
            logger.warning("reviewer.unparsable_output", agent=self.name)
            return []

        valid_paths = set(context.files) | set(context.changed_paths)
        findings: list[UnifiedFinding] = []

        for raw in raw_findings[:MAX_FINDINGS_PER_AGENT]:
            if not isinstance(raw, dict):
                continue
            finding = self._coerce(raw, context, valid_paths, response)
            if finding is not None:
                findings.append(finding)
        return findings

    def _coerce(
        self,
        raw: dict,
        context: AnalysisContext,
        valid_paths: set[str],
        response: LLMResponse,
    ) -> UnifiedFinding | None:
        title = str(raw.get("title", "")).strip()
        file_path = str(raw.get("file_path", "")).strip().lstrip("./")
        if not title or not file_path:
            return None

        # Reject hallucinated files — a finding must point at real code.
        if file_path not in valid_paths:
            match = next((p for p in valid_paths if p.endswith(file_path) or file_path.endswith(p)), None)
            if match is None:
                logger.info("reviewer.dropped_unknown_path", agent=self.name, path=file_path)
                return None
            file_path = match

        source_file = context.files.get(file_path)
        max_line = len(source_file.lines) if source_file else 10_000
        start = _clamp(raw.get("start_line", 1), 1, max_line)
        end = _clamp(raw.get("end_line", start), start, max_line)

        try:
            severity = Severity(str(raw.get("severity", "medium")).lower())
        except ValueError:
            severity = Severity.MEDIUM
        try:
            category = FindingCategory(str(raw.get("category", "code_quality")).lower())
        except ValueError:
            category = _default_category(self.agent)

        confidence = raw.get("confidence", 0.6)
        try:
            confidence = max(0.0, min(1.0, float(confidence)))
        except (TypeError, ValueError):
            confidence = 0.6
        if response.provider == "heuristic":
            # Deterministic offline reviewer — label it honestly.
            confidence = min(confidence, 0.7)

        related = [str(p) for p in (raw.get("related_files") or []) if isinstance(p, str)][:8]

        return UnifiedFinding(
            title=title[:200],
            description=str(raw.get("description", ""))[:4000],
            category=category,
            severity=severity,
            file_path=file_path,
            start_line=start,
            end_line=end,
            source=self.agent.source,
            rule_id=str(raw.get("rule_id", f"{self.name}.finding"))[:80],
            cwe=(str(raw["cwe"])[:20] if raw.get("cwe") else None),
            risk=str(raw.get("risk", ""))[:1000],
            recommendation=str(raw.get("recommendation", ""))[:2000],
            confidence=confidence,
            related_files=related,
            code_snippet=source_file.excerpt(start, end) if source_file else "",
            metadata={
                "agent": self.name,
                "provider": response.provider,
                "model": response.model,
            },
        )


def _clamp(value: object, low: int, high: int) -> int:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return low
    return max(low, min(number, high))


def _default_category(agent: ReviewerAgent) -> FindingCategory:
    return {
        ReviewerAgent.ARCHITECTURE: FindingCategory.ARCHITECTURE,
        ReviewerAgent.SECURITY: FindingCategory.SECURITY,
        ReviewerAgent.PERFORMANCE: FindingCategory.PERFORMANCE,
        ReviewerAgent.RELIABILITY: FindingCategory.RELIABILITY,
        ReviewerAgent.TESTING: FindingCategory.TESTING,
    }[agent]


REVIEWER_AGENTS: dict[str, ReviewAgent] = {
    agent.value: ReviewAgent(agent) for agent in ReviewerAgent
}
