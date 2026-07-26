"""Duplicate-logic detection.

Compares the *normalised token stream* of every extracted function, so renamed
variables and reformatted whitespace still match. This catches copy-paste
validation logic and parallel implementations that text diffing misses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import combinations

from app.core.logging import get_logger
from app.domain.types import AnalysisContext, Symbol, SymbolKind, UnifiedFinding
from app.models.enums import FindingCategory, FindingSource, Severity

logger = get_logger(__name__)

MIN_LINES = 4
MIN_TOKENS = 18
SIMILARITY_THRESHOLD = 0.8
SHINGLE_SIZE = 3
MAX_COMPARISONS = 8000

_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+|[^\s\w]")
# Strings are collapsed before comments so a `#` inside a literal is not
# mistaken for a comment.
_STRING_RE = re.compile(
    r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'|"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'|`(?:[^`\\]|\\.)*`'
)
_COMMENT_RE = re.compile(r"#[^\n]*|//[^\n]*|/\*[\s\S]*?\*/")
# Identifier names are normalised away; keywords and operators are what matter.
_KEYWORDS = {
    "if", "else", "elif", "for", "while", "return", "def", "class", "try", "except",
    "finally", "with", "as", "import", "from", "and", "or", "not", "in", "is", "None",
    "True", "False", "raise", "yield", "await", "async", "lambda", "assert",
    "function", "const", "let", "var", "typeof", "instanceof", "new", "throw", "catch",
}


@dataclass(slots=True)
class _Block:
    symbol: Symbol
    shingles: set[str]
    line_count: int


def _normalise(source: str) -> list[str]:
    """Tokenise, replacing identifiers and literals with placeholders.

    Comments and docstrings are removed first: two copy-pasted functions are
    duplicates of each other whether or not somebody reworded the comment above
    them, and leaving prose in the token stream drowns out the structure.
    """
    source = _STRING_RE.sub(" __strlit__ ", source)
    source = _COMMENT_RE.sub(" ", source)

    tokens: list[str] = []
    for raw in _TOKEN_RE.findall(source):
        if raw in _KEYWORDS:
            tokens.append(raw)
        elif raw[0].isdigit():
            tokens.append("<num>")
        elif raw[0].isalpha() or raw[0] == "_":
            tokens.append("<id>")
        else:
            tokens.append(raw)
    return tokens


def _shingles(tokens: list[str]) -> set[str]:
    if len(tokens) < SHINGLE_SIZE:
        return set()
    return {" ".join(tokens[i : i + SHINGLE_SIZE]) for i in range(len(tokens) - SHINGLE_SIZE + 1)}


def _similarity(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def detect_duplicate_logic(context: AnalysisContext) -> list[UnifiedFinding]:
    """Find near-identical function bodies involving the changed files."""
    blocks: list[_Block] = []
    changed = set(context.changed_paths)

    for symbol in context.symbols:
        if symbol.kind not in (SymbolKind.FUNCTION, SymbolKind.METHOD, SymbolKind.ROUTE):
            continue
        source_file = context.files.get(symbol.file_path)
        if source_file is None:
            continue
        line_count = symbol.end_line - symbol.start_line + 1
        if line_count < MIN_LINES:
            continue
        body = "\n".join(source_file.lines[symbol.start_line - 1 : symbol.end_line])
        tokens = _normalise(body)
        if len(tokens) < MIN_TOKENS:
            continue
        blocks.append(_Block(symbol=symbol, shingles=_shingles(tokens), line_count=line_count))

    findings: list[UnifiedFinding] = []
    seen: set[tuple[str, str]] = set()
    comparisons = 0

    for left, right in combinations(blocks, 2):
        comparisons += 1
        if comparisons > MAX_COMPARISONS:
            break
        # At least one side must be part of this pull request.
        if left.symbol.file_path not in changed and right.symbol.file_path not in changed:
            continue
        if left.symbol.qualified_name == right.symbol.qualified_name:
            continue

        score = _similarity(left.shingles, right.shingles)
        if score < SIMILARITY_THRESHOLD:
            continue

        key = tuple(sorted([left.symbol.qualified_name, right.symbol.qualified_name]))
        if key in seen:
            continue
        seen.add(key)

        primary, secondary = (
            (left, right) if left.symbol.file_path in changed else (right, left)
        )
        same_file = primary.symbol.file_path == secondary.symbol.file_path
        findings.append(
            UnifiedFinding(
                title=(
                    f"Duplicate logic: `{primary.symbol.name}` and `{secondary.symbol.name}` "
                    f"are {score:.0%} identical"
                ),
                description=(
                    f"`{primary.symbol.name}` ({primary.symbol.file_path}:"
                    f"{primary.symbol.start_line}) and `{secondary.symbol.name}` "
                    f"({secondary.symbol.file_path}:{secondary.symbol.start_line}) share "
                    f"{score:.0%} of their normalised token structure across "
                    f"{min(primary.line_count, secondary.line_count)} lines. Duplicated rules "
                    "drift: a fix applied to one copy silently leaves the other wrong, which is "
                    "how validation bypasses appear."
                ),
                category=FindingCategory.CODE_QUALITY,
                severity=Severity.LOW if same_file else Severity.MEDIUM,
                file_path=primary.symbol.file_path,
                start_line=primary.symbol.start_line,
                end_line=primary.symbol.end_line,
                source=FindingSource.AST_RULES,
                rule_id="duplicate-logic",
                confidence=round(min(0.95, score), 3),
                risk=(
                    "The two copies diverge over time; a rule tightened in one path stays loose "
                    "in the other."
                ),
                recommendation=(
                    f"Extract the shared logic into one function and call it from both places — "
                    f"`{secondary.symbol.name}` already looks like the intended home."
                ),
                code_snippet=(context.files[primary.symbol.file_path].excerpt(
                    primary.symbol.start_line, min(primary.symbol.end_line, primary.symbol.start_line + 12)
                )),
                related_files=[secondary.symbol.file_path],
                metadata={
                    "similarity": round(score, 3),
                    "counterpart": secondary.symbol.qualified_name,
                },
            )
        )

    if findings:
        logger.info("duplication.detected", count=len(findings))
    return findings
