"""JavaScript / TypeScript analyzer.

Primary path is tree-sitter (real AST). When a grammar cannot be loaded the
analyzer degrades to a lexical parser, flags the result as ``degraded`` and the
scoring layer discounts every finding derived from it.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from app.analyzers.base import AnalyzerContext, ParseResult
from app.analyzers.javascript_rules import JavaScriptRuleEngine
from app.analyzers.treesitter import get_parser, node_text, walk
from app.core.logging import get_logger
from app.domain.types import (
    CallRef,
    ImportRef,
    Language,
    PatchProposal,
    Symbol,
    SymbolKind,
    UnifiedFinding,
)

logger = get_logger(__name__)

_FUNCTION_NODES = {
    "function_declaration", "function_expression", "generator_function_declaration",
    "arrow_function", "method_definition",
}
_CLASS_NODES = {"class_declaration", "class"}

# Lexical fallback patterns.
_LEX_FUNCTION = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:(async)\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)", re.M
)
_LEX_ARROW = re.compile(
    r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*(?::[^=]+)?=\s*(async\s+)?\(?[^)]*\)?\s*=>", re.M
)
_LEX_CLASS = re.compile(r"^\s*(?:export\s+)?(?:default\s+)?class\s+([A-Za-z_$][\w$]*)", re.M)
_LEX_IMPORT = re.compile(r"""^\s*import\s+(?:(.+?)\s+from\s+)?['"]([^'"]+)['"]""", re.M)
_LEX_REQUIRE = re.compile(r"""\brequire\(\s*['"]([^'"]+)['"]\s*\)""")
_LEX_ROUTE = re.compile(
    r"""\b(?:app|router|api|server)\.(get|post|put|patch|delete|use|all)\(\s*['"`]([^'"`]+)['"`]""",
)


class JavaScriptAnalyzer:
    """Serves .js/.jsx/.mjs/.cjs and, via the TypeScript grammar, .ts/.tsx."""

    language = Language.JAVASCRIPT
    extensions = (".js", ".jsx", ".mjs", ".cjs")
    grammar = "javascript"

    def parse(self, source_code: str, path: str = "") -> ParseResult:
        parser = get_parser(self.grammar)
        if parser is None:
            return ParseResult(
                path=path, language=self.language, tree=None, ok=True,
                degraded=True, source=source_code,
                error="tree-sitter grammar unavailable; using lexical fallback",
            )
        try:
            tree = parser.parse(source_code.encode("utf-8"))
        except Exception as exc:  # pragma: no cover - grammar crash
            return ParseResult(
                path=path, language=self.language, ok=True, degraded=True,
                source=source_code, error=f"tree-sitter parse failed: {exc}",
            )
        has_error = bool(getattr(tree.root_node, "has_error", False))
        return ParseResult(
            path=path,
            language=self.language,
            tree=tree,
            ok=not has_error,
            source=source_code,
            error="parse errors present" if has_error else "",
        )

    def validate_syntax(self, source_code: str) -> tuple[bool, str]:
        parser = get_parser(self.grammar)
        if parser is None:
            return _lexical_syntax_check(source_code)
        try:
            tree = parser.parse(source_code.encode("utf-8"))
        except Exception as exc:  # pragma: no cover
            return False, str(exc)
        if getattr(tree.root_node, "has_error", False):
            node = _first_error_node(tree.root_node)
            line = (node.start_point[0] + 1) if node else 1
            return False, f"Syntax error near line {line}"
        return True, ""

    # ---- structure -------------------------------------------------------
    def extract_symbols(self, tree: ParseResult) -> list[Symbol]:
        if tree.tree is None:
            return _lexical_symbols(tree)

        source = tree.source.encode("utf-8")
        symbols: list[Symbol] = []
        for node in walk(tree.tree.root_node):
            if node.type in _CLASS_NODES:
                name = _identifier(node, source)
                if name:
                    symbols.append(
                        _symbol(name, SymbolKind.CLASS, tree.path, node, f"class {name}")
                    )
            elif node.type in _FUNCTION_NODES:
                name = _function_name(node, source)
                if not name:
                    continue
                kind = SymbolKind.FUNCTION
                if node.type == "method_definition":
                    kind = SymbolKind.METHOD
                elif name[0].isupper() and tree.path.endswith((".jsx", ".tsx")):
                    kind = SymbolKind.COMPONENT
                symbols.append(
                    _symbol(
                        name, kind, tree.path, node,
                        signature=node_text(node, source).split("{", 1)[0].strip()[:160],
                        is_async="async" in node_text(node, source)[:24],
                        parent=_enclosing_class(node, source),
                    )
                )

        # Express-style route registrations become route symbols.
        for match in _LEX_ROUTE.finditer(tree.source):
            line = tree.source[: match.start()].count("\n") + 1
            symbols.append(
                Symbol(
                    name=f"{match.group(1).upper()} {match.group(2)}",
                    kind=SymbolKind.ROUTE,
                    file_path=tree.path,
                    start_line=line,
                    end_line=line,
                    metadata={"method": match.group(1).upper(), "path": match.group(2)},
                )
            )
        return symbols

    def extract_imports(self, tree: ParseResult) -> list[ImportRef]:
        imports: list[ImportRef] = []
        for match in _LEX_IMPORT.finditer(tree.source):
            names_blob = (match.group(1) or "").strip()
            names = [n.strip() for n in re.split(r"[{},]", names_blob) if n.strip()]
            imports.append(
                ImportRef(
                    module=match.group(2),
                    names=names,
                    file_path=tree.path,
                    line=tree.source[: match.start()].count("\n") + 1,
                    is_relative=match.group(2).startswith("."),
                )
            )
        for match in _LEX_REQUIRE.finditer(tree.source):
            imports.append(
                ImportRef(
                    module=match.group(1),
                    file_path=tree.path,
                    line=tree.source[: match.start()].count("\n") + 1,
                    is_relative=match.group(1).startswith("."),
                )
            )
        return imports

    def extract_calls(self, tree: ParseResult, symbols: list[Symbol]) -> list[CallRef]:
        if tree.tree is None:
            return []
        source = tree.source.encode("utf-8")
        scopes = sorted(
            [s for s in symbols if s.kind in (SymbolKind.FUNCTION, SymbolKind.METHOD, SymbolKind.COMPONENT)],
            key=lambda s: s.start_line,
        )
        calls: list[CallRef] = []
        for node in walk(tree.tree.root_node):
            if node.type != "call_expression":
                continue
            function_node = node.child_by_field_name("function")
            if function_node is None:
                continue
            callee = node_text(function_node, source).strip()
            if not callee or len(callee) > 120:
                continue
            line = node.start_point[0] + 1
            caller = next((s.name for s in reversed(scopes) if s.start_line <= line <= s.end_line), "<module>")
            calls.append(
                CallRef(
                    caller=caller,
                    callee=callee,
                    file_path=tree.path,
                    line=line,
                    is_awaited=(node.parent is not None and node.parent.type == "await_expression"),
                )
            )
        return calls

    # ---- rules -----------------------------------------------------------
    def detect_issues(self, context: AnalyzerContext) -> list[UnifiedFinding]:
        return JavaScriptRuleEngine(context, degraded=context.parse.degraded).run()

    # ---- patching --------------------------------------------------------
    def apply_patch(self, source_code: str, patch: PatchProposal) -> Optional[str]:
        original = patch.original_code.strip("\n")
        if not original:
            return None
        if source_code.count(original) == 1:
            return source_code.replace(original, patch.suggested_code.strip("\n"))
        lines = source_code.splitlines()
        start, end = patch.start_line, patch.end_line
        if not (1 <= start <= end <= len(lines)):
            return None
        if "\n".join(lines[start - 1 : end]).strip() != original.strip():
            return None
        return "\n".join(lines[: start - 1] + patch.suggested_code.strip("\n").splitlines() + lines[end:])


class TypeScriptAnalyzer(JavaScriptAnalyzer):
    """Same rule set, TypeScript grammar."""

    language = Language.TYPESCRIPT
    extensions = (".ts", ".mts", ".cts")
    grammar = "typescript"


class TSXAnalyzer(JavaScriptAnalyzer):
    language = Language.TSX
    extensions = (".tsx",)
    grammar = "tsx"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _symbol(
    name: str,
    kind: SymbolKind,
    path: str,
    node: Any,
    signature: str = "",
    is_async: bool = False,
    parent: Optional[str] = None,
) -> Symbol:
    return Symbol(
        name=name,
        kind=kind,
        file_path=path,
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        signature=signature,
        is_async=is_async,
        parent=parent,
    )


def _identifier(node: Any, source: bytes) -> str:
    for child in node.children:
        if child.type in ("identifier", "type_identifier", "property_identifier"):
            return node_text(child, source)
    return ""


def _function_name(node: Any, source: bytes) -> str:
    name_node = node.child_by_field_name("name")
    if name_node is not None:
        return node_text(name_node, source)
    if node.type == "arrow_function" and node.parent is not None:
        if node.parent.type == "variable_declarator":
            return _identifier(node.parent, source)
    return _identifier(node, source)


def _enclosing_class(node: Any, source: bytes) -> Optional[str]:
    current = node.parent
    while current is not None:
        if current.type in _CLASS_NODES:
            return _identifier(current, source) or None
        current = current.parent
    return None


def _first_error_node(node: Any) -> Optional[Any]:
    for child in walk(node):
        if child.type == "ERROR" or getattr(child, "is_missing", False):
            return child
    return None


def _lexical_symbols(tree: ParseResult) -> list[Symbol]:
    """Fallback symbol extraction when no grammar is available."""
    symbols: list[Symbol] = []
    lines = tree.source.splitlines()

    def line_of(offset: int) -> int:
        return tree.source[:offset].count("\n") + 1

    for match in _LEX_CLASS.finditer(tree.source):
        start = line_of(match.start())
        symbols.append(
            Symbol(match.group(1), SymbolKind.CLASS, tree.path, start,
                   _block_end(lines, start), signature=match.group(0).strip())
        )
    for match in _LEX_FUNCTION.finditer(tree.source):
        start = line_of(match.start())
        symbols.append(
            Symbol(match.group(2), SymbolKind.FUNCTION, tree.path, start,
                   _block_end(lines, start), signature=match.group(0).strip(),
                   is_async=bool(match.group(1)))
        )
    for match in _LEX_ARROW.finditer(tree.source):
        start = line_of(match.start())
        symbols.append(
            Symbol(match.group(1), SymbolKind.FUNCTION, tree.path, start,
                   _block_end(lines, start), signature=match.group(0).strip(),
                   is_async=bool(match.group(2)))
        )
    return symbols


def _block_end(lines: list[str], start_line: int, max_scan: int = 400) -> int:
    """Brace-match forward to approximate where a block ends."""
    depth = 0
    seen_open = False
    for index in range(start_line - 1, min(len(lines), start_line - 1 + max_scan)):
        for char in lines[index]:
            if char == "{":
                depth += 1
                seen_open = True
            elif char == "}":
                depth -= 1
        if seen_open and depth <= 0:
            return index + 1
    return min(len(lines), start_line + 20)


def _lexical_syntax_check(source_code: str) -> tuple[bool, str]:
    """Balanced-delimiter check — catches the truncation errors patches introduce."""
    pairs = {"{": "}", "(": ")", "[": "]"}
    stack: list[tuple[str, int]] = []
    line = 1
    in_string: Optional[str] = None
    escaped = False
    index = 0
    while index < len(source_code):
        char = source_code[index]
        if char == "\n":
            line += 1
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == in_string:
                in_string = None
        elif char in "'\"`":
            in_string = char
        elif char == "/" and index + 1 < len(source_code) and source_code[index + 1] == "/":
            newline = source_code.find("\n", index)
            index = len(source_code) if newline == -1 else newline
            continue
        elif char == "/" and index + 1 < len(source_code) and source_code[index + 1] == "*":
            close = source_code.find("*/", index)
            if close == -1:
                return False, f"Unterminated block comment starting on line {line}"
            line += source_code[index:close].count("\n")
            index = close + 2
            continue
        elif char in pairs:
            stack.append((char, line))
        elif char in pairs.values():
            if not stack or pairs[stack[-1][0]] != char:
                return False, f"Unbalanced `{char}` on line {line}"
            stack.pop()
        index += 1

    if in_string:
        return False, "Unterminated string literal"
    if stack:
        opener, opened_line = stack[-1]
        return False, f"Unclosed `{opener}` opened on line {opened_line}"
    return True, ""
