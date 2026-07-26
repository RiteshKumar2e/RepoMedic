"""Fix generation.

Strategy, in order:

1. **Template patch** — deterministic, zero-cost, highest prior confidence.
   Used whenever the defect has one mechanically correct repair.
2. **LLM patch** — for defects that need judgement. Strictly bounded: one call
   per finding, minimal context, structured output, and the result is only
   accepted if the quoted original matches the file byte-for-byte and the
   patched file parses.
3. **No patch** — architectural findings and anything requiring a product
   decision are reported without a suggested fix rather than guessed at.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.agents.prompts import FIX_GENERATOR, fix_user_message
from app.core.logging import get_logger
from app.domain.types import PatchProposal, SourceFile, UnifiedFinding
from app.llm.base import ChatMessage, LLMProvider, LLMUnavailable, UsageTracker
from app.models.enums import FindingCategory, RiskLevel
from app.patching.differ import build_proposal
from app.patching.templates import template_patch
from app.security.firewall import sanitize_for_llm

logger = get_logger(__name__)

EXCERPT_PADDING = 25
MAX_OUTPUT_TOKENS = 2048

# Categories where an automated patch is not appropriate.
NON_PATCHABLE_CATEGORIES = {FindingCategory.ARCHITECTURE, FindingCategory.BREAKING_CHANGE}


@dataclass(slots=True)
class FixOutcome:
    proposal: Optional[PatchProposal] = None
    generated_by: str = ""
    reason: str = ""


class FixGenerator:
    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    async def generate(
        self,
        finding: UnifiedFinding,
        source_file: SourceFile,
        usage: UsageTracker,
        *,
        allow_llm: bool = True,
    ) -> FixOutcome:
        # 1. Deterministic template.
        proposal = template_patch(finding, source_file.content)
        if proposal is not None:
            proposal.confidence = 0.9
            logger.info("fix.template_applied", rule=finding.rule_id, file=finding.file_path)
            return FixOutcome(proposal=proposal, generated_by="template")

        if finding.category in NON_PATCHABLE_CATEGORIES:
            return FixOutcome(
                reason=(
                    f"{finding.category.value.replace('_', ' ').title()} findings are reported "
                    "without an automated patch — the correct fix is a design decision."
                )
            )
        if not allow_llm:
            return FixOutcome(reason="patch generation disabled for this analysis")
        if usage.exhausted:
            return FixOutcome(reason=f"cost budget of ${usage.budget_usd:.2f} exhausted")

        # 2. LLM patch.
        return await self._generate_with_llm(finding, source_file, usage)

    async def _generate_with_llm(
        self, finding: UnifiedFinding, source_file: SourceFile, usage: UsageTracker
    ) -> FixOutcome:
        lines = source_file.lines
        start = max(1, finding.start_line - EXCERPT_PADDING)
        end = min(len(lines), finding.end_line + EXCERPT_PADDING)
        numbered = "\n".join(f"{n:>5} | {lines[n - 1]}" for n in range(start, end + 1))
        excerpt, _report = sanitize_for_llm(numbered, source_label=source_file.path)

        message = fix_user_message(
            finding_title=finding.title,
            finding_description=finding.description,
            finding_recommendation=finding.recommendation,
            file_path=finding.file_path,
            start_line=finding.start_line,
            end_line=finding.end_line,
            file_excerpt=excerpt,
            conventions=_describe_conventions(source_file),
        )

        try:
            response = await self.provider.complete(
                system=FIX_GENERATOR,
                messages=[ChatMessage(role="user", content=message)],
                max_tokens=MAX_OUTPUT_TOKENS,
                temperature=0.0,
            )
        except LLMUnavailable as exc:
            return FixOutcome(reason=str(exc))
        except Exception as exc:
            logger.warning("fix.generation_failed", error=str(exc), rule=finding.rule_id)
            return FixOutcome(reason=f"fix generator error: {exc}")

        usage.record(response)
        payload = response.json_payload()
        if not isinstance(payload, dict):
            return FixOutcome(reason="fix generator returned unparsable output")
        if payload.get("patchable") is False:
            return FixOutcome(reason=str(payload.get("reason", "not safely automatable"))[:400])

        suggested = payload.get("suggested_code")
        original = payload.get("original_code")
        if not isinstance(suggested, str) or not suggested.strip():
            return FixOutcome(reason="fix generator returned no replacement code")

        start_line, end_line = _resolve_range(payload, original, source_file, finding)
        if start_line is None or end_line is None:
            return FixOutcome(
                reason="the quoted original code does not match the file — patch rejected"
            )

        proposal = build_proposal(
            file_path=finding.file_path,
            source=source_file.content,
            start_line=start_line,
            end_line=end_line,
            suggested_code=suggested,
            explanation=str(payload.get("explanation", ""))[:2000],
            expected_impact=str(payload.get("expected_impact", ""))[:1000],
            side_effects=[str(s)[:300] for s in (payload.get("side_effects") or [])][:6],
            generated_by=f"llm:{response.provider}",
        )
        if proposal is None:
            return FixOutcome(reason="patch produced no change")

        try:
            proposal.risk_level = RiskLevel(str(payload.get("risk_level", "medium")).lower())
        except ValueError:
            proposal.risk_level = RiskLevel.MEDIUM
        proposal.confidence = 0.65
        return FixOutcome(proposal=proposal, generated_by=f"llm:{response.provider}")


def _resolve_range(
    payload: dict,
    original: object,
    source_file: SourceFile,
    finding: UnifiedFinding,
) -> tuple[Optional[int], Optional[int]]:
    """Locate the replacement range, trusting the quoted text over the line numbers."""
    lines = source_file.lines

    if isinstance(original, str) and original.strip():
        stripped = original.strip("\n")
        located = _find_block(lines, stripped)
        if located is not None:
            return located

    try:
        start = int(payload.get("start_line", finding.start_line))
        end = int(payload.get("end_line", finding.end_line))
    except (TypeError, ValueError):
        start, end = finding.start_line, finding.end_line

    start = max(1, min(start, len(lines)))
    end = max(start, min(end, len(lines)))

    # Without a verifiable quote, only accept the exact range the finding named.
    if isinstance(original, str) and original.strip():
        return None, None
    return start, end


def _find_block(lines: list[str], block: str) -> Optional[tuple[int, int]]:
    """Find a unique multi-line block, comparing on stripped content."""
    needle = [line.strip() for line in block.splitlines() if line.strip()]
    if not needle:
        return None

    matches: list[tuple[int, int]] = []
    for index in range(len(lines)):
        cursor = index
        matched: list[int] = []
        for wanted in needle:
            while cursor < len(lines) and not lines[cursor].strip():
                cursor += 1
            if cursor >= len(lines) or lines[cursor].strip() != wanted:
                break
            matched.append(cursor)
            cursor += 1
        else:
            matches.append((matched[0] + 1, matched[-1] + 1))
            if len(matches) > 1:
                return None  # ambiguous — refuse rather than guess
    return matches[0] if matches else None


def _describe_conventions(source_file: SourceFile) -> str:
    """Short description of the file's style so the patch blends in."""
    lines = source_file.lines[:400]
    indented = [line for line in lines if line.startswith((" ", "\t"))]
    uses_tabs = sum(1 for line in indented if line.startswith("\t")) > len(indented) / 2 if indented else False
    indent_width = 4
    for line in indented:
        if line.startswith(" "):
            width = len(line) - len(line.lstrip(" "))
            if width in (2, 4):
                indent_width = width
                break

    double_quotes = sum(line.count('"') for line in lines)
    single_quotes = sum(line.count("'") for line in lines)
    has_type_hints = any("->" in line or ": " in line for line in lines if line.strip().startswith("def "))
    semicolons = sum(1 for line in lines if line.rstrip().endswith(";"))

    parts = [
        "tabs" if uses_tabs else f"{indent_width}-space indentation",
        "double quotes" if double_quotes >= single_quotes else "single quotes",
    ]
    if source_file.language.value == "python" and has_type_hints:
        parts.append("type-hinted signatures")
    if semicolons > len(lines) / 4:
        parts.append("semicolon line endings")
    return ", ".join(parts)
