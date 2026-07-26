"""JavaScript / TypeScript defect rules.

Structural checks run over the tree-sitter AST. When the grammar is unavailable
the same rules run over a lexical view of the file and every finding is issued
with reduced confidence and an explicit note.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.analyzers.base import AnalyzerContext
from app.analyzers.treesitter import node_text, walk
from app.domain.types import UnifiedFinding
from app.models.enums import FindingCategory, FindingSource, Severity

DEGRADED_NOTE = (
    "\n\n_Detected without a full AST (tree-sitter grammar unavailable on this host), "
    "so confidence is reduced._"
)

_SQL_KEYWORDS = ("select ", "insert ", "update ", "delete ", "from ", "where ")
_DB_EXECUTORS = ("query", "execute", "raw", "$queryRawUnsafe", "run", "exec", "all")
_AWAITABLE_DB = ("findmany", "findone", "findunique", "findfirst", "query", "execute", "aggregate", "count", "fetch")


@dataclass(slots=True)
class _Hit:
    line: int
    end_line: int
    text: str


class JavaScriptRuleEngine:
    def __init__(self, context: AnalyzerContext, *, degraded: bool = False) -> None:
        self.context = context
        self.degraded = degraded
        self.source = context.file.content
        self.lines = self.source.splitlines()
        self.findings: list[UnifiedFinding] = []
        self._tree = context.parse.tree
        self._bytes = self.source.encode("utf-8")

    # ---- entry point -----------------------------------------------------
    def run(self) -> list[UnifiedFinding]:
        self._check_sql_injection()
        self._check_dangerous_eval()
        self._check_dangerous_html()
        self._check_command_injection()
        self._check_floating_promises()
        self._check_await_in_loop()
        self._check_weak_jwt_verification()
        self._check_missing_error_handling()
        self._check_hardcoded_comparison_auth()
        self._check_react_effect_dependencies()
        self._check_unbounded_response()
        return self.findings

    # ---- emission --------------------------------------------------------
    def _emit(
        self,
        hit: _Hit,
        *,
        title: str,
        description: str,
        category: FindingCategory,
        severity: Severity,
        rule_id: str,
        risk: str,
        recommendation: str,
        cwe: str | None = None,
        confidence: float = 0.0,
    ) -> None:
        if not self.context.touches_changed_lines(hit.line, hit.end_line):
            return
        if self.degraded:
            confidence = max(0.0, confidence - 0.2)
            description = description + DEGRADED_NOTE
        self.findings.append(
            UnifiedFinding(
                title=title,
                description=description,
                category=category,
                severity=severity,
                file_path=self.context.file.path,
                start_line=hit.line,
                end_line=hit.end_line,
                source=FindingSource.AST_RULES,
                rule_id=rule_id,
                cwe=cwe,
                risk=risk,
                recommendation=recommendation,
                confidence=confidence,
                code_snippet=self.context.file.excerpt(hit.line, hit.end_line),
                metadata={"degraded_parse": self.degraded},
            )
        )

    # ---- traversal helpers ----------------------------------------------
    def _calls(self) -> list[tuple[str, Any, _Hit]]:
        """`(callee_text, node, hit)` for every call expression."""
        results: list[tuple[str, Any, _Hit]] = []
        if self._tree is not None:
            for node in walk(self._tree.root_node):
                if node.type != "call_expression":
                    continue
                function_node = node.child_by_field_name("function")
                callee = node_text(function_node, self._bytes) if function_node else ""
                results.append(
                    (
                        callee,
                        node,
                        _Hit(node.start_point[0] + 1, node.end_point[0] + 1,
                             node_text(node, self._bytes)),
                    )
                )
            return results

        # Lexical fallback: one entry per `name(` occurrence.
        for match in re.finditer(r"([A-Za-z_$][\w$.]*)\s*\(", self.source):
            line = self.source[: match.start()].count("\n") + 1
            results.append((match.group(1), None, _Hit(line, line, self.lines[line - 1] if line <= len(self.lines) else "")))
        return results

    def _lines_matching(self, pattern: re.Pattern[str]) -> list[_Hit]:
        hits: list[_Hit] = []
        for index, line in enumerate(self.lines, start=1):
            if pattern.search(line):
                hits.append(_Hit(index, index, line.strip()))
        return hits

    # ---- rules -----------------------------------------------------------
    def _check_sql_injection(self) -> None:
        for callee, _node, hit in self._calls():
            tail = callee.rsplit(".", 1)[-1]
            if tail not in _DB_EXECUTORS:
                continue
            argument = hit.text[hit.text.find("(") :] if "(" in hit.text else hit.text
            lowered = argument.lower()
            if not any(keyword in lowered for keyword in _SQL_KEYWORDS):
                continue
            interpolated = "${" in argument or re.search(r"['\"]\s*\+\s*\w", argument)
            if not interpolated:
                continue
            self._emit(
                hit,
                title="SQL injection: query built from a template literal",
                description=(
                    f"`{callee}()` receives SQL assembled with interpolation (`${{...}}` or `+`). "
                    "Values placed there are parsed as SQL, so a caller-controlled value rewrites "
                    "the statement."
                ),
                category=FindingCategory.SECURITY,
                severity=Severity.CRITICAL,
                rule_id="js.sql-injection",
                cwe="CWE-89",
                confidence=0.85,
                risk="Database read/write access and authentication bypass.",
                recommendation=(
                    "Use parameterised queries — `db.query('... WHERE id = $1', [id])`, Prisma's "
                    "`$queryRaw` tagged template, or the ORM's query builder."
                ),
            )

    def _check_dangerous_eval(self) -> None:
        pattern = re.compile(r"\b(eval|new\s+Function|setTimeout\s*\(\s*['\"`])")
        for hit in self._lines_matching(pattern):
            if hit.text.lstrip().startswith(("//", "*")):
                continue
            self._emit(
                hit,
                title="Dynamic code execution (`eval` / `new Function`)",
                description=(
                    "This line compiles a string into executable code. Any influence over that "
                    "string — a query parameter, a stored value, a config field — becomes code "
                    "execution in the runtime."
                ),
                category=FindingCategory.SECURITY,
                severity=Severity.HIGH,
                rule_id="js.dynamic-code-execution",
                cwe="CWE-95",
                confidence=0.8,
                risk="Remote code execution in Node, or full XSS in the browser.",
                recommendation="Use `JSON.parse` for data and a lookup table for dynamic dispatch.",
            )

    def _check_dangerous_html(self) -> None:
        pattern = re.compile(r"(dangerouslySetInnerHTML|\.innerHTML\s*=|document\.write\s*\()")
        for hit in self._lines_matching(pattern):
            if "sanitize" in hit.text.lower() or "dompurify" in hit.text.lower():
                continue
            self._emit(
                hit,
                title="Cross-site scripting: unsanitised HTML injection",
                description=(
                    "Assigning raw HTML bypasses React's escaping and the browser's own protections. "
                    "If any part of the value originates from user input or an API response, the "
                    "attacker's `<script>`/`onerror` payload executes with the victim's session."
                ),
                category=FindingCategory.SECURITY,
                severity=Severity.HIGH,
                rule_id="js.xss-inner-html",
                cwe="CWE-79",
                confidence=0.8,
                risk="Session theft, account takeover and arbitrary actions as the victim.",
                recommendation=(
                    "Render the value as text, or sanitise it with DOMPurify before injecting HTML."
                ),
            )

    def _check_command_injection(self) -> None:
        pattern = re.compile(r"\b(exec|execSync|spawnSync?)\s*\(")
        for hit in self._lines_matching(pattern):
            if "${" not in hit.text and "+" not in hit.text:
                continue
            self._emit(
                hit,
                title="Command injection: shell command built from interpolation",
                description=(
                    "`child_process.exec` runs its argument through a shell. Interpolating a value "
                    "lets `; rm -rf /` or `$(curl attacker)` execute as a separate command."
                ),
                category=FindingCategory.SECURITY,
                severity=Severity.CRITICAL,
                rule_id="js.command-injection",
                cwe="CWE-78",
                confidence=0.85,
                risk="Arbitrary command execution on the server.",
                recommendation="Use `execFile`/`spawn` with an argument array and never a shell string.",
            )

    def _check_floating_promises(self) -> None:
        """Async work started but never awaited — errors vanish, ordering breaks."""
        for callee, node, hit in self._calls():
            tail = callee.rsplit(".", 1)[-1].lower()
            if tail not in _AWAITABLE_DB and tail not in ("fetch", "save", "update", "delete", "create"):
                continue
            line_text = self.lines[hit.line - 1] if hit.line <= len(self.lines) else ""
            if "await" in line_text or "return" in line_text or ".then" in line_text or "catch" in line_text:
                continue
            if node is not None and node.parent is not None and node.parent.type in (
                "await_expression", "return_statement", "member_expression", "arguments",
                "variable_declarator", "assignment_expression", "binary_expression",
            ):
                continue
            if not line_text.strip().startswith(callee.split(".")[0]):
                continue
            self._emit(
                hit,
                title=f"Floating promise: `{callee}()` is never awaited",
                description=(
                    "The returned promise is discarded. The operation may not have completed when the "
                    "response is sent, and a rejection becomes an unhandled rejection that can crash "
                    "the Node process rather than surfacing as an error."
                ),
                category=FindingCategory.RELIABILITY,
                severity=Severity.MEDIUM,
                rule_id="js.floating-promise",
                confidence=0.6,
                risk="Silent data loss and unhandled promise rejections in production.",
                recommendation="`await` the call, or attach `.catch()` and document the fire-and-forget intent.",
            )

    def _check_await_in_loop(self) -> None:
        for index, line in enumerate(self.lines, start=1):
            if "await" not in line:
                continue
            context_window = self.lines[max(0, index - 6) : index]
            if not any(re.search(r"\b(for|while)\s*\(|\.forEach\(|\.map\(", prior) for prior in context_window):
                continue
            if not any(hint in line.lower() for hint in _AWAITABLE_DB):
                continue
            self._emit(
                _Hit(index, index, line.strip()),
                title="Sequential awaits inside a loop (N+1 pattern)",
                description=(
                    "Each iteration awaits its own round trip, so total latency is N × per-call "
                    "latency. With 100 items and a 20 ms query this endpoint takes two seconds."
                ),
                category=FindingCategory.PERFORMANCE,
                severity=Severity.MEDIUM,
                rule_id="js.await-in-loop",
                confidence=0.65,
                risk="Latency grows linearly with collection size.",
                recommendation=(
                    "Batch into a single `WHERE id IN (...)` query, or run concurrently with "
                    "`await Promise.all(items.map(...))` when the calls are independent."
                ),
            )
            return

    def _check_weak_jwt_verification(self) -> None:
        pattern = re.compile(r"jwt\.(verify|decode)\s*\(")
        for hit in self._lines_matching(pattern):
            window = "\n".join(self.lines[hit.line - 1 : hit.line + 3])
            if ".decode(" in hit.text:
                self._emit(
                    hit,
                    title="JWT decoded without signature verification",
                    description=(
                        "`jwt.decode()` parses the token without checking its signature. Any client "
                        "can forge claims — including `role: \"admin\"` — by base64-encoding their own payload."
                    ),
                    category=FindingCategory.SECURITY,
                    severity=Severity.CRITICAL,
                    rule_id="js.jwt-unverified",
                    cwe="CWE-347",
                    confidence=0.9,
                    risk="Complete authentication bypass and privilege escalation.",
                    recommendation="Use `jwt.verify(token, secret, { algorithms: ['HS256'] })`.",
                )
            elif "algorithms" not in window:
                self._emit(
                    hit,
                    title="JWT verification without an algorithm allowlist",
                    description=(
                        "`jwt.verify()` is called without `algorithms`. Historically this permitted "
                        "`alg: none` and HMAC/RSA confusion attacks where a public key is used as an "
                        "HMAC secret."
                    ),
                    category=FindingCategory.SECURITY,
                    severity=Severity.HIGH,
                    rule_id="js.jwt-missing-algorithms",
                    cwe="CWE-347",
                    confidence=0.75,
                    risk="Token forgery through algorithm confusion.",
                    recommendation="Pass an explicit `{ algorithms: ['HS256'] }` allowlist.",
                )

    def _check_missing_error_handling(self) -> None:
        pattern = re.compile(r"^\s*catch\s*\([^)]*\)\s*\{\s*\}\s*$")
        for hit in self._lines_matching(pattern):
            self._emit(
                hit,
                title="Empty catch block swallows the error",
                description=(
                    "The caught error is discarded with no logging and no rethrow. Failures become "
                    "invisible: the caller sees success and the incident has no trace to debug from."
                ),
                category=FindingCategory.RELIABILITY,
                severity=Severity.MEDIUM,
                rule_id="js.empty-catch",
                cwe="CWE-390",
                confidence=0.9,
                risk="Silent failures and unexplainable production incidents.",
                recommendation="Log the error with context and rethrow or return a typed failure.",
            )

    def _check_hardcoded_comparison_auth(self) -> None:
        pattern = re.compile(
            r"""(?i)\b(password|token|secret|api[_-]?key|apikey)\b\s*(===?|!==?)\s*['"][^'"]{4,}['"]"""
        )
        for hit in self._lines_matching(pattern):
            self._emit(
                hit,
                title="Credential compared against a hardcoded literal",
                description=(
                    "An authentication decision compares a secret with a literal embedded in source. "
                    "The value ships to every environment and every clone, and `===` on strings is "
                    "not constant-time, leaking length and prefix through timing."
                ),
                category=FindingCategory.SECURITY,
                severity=Severity.HIGH,
                rule_id="js.hardcoded-credential-comparison",
                cwe="CWE-798",
                confidence=0.85,
                risk="Anyone with source access authenticates as a privileged user.",
                recommendation=(
                    "Load the expected value from configuration and compare with "
                    "`crypto.timingSafeEqual`, or verify a hash with bcrypt/argon2."
                ),
            )

    def _check_react_effect_dependencies(self) -> None:
        if not self.context.file.path.endswith((".jsx", ".tsx")):
            return
        for index, line in enumerate(self.lines, start=1):
            if "useEffect(" not in line:
                continue
            window = "\n".join(self.lines[index - 1 : index + 12])
            if re.search(r"\}\s*\)\s*;?\s*$", window.splitlines()[-1] if window else "") and "[" not in window:
                self._emit(
                    _Hit(index, index, line.strip()),
                    title="`useEffect` without a dependency array",
                    description=(
                        "An effect with no dependency array runs after *every* render. If it sets "
                        "state or fetches, it re-triggers itself — an infinite render loop that "
                        "hammers the API."
                    ),
                    category=FindingCategory.PERFORMANCE,
                    severity=Severity.MEDIUM,
                    rule_id="js.useeffect-missing-deps",
                    confidence=0.6,
                    risk="Runaway re-renders and duplicated network requests.",
                    recommendation="Add a dependency array listing every value the effect reads.",
                )

    def _check_unbounded_response(self) -> None:
        pattern = re.compile(r"\.(findMany|find)\s*\(\s*\)|\.find\(\s*\{\s*\}\s*\)")
        for hit in self._lines_matching(pattern):
            self._emit(
                hit,
                title="Unbounded collection query",
                description=(
                    "This query has no `take`/`limit`/`skip`, so it returns the entire collection. "
                    "The response size and memory footprint grow with production data."
                ),
                category=FindingCategory.PERFORMANCE,
                severity=Severity.MEDIUM,
                rule_id="js.unbounded-query",
                confidence=0.6,
                risk="Slow responses and memory pressure as the table grows.",
                recommendation="Add `take`/`limit` with a capped page size and return a cursor.",
            )
