"""Builds and queries the repository knowledge graph.

Nodes are files, modules, classes, functions, routes, database models, tests and
external dependencies. Edges capture imports, calls, inheritance, test coverage
and dependency use.

The graph is what lets RepoMedic reason about *impact*: when a pull request
changes a function signature or an API response shape, reverse-import traversal
identifies which unchanged files consume it, which is the basis for
breaking-change findings.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from app.core.logging import get_logger
from app.domain.types import CallRef, ImportRef, SourceFile, Symbol, SymbolKind

logger = get_logger(__name__)

MAX_NODES = 1200
MAX_EDGES = 3000


@dataclass(slots=True)
class Node:
    id: str
    label: str
    type: str
    file_path: str = ""
    language: str = ""
    start_line: int = 0
    end_line: int = 0
    changed: bool = False
    metrics: dict = field(default_factory=dict)


@dataclass(slots=True)
class Edge:
    id: str
    source: str
    target: str
    type: str
    weight: float = 1.0


@dataclass
class KnowledgeGraph:
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: dict[str, Edge] = field(default_factory=dict)
    _out: dict[str, list[Edge]] = field(default_factory=lambda: defaultdict(list))
    _in: dict[str, list[Edge]] = field(default_factory=lambda: defaultdict(list))

    # ---- construction ----------------------------------------------------
    def add_node(self, node: Node) -> None:
        if node.id not in self.nodes and len(self.nodes) < MAX_NODES:
            self.nodes[node.id] = node

    def add_edge(self, edge: Edge) -> None:
        if edge.id in self.edges or len(self.edges) >= MAX_EDGES:
            return
        if edge.source not in self.nodes or edge.target not in self.nodes:
            return
        self.edges[edge.id] = edge
        self._out[edge.source].append(edge)
        self._in[edge.target].append(edge)

    # ---- queries ---------------------------------------------------------
    def dependents_of(self, file_path: str, *, max_depth: int = 3) -> list[str]:
        """Files that (transitively) import ``file_path`` — its blast radius."""
        start = f"file:{file_path}"
        if start not in self.nodes:
            return []
        seen: set[str] = {start}
        result: list[str] = []
        queue: deque[tuple[str, int]] = deque([(start, 0)])
        while queue:
            current, depth = queue.popleft()
            if depth >= max_depth:
                continue
            for edge in self._in.get(current, []):
                if edge.type not in ("imports", "calls"):
                    continue
                if edge.source in seen:
                    continue
                seen.add(edge.source)
                node = self.nodes.get(edge.source)
                if node and node.type == "file":
                    result.append(node.file_path)
                queue.append((edge.source, depth + 1))
        return result

    def dependencies_of(self, file_path: str, *, max_depth: int = 2) -> list[str]:
        start = f"file:{file_path}"
        if start not in self.nodes:
            return []
        seen = {start}
        result: list[str] = []
        queue: deque[tuple[str, int]] = deque([(start, 0)])
        while queue:
            current, depth = queue.popleft()
            if depth >= max_depth:
                continue
            for edge in self._out.get(current, []):
                if edge.type != "imports" or edge.target in seen:
                    continue
                seen.add(edge.target)
                node = self.nodes.get(edge.target)
                if node and node.type == "file":
                    result.append(node.file_path)
                queue.append((edge.target, depth + 1))
        return result

    def tests_covering(self, file_path: str) -> list[str]:
        return [
            self.nodes[edge.source].file_path
            for edge in self._in.get(f"file:{file_path}", [])
            if edge.type == "imports"
            and edge.source in self.nodes
            and self.nodes[edge.source].metrics.get("is_test")
        ]

    def symbols_in(self, file_path: str) -> list[Node]:
        return [n for n in self.nodes.values() if n.file_path == file_path and n.type != "file"]

    def path_between(self, source_file: str, target_file: str, *, max_depth: int = 4) -> list[str]:
        """Shortest import path between two files, for impact visualisation."""
        start, goal = f"file:{source_file}", f"file:{target_file}"
        if start not in self.nodes or goal not in self.nodes:
            return []
        queue: deque[list[str]] = deque([[start]])
        seen = {start}
        while queue:
            path = queue.popleft()
            if len(path) > max_depth:
                continue
            for edge in self._out.get(path[-1], []):
                if edge.target == goal:
                    return [*path, goal]
                if edge.target in seen:
                    continue
                seen.add(edge.target)
                queue.append([*path, edge.target])
        return []

    def circular_imports(self) -> list[list[str]]:
        """Detect import cycles between files (architecture smell)."""
        cycles: list[list[str]] = []
        colour: dict[str, int] = {}
        stack: list[str] = []

        def visit(node_id: str) -> None:
            colour[node_id] = 1
            stack.append(node_id)
            for edge in self._out.get(node_id, []):
                if edge.type != "imports":
                    continue
                target = edge.target
                if colour.get(target, 0) == 0:
                    visit(target)
                elif colour.get(target) == 1 and target in stack:
                    cycle = stack[stack.index(target) :]
                    if len(cycle) > 1 and len(cycles) < 20:
                        cycles.append(
                            [self.nodes[n].file_path or self.nodes[n].label for n in cycle if n in self.nodes]
                        )
            stack.pop()
            colour[node_id] = 2

        for node_id, node in list(self.nodes.items()):
            if node.type == "file" and colour.get(node_id, 0) == 0:
                visit(node_id)
        return cycles

    def stats(self) -> dict[str, int]:
        by_type: dict[str, int] = defaultdict(int)
        for node in self.nodes.values():
            by_type[node.type] += 1
        by_type["edges"] = len(self.edges)
        by_type["nodes"] = len(self.nodes)
        return dict(by_type)

    def to_payload(self, *, embedding=None) -> dict:
        """Serialise the graph.

        When an embedding is supplied each node also carries its PageRank
        centrality and nearest neighbours, so consumers get "how important is
        this" and "what else looks like this" without recomputing anything.
        """
        centrality = embedding.centrality if embedding is not None else {}

        def node_metrics(node: Node) -> dict:
            metrics = dict(node.metrics)
            if embedding is None:
                return metrics
            metrics["centrality"] = round(centrality.get(node.id, 0.0), 4)
            metrics["similar"] = [
                {"id": other, "score": round(score, 3)}
                for other, score in embedding.similar(node.id, k=3)
            ]
            return metrics

        return {
            "nodes": [
                {
                    "id": n.id, "label": n.label, "type": n.type, "file_path": n.file_path,
                    "language": n.language, "start_line": n.start_line, "end_line": n.end_line,
                    "changed": n.changed, "metrics": node_metrics(n),
                }
                for n in self.nodes.values()
            ],
            "edges": [
                {"id": e.id, "source": e.source, "target": e.target, "type": e.type, "weight": e.weight}
                for e in self.edges.values()
            ],
            "stats": self.stats(),
        }


# --------------------------------------------------------------------------- #
# Construction
# --------------------------------------------------------------------------- #
def build_graph(
    files: Iterable[SourceFile],
    symbols: Iterable[Symbol],
    imports: Iterable[ImportRef],
    calls: Iterable[CallRef],
    *,
    changed_paths: set[str] | None = None,
    dependencies: dict[str, str] | None = None,
) -> KnowledgeGraph:
    graph = KnowledgeGraph()
    changed_paths = changed_paths or set()
    file_list = list(files)
    known_paths = {f.path for f in file_list}

    for source_file in file_list:
        graph.add_node(
            Node(
                id=f"file:{source_file.path}",
                label=PurePosixPath(source_file.path).name,
                type="file",
                file_path=source_file.path,
                language=source_file.language.value,
                changed=source_file.path in changed_paths,
                metrics={"lines": len(source_file.lines), "is_test": source_file.is_test},
            )
        )

    symbol_index: dict[tuple[str, str], str] = {}
    for symbol in symbols:
        node_id = f"symbol:{symbol.file_path}:{symbol.name}:{symbol.start_line}"
        node_type = {
            SymbolKind.CLASS: "class",
            SymbolKind.FUNCTION: "function",
            SymbolKind.METHOD: "function",
            SymbolKind.ROUTE: "route",
            SymbolKind.MODEL: "model",
            SymbolKind.TEST: "test",
            SymbolKind.COMPONENT: "component",
            SymbolKind.CONSTANT: "constant",
            SymbolKind.MODULE: "module",
        }.get(symbol.kind, "function")
        graph.add_node(
            Node(
                id=node_id,
                label=symbol.name,
                type=node_type,
                file_path=symbol.file_path,
                start_line=symbol.start_line,
                end_line=symbol.end_line,
                changed=symbol.file_path in changed_paths,
                metrics={"complexity": symbol.complexity, "is_async": symbol.is_async},
            )
        )
        symbol_index[(symbol.file_path, symbol.name)] = node_id
        graph.add_edge(
            Edge(
                id=f"contains:{symbol.file_path}:{symbol.name}:{symbol.start_line}",
                source=f"file:{symbol.file_path}",
                target=node_id,
                type="contains",
            )
        )
        for base in symbol.metadata.get("bases", []) or []:
            target = symbol_index.get((symbol.file_path, base))
            if target:
                graph.add_edge(
                    Edge(id=f"extends:{node_id}:{base}", source=node_id, target=target, type="extends")
                )

    # Imports: resolve relative module specifiers to files inside the repository.
    for ref in imports:
        target_path = _resolve_import(ref, known_paths)
        if target_path:
            graph.add_edge(
                Edge(
                    id=f"imports:{ref.file_path}:{target_path}:{ref.line}",
                    source=f"file:{ref.file_path}",
                    target=f"file:{target_path}",
                    type="imports",
                )
            )
            continue
        package = ref.module.split(".")[0].lstrip(".")
        if not package or ref.is_relative:
            continue
        dependency_id = f"dependency:{package}"
        graph.add_node(
            Node(
                id=dependency_id,
                label=package,
                type="dependency",
                metrics={"version": (dependencies or {}).get(package, "")},
            )
        )
        graph.add_edge(
            Edge(
                id=f"depends:{ref.file_path}:{package}",
                source=f"file:{ref.file_path}",
                target=dependency_id,
                type="depends_on",
            )
        )

    for call in calls:
        source_id = symbol_index.get((call.file_path, call.caller))
        target_id = next(
            (node_id for (path, name), node_id in symbol_index.items() if name == call.callee.rsplit(".", 1)[-1]),
            None,
        )
        if source_id and target_id and source_id != target_id:
            graph.add_edge(
                Edge(
                    id=f"calls:{source_id}:{target_id}",
                    source=source_id,
                    target=target_id,
                    type="calls",
                )
            )

    # Test coverage edges: a test file importing a module tests it.
    for source_file in file_list:
        if not source_file.is_test:
            continue
        for target in graph.dependencies_of(source_file.path, max_depth=1):
            graph.add_edge(
                Edge(
                    id=f"tests:{source_file.path}:{target}",
                    source=f"file:{source_file.path}",
                    target=f"file:{target}",
                    type="tests",
                )
            )

    logger.info("graph.built", **graph.stats())
    return graph


_JS_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")


def _resolve_import(ref: ImportRef, known_paths: set[str]) -> str | None:
    """Best-effort resolution of a module specifier to a repository file."""
    module = ref.module
    if not module:
        return None

    # JavaScript/TypeScript relative specifiers.
    if module.startswith("."):
        base = PurePosixPath(ref.file_path).parent
        candidate = (base / module).as_posix()
        candidate = _normalise(candidate)
        for suffix in ("", *_JS_EXTENSIONS, "/index.ts", "/index.tsx", "/index.js", ".py"):
            if f"{candidate}{suffix}" in known_paths:
                return f"{candidate}{suffix}"

    # Python dotted modules.
    dotted = module.lstrip(".").replace(".", "/")
    if dotted:
        for suffix in (".py", "/__init__.py"):
            if f"{dotted}{suffix}" in known_paths:
                return f"{dotted}{suffix}"
        # Also try relative to the importing package.
        base = PurePosixPath(ref.file_path).parent
        for suffix in (".py", "/__init__.py"):
            candidate = _normalise((base / dotted).as_posix()) + suffix
            if candidate in known_paths:
                return candidate
    return None


def _normalise(path: str) -> str:
    parts: list[str] = []
    for part in path.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)
