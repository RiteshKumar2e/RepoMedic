"""AST-based Python defect rules.

These are structural checks, not text matching: each rule reasons about node
types, scope, loop nesting and async context. That is what lets RepoMedic say
"this database call is inside a loop inside a request handler" rather than
"this line contains the word `query`".
"""

from __future__ import annotations

import ast

from app.analyzers.base import AnalyzerContext
from app.domain.types import UnifiedFinding
from app.models.enums import FindingCategory, FindingSource, Severity

# ---- vocabulary ----------------------------------------------------------- #
SQL_EXECUTORS = {"execute", "executemany", "executescript", "raw", "text", "from_statement"}
SQL_KEYWORDS = ("select ", "insert ", "update ", "delete ", "drop ", "where ", "from ", "union ")

DB_CALLS = {
    "execute", "executemany", "query", "filter", "filter_by", "all", "first",
    "one", "one_or_none", "scalar", "scalars", "fetchall", "fetchone", "get",
    "find", "find_one", "aggregate", "exec", "count",
}
DB_OWNERS = ("session", "db", "cursor", "conn", "connection", "engine", "collection", "objects")

BLOCKING_CALLS = {
    "time.sleep": "time.sleep blocks the event loop for every concurrent request",
    "requests.get": "the `requests` library is synchronous",
    "requests.post": "the `requests` library is synchronous",
    "requests.put": "the `requests` library is synchronous",
    "requests.delete": "the `requests` library is synchronous",
    "requests.request": "the `requests` library is synchronous",
    "urllib.request.urlopen": "urlopen is synchronous",
    "subprocess.run": "subprocess.run blocks until the child exits",
    "subprocess.call": "subprocess.call blocks until the child exits",
    "subprocess.check_output": "subprocess.check_output blocks until the child exits",
    "os.system": "os.system blocks and is also command-injection prone",
}
ASYNC_ALTERNATIVES = {
    "time.sleep": "await asyncio.sleep(...)",
    "requests.get": "await httpx.AsyncClient().get(...)",
    "requests.post": "await httpx.AsyncClient().post(...)",
    "requests.put": "await httpx.AsyncClient().put(...)",
    "requests.delete": "await httpx.AsyncClient().delete(...)",
    "requests.request": "await httpx.AsyncClient().request(...)",
    "subprocess.run": "await asyncio.create_subprocess_exec(...)",
    "os.system": "await asyncio.create_subprocess_exec(...)",
}

DANGEROUS_CALLS = {
    "eval": ("CWE-95", "Arbitrary code execution via eval()"),
    "exec": ("CWE-95", "Arbitrary code execution via exec()"),
    "pickle.loads": ("CWE-502", "Unsafe deserialization with pickle"),
    "pickle.load": ("CWE-502", "Unsafe deserialization with pickle"),
    "yaml.load": ("CWE-502", "yaml.load without SafeLoader executes arbitrary Python"),
    "marshal.loads": ("CWE-502", "Unsafe deserialization with marshal"),
    "os.popen": ("CWE-78", "Shell command execution via os.popen"),
}

AUTH_HINTS = (
    "auth", "current_user", "get_current_user", "require", "permission", "token",
    "jwt", "login_required", "authenticated", "verify", "principal", "session_user",
)
HTTP_CLIENTS = {"requests", "httpx", "aiohttp", "urllib"}
FILE_OPENERS = {"open", "os.remove", "os.unlink", "shutil.copy", "shutil.move", "send_file", "FileResponse"}


class PythonRuleVisitor(ast.NodeVisitor):
    """Walks a module, accumulating :class:`UnifiedFinding` objects."""

    def __init__(self, context: AnalyzerContext) -> None:
        self.context = context
        self.findings: list[UnifiedFinding] = []
        self._scope: list[ast.AST] = []
        self._loop_depth = 0
        self._async_stack: list[bool] = []
        self._route_params: set[str] = set()
        self._module_globals: set[str] = set()

    # ---- emission --------------------------------------------------------
    def _emit(
        self,
        *,
        node: ast.AST,
        title: str,
        description: str,
        category: FindingCategory,
        severity: Severity,
        rule_id: str,
        risk: str,
        recommendation: str,
        cwe: str | None = None,
        confidence: float = 0.0,
        end_node: ast.AST | None = None,
    ) -> None:
        start = getattr(node, "lineno", 1)
        end = getattr(end_node or node, "end_lineno", start) or start
        if not self.context.touches_changed_lines(start, end):
            return
        self.findings.append(
            UnifiedFinding(
                title=title,
                description=description,
                category=category,
                severity=severity,
                file_path=self.context.file.path,
                start_line=start,
                end_line=max(start, end),
                source=FindingSource.AST_RULES,
                rule_id=rule_id,
                cwe=cwe,
                risk=risk,
                recommendation=recommendation,
                confidence=confidence,
                code_snippet=self.context.file.excerpt(start, max(start, end)),
            )
        )

    # ---- scope tracking --------------------------------------------------
    def visit_Module(self, node: ast.Module) -> None:
        for stmt in node.body:
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Name):
                        self._module_globals.add(target.id)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._enter_function(node, is_async=False)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._enter_function(node, is_async=True)

    def _enter_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, is_async: bool) -> None:
        self._scope.append(node)
        self._async_stack.append(is_async)
        previous_params = self._route_params

        decorators = [_name_of(d) for d in node.decorator_list]
        if _is_route(decorators):
            self._route_params = {a.arg for a in node.args.args} | {
                a.arg for a in node.args.kwonlyargs
            }
            self._check_route_authentication(node, decorators)
            self._check_route_validation(node)
        self.generic_visit(node)

        self._route_params = previous_params
        self._async_stack.pop()
        self._scope.pop()

    def visit_For(self, node: ast.For) -> None:
        self._loop_depth += 1
        self._check_n_plus_one(node)
        self.generic_visit(node)
        self._loop_depth -= 1

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self._loop_depth += 1
        self._check_n_plus_one(node)
        self.generic_visit(node)
        self._loop_depth -= 1

    def visit_While(self, node: ast.While) -> None:
        self._loop_depth += 1
        self.generic_visit(node)
        self._loop_depth -= 1

    # ---- call-site rules -------------------------------------------------
    def visit_Call(self, node: ast.Call) -> None:
        callee = _name_of(node.func)
        tail = callee.rsplit(".", 1)[-1]

        self._check_sql_injection(node, callee, tail)
        self._check_dangerous_call(node, callee)
        self._check_blocking_in_async(node, callee)
        self._check_ssrf(node, callee, tail)
        self._check_missing_timeout(node, callee)
        self._check_tls_verification(node, callee)
        self._check_path_traversal(node, callee, tail)
        self._check_permissive_cors(node, callee)
        self._check_unbounded_query(node, callee, tail)
        self.generic_visit(node)

    # ---- individual rules ------------------------------------------------
    def _check_sql_injection(self, node: ast.Call, callee: str, tail: str) -> None:
        if tail not in SQL_EXECUTORS or not node.args:
            return
        argument = node.args[0]
        interpolation = _interpolation_kind(argument)
        if interpolation is None:
            return
        if not _looks_like_sql(argument):
            return
        self._emit(
            node=node,
            title="SQL injection: query built with string interpolation",
            description=(
                f"`{callee}()` receives a query assembled with {interpolation}. Any value reaching "
                "this expression is concatenated directly into SQL, so an attacker controlling it "
                "controls the statement — including appending `OR 1=1`, `UNION SELECT`, or a second "
                "statement entirely."
            ),
            category=FindingCategory.SECURITY,
            severity=Severity.CRITICAL,
            rule_id="python.sql-injection",
            cwe="CWE-89",
            confidence=0.9,
            risk=(
                "Full read/write access to the database, authentication bypass, and data "
                "exfiltration. This is the single highest-impact web vulnerability class."
            ),
            recommendation=(
                "Pass values as bound parameters — `cursor.execute(\"SELECT ... WHERE id = %s\", (value,))` "
                "or SQLAlchemy `text(...).bindparams(...)`. Never build SQL with f-strings, `%`, `.format()` "
                "or `+`."
            ),
        )

    def _check_dangerous_call(self, node: ast.Call, callee: str) -> None:
        entry = DANGEROUS_CALLS.get(callee) or DANGEROUS_CALLS.get(callee.rsplit(".", 1)[-1])
        if not entry:
            return
        if callee.endswith("yaml.load") and any(
            kw.arg == "Loader" for kw in node.keywords
        ):
            return
        cwe, label = entry
        self._emit(
            node=node,
            title=label,
            description=(
                f"`{callee}()` executes or deserialises data. If any part of its input is influenced "
                "by a request, an upload, or repository content, this is remote code execution."
            ),
            category=FindingCategory.SECURITY,
            severity=Severity.CRITICAL if cwe in ("CWE-95", "CWE-502", "CWE-78") else Severity.HIGH,
            rule_id=f"python.dangerous-call.{callee.replace('.', '-')}",
            cwe=cwe,
            confidence=0.85,
            risk="Remote code execution on the application host.",
            recommendation=(
                "Use `ast.literal_eval` for literals, `json.loads` for data interchange, "
                "`yaml.safe_load` for YAML, and `subprocess.run([...], shell=False)` for processes."
            ),
        )

    def _check_blocking_in_async(self, node: ast.Call, callee: str) -> None:
        if not (self._async_stack and self._async_stack[-1]):
            return
        reason = BLOCKING_CALLS.get(callee)
        if reason is None and callee.split(".")[0] in HTTP_CLIENTS and callee.startswith("requests."):
            reason = "the `requests` library is synchronous"
        if reason is None:
            return
        alternative = ASYNC_ALTERNATIVES.get(callee, "an awaitable equivalent")
        self._emit(
            node=node,
            title=f"Blocking call `{callee}()` inside an async function",
            description=(
                f"This coroutine calls `{callee}()`, and {reason}. While it runs, the event loop "
                "cannot service any other request on this worker — throughput collapses to one "
                "request at a time under load."
            ),
            category=FindingCategory.PERFORMANCE,
            severity=Severity.HIGH,
            rule_id="python.blocking-call-in-async",
            confidence=0.9,
            risk=(
                "Request latency grows linearly with concurrency; health checks time out and the "
                "service appears down even though CPU is idle."
            ),
            recommendation=(
                f"Use {alternative}, or move the blocking work off the loop with "
                "`await asyncio.to_thread(...)` / `run_in_executor`."
            ),
        )

    def _check_n_plus_one(self, loop: ast.For | ast.AsyncFor) -> None:
        """A database call in a loop body issues one query per iteration."""
        for node in ast.walk(loop):
            if not isinstance(node, ast.Call):
                continue
            callee = _name_of(node.func)
            tail = callee.rsplit(".", 1)[-1]
            if tail not in DB_CALLS:
                continue
            owner = callee.rsplit(".", 2)[0].lower() if "." in callee else ""
            if not any(hint in callee.lower() for hint in DB_OWNERS) and owner not in DB_OWNERS:
                continue
            self._emit(
                node=node,
                title="N+1 query: database call inside a loop",
                description=(
                    f"`{callee}()` executes once per iteration of the enclosing loop. For a "
                    "collection of N items this issues N round trips to the database instead of one, "
                    "and the cost grows with production data volume — not with test-fixture size."
                ),
                category=FindingCategory.PERFORMANCE,
                severity=Severity.MEDIUM,
                rule_id="python.n-plus-one-query",
                confidence=0.75,
                risk=(
                    "Endpoint latency scales linearly with result-set size; connection-pool "
                    "exhaustion under moderate traffic."
                ),
                recommendation=(
                    "Fetch the whole set in one query — `WHERE id IN (...)`, a JOIN, or an eager-loading "
                    "option such as `selectinload()` — then index the results in memory."
                ),
            )
            return  # one finding per loop is enough

    def _check_route_authentication(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef, decorators: list[str]
    ) -> None:
        method = next(
            (d.rsplit(".", 1)[-1].upper() for d in decorators if _is_route([d])), "GET"
        )
        if method in ("GET", "HEAD", "OPTIONS"):
            return  # read endpoints are frequently public by design

        blob = " ".join(
            [
                *decorators,
                *[a.arg for a in node.args.args],
                *[a.arg for a in node.args.kwonlyargs],
                ast.dump(node.args) if node.args else "",
            ]
        ).lower()
        if any(hint in blob for hint in AUTH_HINTS):
            return
        body_blob = " ".join(
            _name_of(inner.func) for inner in ast.walk(node) if isinstance(inner, ast.Call)
        ).lower()
        if any(hint in body_blob for hint in AUTH_HINTS):
            return

        self._emit(
            node=node,
            title=f"State-changing route `{node.name}` has no visible authentication",
            description=(
                f"`{node.name}` handles {method} requests but declares no authentication dependency, "
                "decorator, or in-body identity check. Nothing in this handler establishes *who* is "
                "making the request before it mutates state."
            ),
            category=FindingCategory.SECURITY,
            severity=Severity.HIGH,
            rule_id="python.route-missing-auth",
            cwe="CWE-306",
            confidence=0.6,
            risk="Unauthenticated writes: any client on the network can invoke this operation.",
            recommendation=(
                "Add the framework's auth dependency (`Depends(get_current_user)`, "
                "`@login_required`) and an authorization check that the caller owns the resource."
            ),
        )

    def _check_route_validation(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Untyped or `dict`-typed request bodies bypass schema validation."""
        for arg in list(node.args.args) + list(node.args.kwonlyargs):
            if arg.arg in ("self", "cls", "request", "response"):
                continue
            annotation = _name_of(arg.annotation) if arg.annotation else ""
            if annotation in ("dict", "Dict", "Any", "object", "") and arg.arg not in ("db", "session"):
                self._emit(
                    node=node,
                    title=f"Unvalidated request input `{arg.arg}` in `{node.name}`",
                    description=(
                        f"Parameter `{arg.arg}` is typed `{annotation or 'untyped'}`, so the framework "
                        "performs no schema validation. Missing keys, wrong types and unexpected "
                        "extra fields all reach the handler body unchecked."
                    ),
                    category=FindingCategory.BUG,
                    severity=Severity.MEDIUM,
                    rule_id="python.missing-input-validation",
                    cwe="CWE-20",
                    confidence=0.6,
                    risk="Runtime KeyError/TypeError on malformed input, and mass-assignment exposure.",
                    recommendation="Declare a Pydantic model for the payload and annotate the parameter with it.",
                )
                return

    def _check_ssrf(self, node: ast.Call, callee: str, tail: str) -> None:
        root = callee.split(".")[0]
        if root not in HTTP_CLIENTS or tail not in ("get", "post", "put", "delete", "request", "urlopen"):
            return
        if not node.args:
            return
        target = node.args[0]
        if isinstance(target, ast.Constant):
            return  # literal URL — not attacker controlled
        referenced = _names_in(target)
        if not (referenced & self._route_params):
            return
        self._emit(
            node=node,
            title="Server-side request forgery: request parameter used as a URL",
            description=(
                f"`{callee}()` fetches a URL derived from the request parameter(s) "
                f"{sorted(referenced & self._route_params)}. The server will request whatever host "
                "the caller names — including `http://169.254.169.254/` cloud metadata, internal "
                "admin services, and `file://` style schemes depending on the client."
            ),
            category=FindingCategory.SECURITY,
            severity=Severity.HIGH,
            rule_id="python.ssrf",
            cwe="CWE-918",
            confidence=0.8,
            risk="Access to internal networks and cloud credentials from the metadata endpoint.",
            recommendation=(
                "Validate the URL against an explicit allowlist of hosts and schemes, resolve DNS "
                "and reject private/link-local address ranges, and disable redirects."
            ),
        )

    def _check_missing_timeout(self, node: ast.Call, callee: str) -> None:
        root = callee.split(".")[0]
        tail = callee.rsplit(".", 1)[-1]
        if root not in ("requests", "httpx") or tail not in ("get", "post", "put", "delete", "request"):
            return
        if any(kw.arg == "timeout" for kw in node.keywords):
            return
        self._emit(
            node=node,
            title=f"Outbound HTTP call without a timeout (`{callee}`)",
            description=(
                f"`{callee}()` has no `timeout=`. The default for `requests` is *no timeout at all*, "
                "so a slow or hung upstream holds this worker open indefinitely."
            ),
            category=FindingCategory.RELIABILITY,
            severity=Severity.MEDIUM,
            rule_id="python.missing-timeout",
            confidence=0.85,
            risk="Cascading failure: one slow dependency exhausts the whole worker pool.",
            recommendation="Pass an explicit `timeout=(connect, read)` and handle the timeout exception.",
        )

    def _check_tls_verification(self, node: ast.Call, callee: str) -> None:
        for keyword in node.keywords:
            if keyword.arg == "verify" and isinstance(keyword.value, ast.Constant) and keyword.value.value is False:
                self._emit(
                    node=node,
                    title="TLS certificate verification disabled",
                    description=(
                        f"`{callee}()` is called with `verify=False`, which accepts any certificate "
                        "including an attacker's. TLS provides no protection here."
                    ),
                    category=FindingCategory.SECURITY,
                    severity=Severity.HIGH,
                    rule_id="python.tls-verification-disabled",
                    cwe="CWE-295",
                    confidence=0.95,
                    risk="Machine-in-the-middle interception of credentials and payloads.",
                    recommendation="Remove `verify=False`; supply a CA bundle if you need a private root.",
                )

    def _check_path_traversal(self, node: ast.Call, callee: str, tail: str) -> None:
        if callee not in FILE_OPENERS and tail not in ("open", "send_file", "FileResponse"):
            return
        if not node.args:
            return
        target = node.args[0]
        if isinstance(target, ast.Constant):
            return
        referenced = _names_in(target)
        if not (referenced & self._route_params):
            return
        self._emit(
            node=node,
            title="Path traversal: request input used to build a filesystem path",
            description=(
                f"`{callee}()` opens a path derived from request parameter(s) "
                f"{sorted(referenced & self._route_params)}. A value such as `../../etc/passwd` or an "
                "absolute path escapes the intended directory — `os.path.join` does not prevent this "
                "and silently discards the prefix when handed an absolute path."
            ),
            category=FindingCategory.SECURITY,
            severity=Severity.HIGH,
            rule_id="python.path-traversal",
            cwe="CWE-22",
            confidence=0.8,
            risk="Arbitrary file read (and write, for upload handlers) outside the intended directory.",
            recommendation=(
                "Resolve the candidate with `Path(base, name).resolve()` and reject it unless "
                "`resolved.is_relative_to(base.resolve())`. Prefer an opaque ID mapped server-side."
            ),
        )

    def _check_permissive_cors(self, node: ast.Call, callee: str) -> None:
        if "CORS" not in callee and "cors" not in callee.lower():
            return
        for keyword in node.keywords:
            if keyword.arg not in ("allow_origins", "origins"):
                continue
            values = _literal_strings(keyword.value)
            if "*" not in values:
                continue
            credentials = any(
                kw.arg == "allow_credentials"
                and isinstance(kw.value, ast.Constant)
                and kw.value.value is True
                for kw in node.keywords
            )
            self._emit(
                node=node,
                title="CORS allows every origin",
                description=(
                    "The CORS middleware is configured with `*`"
                    + (
                        " *together with* `allow_credentials=True`, a combination browsers reject and "
                        "servers must never intend."
                        if credentials
                        else ", so any website can call this API with the user's browser."
                    )
                ),
                category=FindingCategory.SECURITY,
                severity=Severity.HIGH if credentials else Severity.MEDIUM,
                rule_id="python.permissive-cors",
                cwe="CWE-942",
                confidence=0.9,
                risk="Cross-origin data theft from authenticated users.",
                recommendation="List the exact frontend origins allowed to call this API.",
            )

    def _check_unbounded_query(self, node: ast.Call, callee: str, tail: str) -> None:
        if tail not in ("all", "fetchall", "scalars"):
            return
        if not any(hint in callee.lower() for hint in DB_OWNERS):
            return
        if not self._route_params:
            return  # only interesting inside a request handler
        chain = _call_chain(node)
        if any(part in ("limit", "paginate", "slice", "first", "offset") for part in chain):
            return
        self._emit(
            node=node,
            title="Unbounded query result returned from a request handler",
            description=(
                f"`{callee}()` materialises every matching row with no `limit()`/pagination in the "
                "chain. Behaviour is fine on a seed database and degrades without warning as the "
                "table grows."
            ),
            category=FindingCategory.PERFORMANCE,
            severity=Severity.MEDIUM,
            rule_id="python.unbounded-pagination",
            confidence=0.65,
            risk="Memory spikes and multi-second responses once the table reaches production size.",
            recommendation="Apply `.limit()`/`.offset()` with a capped page size and return a cursor.",
        )

    # ---- statement-level rules ------------------------------------------
    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        is_bare = node.type is None
        is_broad = isinstance(node.type, ast.Name) and node.type.id in ("Exception", "BaseException")
        swallows = all(isinstance(stmt, ast.Pass | ast.Continue) for stmt in node.body) or (
            len(node.body) == 1 and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
        )

        if is_bare or (is_broad and swallows):
            self._emit(
                node=node,
                title="Exception swallowed without handling" if swallows else "Bare `except:` catches everything",
                description=(
                    "This handler catches every exception"
                    + (
                        " and discards it. Failures become silent: the operation reports success while "
                        "having done nothing, and there is no log line to debug from."
                        if swallows
                        else ", including `KeyboardInterrupt` and `SystemExit`, which makes the process "
                        "impossible to shut down cleanly."
                    )
                ),
                category=FindingCategory.RELIABILITY,
                severity=Severity.MEDIUM,
                rule_id="python.swallowed-exception",
                cwe="CWE-390",
                confidence=0.85,
                risk="Data-corrupting failures pass unnoticed in production.",
                recommendation=(
                    "Catch the specific exception you can handle, log it with context, and re-raise "
                    "or return a typed error for anything else."
                ),
            )
        self.generic_visit(node)

    def visit_Assert(self, node: ast.Assert) -> None:
        if not self.context.file.is_test:
            blob = ast.dump(node.test).lower()
            if any(hint in blob for hint in ("auth", "permission", "role", "admin", "owner", "token")):
                self._emit(
                    node=node,
                    title="Security check implemented with `assert`",
                    description=(
                        "`assert` statements are removed entirely when Python runs with `-O`, so this "
                        "authorization check silently disappears in an optimised production run."
                    ),
                    category=FindingCategory.SECURITY,
                    severity=Severity.HIGH,
                    rule_id="python.assert-for-authorization",
                    cwe="CWE-617",
                    confidence=0.8,
                    risk="Authorization bypass in any deployment using `python -O`.",
                    recommendation="Replace with an explicit `if not ...: raise HTTPException(403)`.",
                )
        self.generic_visit(node)

    def visit_Global(self, node: ast.Global) -> None:
        if self._async_stack and self._async_stack[-1]:
            self._emit(
                node=node,
                title="Shared mutable state mutated from a coroutine",
                description=(
                    f"This coroutine declares `global {', '.join(node.names)}` and mutates process-wide "
                    "state. Concurrent requests interleave at every `await`, so read-modify-write "
                    "sequences race and lose updates non-deterministically."
                ),
                category=FindingCategory.RELIABILITY,
                severity=Severity.MEDIUM,
                rule_id="python.async-race-condition",
                cwe="CWE-362",
                confidence=0.7,
                risk="Lost updates and corrupted counters that only reproduce under load.",
                recommendation=(
                    "Guard the section with `asyncio.Lock()`, or move the state into the database "
                    "with an atomic update."
                ),
            )
        self.generic_visit(node)

    def visit_Return(self, node: ast.Return) -> None:
        parent_body = self._current_body(node)
        if parent_body:
            index = parent_body.index(node)
            unreachable = parent_body[index + 1 :]
            if unreachable:
                self._emit(
                    node=unreachable[0],
                    title="Dead code after `return`",
                    description=(
                        f"{len(unreachable)} statement(s) follow this `return` and can never execute. "
                        "Dead code hides intent and misleads future readers into thinking it runs."
                    ),
                    category=FindingCategory.CODE_QUALITY,
                    severity=Severity.LOW,
                    rule_id="python.dead-code",
                    confidence=0.95,
                    risk="Maintenance hazard; often the residue of an incomplete refactor.",
                    recommendation="Delete the unreachable statements or move them before the return.",
                    end_node=unreachable[-1],
                )
        self.generic_visit(node)

    def _current_body(self, node: ast.AST) -> list | None:
        for scope in reversed(self._scope):
            body = getattr(scope, "body", None)
            if isinstance(body, list) and node in body:
                return body
        return None


# --------------------------------------------------------------------------- #
# AST helpers
# --------------------------------------------------------------------------- #
def _name_of(node: ast.AST | None) -> str:
    if node is None:
        return ""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_name_of(node.value)}.{node.attr}".lstrip(".")
    if isinstance(node, ast.Call):
        return _name_of(node.func)
    if isinstance(node, ast.Subscript):
        return _name_of(node.value)
    if isinstance(node, ast.Constant):
        return str(node.value)
    return ""


def _is_route(decorators: list[str]) -> bool:
    for decorator in decorators:
        parts = decorator.split(".")
        if len(parts) >= 2 and parts[-1] in (
            "get", "post", "put", "patch", "delete", "route", "websocket", "head", "options"
        ):
            return True
    return False


def _interpolation_kind(node: ast.AST) -> str | None:
    """Describe how a string expression was built, if it is dynamic."""
    if isinstance(node, ast.JoinedStr):
        return "an f-string" if any(isinstance(v, ast.FormattedValue) for v in node.values) else None
    if isinstance(node, ast.BinOp):
        if isinstance(node.op, ast.Add):
            return "`+` concatenation"
        if isinstance(node.op, ast.Mod):
            return "`%` formatting"
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "format":
        return "`.format()`"
    return None


def _looks_like_sql(node: ast.AST) -> bool:
    text = " ".join(
        str(child.value).lower()
        for child in ast.walk(node)
        if isinstance(child, ast.Constant) and isinstance(child.value, str)
    )
    return any(keyword in text for keyword in SQL_KEYWORDS)


def _names_in(node: ast.AST) -> set[str]:
    return {child.id for child in ast.walk(node) if isinstance(child, ast.Name)}


def _literal_strings(node: ast.AST) -> set[str]:
    return {
        child.value
        for child in ast.walk(node)
        if isinstance(child, ast.Constant) and isinstance(child.value, str)
    }


def _call_chain(node: ast.Call) -> list[str]:
    """Method names in a fluent chain, e.g. ``session.query(X).filter(...).all()``."""
    chain: list[str] = []
    current: ast.AST = node
    while isinstance(current, ast.Call | ast.Attribute):
        if isinstance(current, ast.Attribute):
            chain.append(current.attr)
            current = current.value
        else:
            current = current.func
    return chain
