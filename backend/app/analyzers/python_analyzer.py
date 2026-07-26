"""Python analyzer built on the standard-library ``ast`` module.

``ast`` gives exact, version-accurate structure for Python — more precise than a
generic grammar — so it is preferred over tree-sitter for this language.
"""

from __future__ import annotations

import ast
from typing import Optional

from app.analyzers.base import AnalyzerContext, ParseResult
from app.analyzers.python_rules import PythonRuleVisitor
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

# Decorator names that mark an HTTP route across common frameworks.
ROUTE_DECORATORS = {"get", "post", "put", "patch", "delete", "route", "head", "options", "websocket"}
MODEL_BASES = {"Base", "Model", "SQLModel", "BaseModel", "db.Model", "declarative_base"}
TEST_PREFIXES = ("test_",)


class PythonAnalyzer:
    language = Language.PYTHON
    extensions = (".py", ".pyi")

    # ---- parsing ---------------------------------------------------------
    def parse(self, source_code: str, path: str = "") -> ParseResult:
        try:
            tree = ast.parse(source_code, filename=path or "<unknown>")
        except SyntaxError as exc:
            return ParseResult(
                path=path,
                language=self.language,
                ok=False,
                error=f"SyntaxError: {exc.msg} (line {exc.lineno})",
                source=source_code,
            )
        return ParseResult(path=path, language=self.language, tree=tree, source=source_code)

    def validate_syntax(self, source_code: str) -> tuple[bool, str]:
        try:
            ast.parse(source_code)
        except SyntaxError as exc:
            return False, f"SyntaxError: {exc.msg} (line {exc.lineno}, column {exc.offset})"
        return True, ""

    # ---- structure extraction -------------------------------------------
    def extract_symbols(self, tree: ParseResult) -> list[Symbol]:
        if not tree.ok or tree.tree is None:
            return []
        symbols: list[Symbol] = []
        module = tree.tree

        for node in module.body:
            self._collect(node, tree.path, parent=None, symbols=symbols)
        return symbols

    def _collect(
        self, node: ast.AST, path: str, parent: Optional[str], symbols: list[Symbol]
    ) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            decorators = [_decorator_name(d) for d in node.decorator_list]
            kind = SymbolKind.METHOD if parent else SymbolKind.FUNCTION
            if any(_is_route_decorator(d) for d in decorators):
                kind = SymbolKind.ROUTE
            elif node.name.startswith(TEST_PREFIXES):
                kind = SymbolKind.TEST
            symbols.append(
                Symbol(
                    name=node.name,
                    kind=kind,
                    file_path=path,
                    start_line=node.lineno,
                    end_line=getattr(node, "end_lineno", node.lineno) or node.lineno,
                    signature=_signature(node),
                    docstring=(ast.get_docstring(node) or "")[:400],
                    parent=parent,
                    decorators=decorators,
                    is_async=isinstance(node, ast.AsyncFunctionDef),
                    complexity=_cyclomatic(node),
                    metadata={"route": _route_metadata(decorators)} if kind is SymbolKind.ROUTE else {},
                )
            )
            for child in node.body:
                self._collect(child, path, parent=node.name, symbols=symbols)

        elif isinstance(node, ast.ClassDef):
            bases = [_decorator_name(b) for b in node.bases]
            kind = SymbolKind.MODEL if any(b.split(".")[-1] in MODEL_BASES for b in bases) else SymbolKind.CLASS
            symbols.append(
                Symbol(
                    name=node.name,
                    kind=kind,
                    file_path=path,
                    start_line=node.lineno,
                    end_line=getattr(node, "end_lineno", node.lineno) or node.lineno,
                    signature=f"class {node.name}({', '.join(bases)})",
                    docstring=(ast.get_docstring(node) or "")[:400],
                    parent=parent,
                    decorators=[_decorator_name(d) for d in node.decorator_list],
                    metadata={"bases": bases},
                )
            )
            for child in node.body:
                self._collect(child, path, parent=node.name, symbols=symbols)

        elif isinstance(node, ast.Assign) and parent is None:
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    symbols.append(
                        Symbol(
                            name=target.id,
                            kind=SymbolKind.CONSTANT,
                            file_path=path,
                            start_line=node.lineno,
                            end_line=getattr(node, "end_lineno", node.lineno) or node.lineno,
                            parent=parent,
                        )
                    )

    def extract_imports(self, tree: ParseResult) -> list[ImportRef]:
        if not tree.ok or tree.tree is None:
            return []
        imports: list[ImportRef] = []
        for node in ast.walk(tree.tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(
                        ImportRef(module=alias.name, names=[alias.asname or alias.name],
                                   file_path=tree.path, line=node.lineno)
                    )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                imports.append(
                    ImportRef(
                        module=("." * (node.level or 0)) + module,
                        names=[a.name for a in node.names],
                        file_path=tree.path,
                        line=node.lineno,
                        is_relative=bool(node.level),
                    )
                )
        return imports

    def extract_calls(self, tree: ParseResult, symbols: list[Symbol]) -> list[CallRef]:
        if not tree.ok or tree.tree is None:
            return []
        calls: list[CallRef] = []
        scopes = sorted(
            [s for s in symbols if s.kind in (SymbolKind.FUNCTION, SymbolKind.METHOD, SymbolKind.ROUTE, SymbolKind.TEST)],
            key=lambda s: s.start_line,
        )

        for node in ast.walk(tree.tree):
            if not isinstance(node, ast.Call):
                continue
            callee = _decorator_name(node.func)
            if not callee:
                continue
            caller = next(
                (s.name for s in reversed(scopes) if s.start_line <= node.lineno <= s.end_line),
                "<module>",
            )
            calls.append(
                CallRef(
                    caller=caller,
                    callee=callee,
                    file_path=tree.path,
                    line=node.lineno,
                    is_awaited=_is_awaited(node, tree.tree),
                )
            )
        return calls

    # ---- rules -----------------------------------------------------------
    def detect_issues(self, context: AnalyzerContext) -> list[UnifiedFinding]:
        if not context.parse.ok or context.parse.tree is None:
            return []
        visitor = PythonRuleVisitor(context)
        visitor.visit(context.parse.tree)
        return visitor.findings

    # ---- patching --------------------------------------------------------
    def apply_patch(self, source_code: str, patch: PatchProposal) -> Optional[str]:
        """Replace the original snippet with the suggestion, preserving indentation.

        Returns ``None`` when the original text cannot be located unambiguously —
        the caller then refuses the patch rather than guessing.
        """
        original = patch.original_code.strip("\n")
        if not original:
            return None
        if source_code.count(original) == 1:
            return source_code.replace(original, patch.suggested_code.strip("\n"))

        # Fall back to a line-range replacement when the text is not unique.
        lines = source_code.splitlines()
        start, end = patch.start_line, patch.end_line
        if not (1 <= start <= end <= len(lines)):
            return None
        target = "\n".join(lines[start - 1 : end])
        if target.strip() != original.strip():
            return None
        replacement = patch.suggested_code.strip("\n").splitlines()
        return "\n".join(lines[: start - 1] + replacement + lines[end:])


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _decorator_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_decorator_name(node.value)}.{node.attr}".lstrip(".")
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    if isinstance(node, ast.Subscript):
        return _decorator_name(node.value)
    if isinstance(node, ast.Constant):
        return str(node.value)
    return ""


def _is_route_decorator(decorator: str) -> bool:
    tail = decorator.rsplit(".", 1)[-1]
    return tail in ROUTE_DECORATORS and "." in decorator


def _route_metadata(decorators: list[str]) -> dict:
    for decorator in decorators:
        tail = decorator.rsplit(".", 1)[-1]
        if tail in ROUTE_DECORATORS:
            return {"method": tail.upper(), "decorator": decorator}
    return {}


def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    args = [a.arg for a in node.args.args]
    if node.args.vararg:
        args.append(f"*{node.args.vararg.arg}")
    if node.args.kwarg:
        args.append(f"**{node.args.kwarg.arg}")
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    return f"{prefix} {node.name}({', '.join(args)})"


def _cyclomatic(node: ast.AST) -> int:
    """Approximate cyclomatic complexity: one plus every branching construct."""
    complexity = 1
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler,
                              ast.With, ast.AsyncWith, ast.Assert, ast.IfExp)):
            complexity += 1
        elif isinstance(child, ast.BoolOp):
            complexity += len(child.values) - 1
        elif isinstance(child, ast.comprehension):
            complexity += 1 + len(child.ifs)
    return complexity


def _is_awaited(call: ast.Call, module: ast.AST) -> bool:
    for node in ast.walk(module):
        if isinstance(node, ast.Await) and node.value is call:
            return True
    return False
