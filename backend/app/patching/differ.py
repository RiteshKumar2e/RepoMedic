"""Unified diffs and safe patch application.

Application is *AST-aware*: the analyzer for the file's language performs the
replacement and then re-parses the result. A patch that does not parse is
rejected before it ever reaches validation, let alone a branch.
"""

from __future__ import annotations

import difflib

from app.analyzers.registry import analyzer_for_path
from app.core.logging import get_logger
from app.domain.types import PatchProposal

logger = get_logger(__name__)


def make_unified_diff(
    original: str, updated: str, file_path: str, *, context_lines: int = 3
) -> str:
    diff = difflib.unified_diff(
        original.splitlines(keepends=True),
        updated.splitlines(keepends=True),
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
        n=context_lines,
    )
    return "".join(diff)


def changed_line_count(unified_diff: str) -> int:
    return sum(
        1
        for line in unified_diff.splitlines()
        if (line.startswith("+") and not line.startswith("+++"))
        or (line.startswith("-") and not line.startswith("---"))
    )


def apply_proposal(source: str, proposal: PatchProposal) -> tuple[str | None, str]:
    """Apply a proposal to source text.

    Returns ``(updated_source, error)``. ``updated_source`` is ``None`` when the
    patch could not be applied safely; ``error`` then explains why.
    """
    analyzer = analyzer_for_path(proposal.file_path)
    if analyzer is None:
        # Unsupported language: exact, unambiguous text replacement only.
        original = proposal.original_code.strip("\n")
        if not original or source.count(original) != 1:
            return None, "Cannot locate the original snippet unambiguously"
        return source.replace(original, proposal.suggested_code.strip("\n")), ""

    updated = analyzer.apply_patch(source, proposal)
    if updated is None:
        return None, (
            "The original snippet does not match the current file contents — "
            "the file changed since the patch was proposed"
        )
    if updated == source:
        return None, "Patch is a no-op"

    ok, error = analyzer.validate_syntax(updated)
    if not ok:
        return None, f"Patched file does not parse: {error}"
    return updated, ""


def normalise_indentation(original: str, suggested: str) -> str:
    """Re-indent a suggestion to match the block it replaces.

    Models routinely return correct code at the wrong indentation level; in
    Python that is the difference between a valid patch and a SyntaxError.
    """
    original_lines = [line for line in original.splitlines() if line.strip()]
    suggested_lines = [line for line in suggested.splitlines() if line.strip()]
    if not original_lines or not suggested_lines:
        return suggested

    original_indent = len(original_lines[0]) - len(original_lines[0].lstrip())
    suggested_indent = len(suggested_lines[0]) - len(suggested_lines[0].lstrip())
    delta = original_indent - suggested_indent
    if delta == 0:
        return suggested

    output: list[str] = []
    for line in suggested.splitlines():
        if not line.strip():
            output.append(line)
        elif delta > 0:
            output.append(" " * delta + line)
        else:
            strippable = min(-delta, len(line) - len(line.lstrip()))
            output.append(line[strippable:])
    return "\n".join(output)


def build_proposal(
    *,
    file_path: str,
    source: str,
    start_line: int,
    end_line: int,
    suggested_code: str,
    explanation: str,
    expected_impact: str = "",
    side_effects: list[str] | None = None,
    generated_by: str = "fix_generator",
) -> PatchProposal | None:
    """Construct a proposal from a line range, computing the diff."""
    lines = source.splitlines()
    if not (1 <= start_line <= end_line <= len(lines)):
        return None

    original_code = "\n".join(lines[start_line - 1 : end_line])
    suggested_code = normalise_indentation(original_code, suggested_code)
    if original_code.strip() == suggested_code.strip():
        return None

    updated = "\n".join(lines[: start_line - 1] + suggested_code.splitlines() + lines[end_line:])
    if source.endswith("\n"):
        updated += "\n"

    return PatchProposal(
        file_path=file_path,
        original_code=original_code,
        suggested_code=suggested_code,
        unified_diff=make_unified_diff(source, updated, file_path),
        explanation=explanation,
        expected_impact=expected_impact,
        side_effects=side_effects or [],
        start_line=start_line,
        end_line=end_line,
        generated_by=generated_by,
    )
