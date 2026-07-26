"""Symbol-aware chunking.

Repository code is split along structural boundaries — classes, functions,
methods, import blocks — rather than fixed character windows, so a retrieved
chunk is always a complete, compilable-looking unit the model can reason about.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.types import ImportRef, SourceFile, Symbol, SymbolKind

MAX_CHUNK_LINES = 160
MIN_CHUNK_LINES = 3


@dataclass(slots=True)
class Chunk:
    id: str
    file_path: str
    content: str
    start_line: int
    end_line: int
    kind: str  # imports | class | function | method | route | model | test | module
    symbol_name: str = ""
    parent: str = ""
    language: str = ""
    tokens: int = 0
    metadata: dict = field(default_factory=dict)

    @property
    def header(self) -> str:
        location = f"{self.file_path}:{self.start_line}-{self.end_line}"
        name = f" {self.symbol_name}" if self.symbol_name else ""
        return f"[{self.kind}{name}] {location}"


def estimate_tokens(text: str) -> int:
    """Cheap, provider-agnostic token estimate (~4 characters per token)."""
    return max(1, len(text) // 4)


def chunk_file(
    source_file: SourceFile,
    symbols: list[Symbol],
    imports: list[ImportRef] | None = None,
) -> list[Chunk]:
    """Split one file into retrievable chunks."""
    lines = source_file.lines
    if not lines:
        return []

    chunks: list[Chunk] = []
    file_symbols = sorted(
        [s for s in symbols if s.file_path == source_file.path],
        key=lambda s: (s.start_line, -s.end_line),
    )

    # 1. Import block — cheap and disproportionately informative about coupling.
    file_imports = [i for i in (imports or []) if i.file_path == source_file.path]
    if file_imports:
        last_import_line = min(max(i.line for i in file_imports) + 1, len(lines))
        content = "\n".join(lines[:last_import_line])
        if content.strip():
            chunks.append(
                Chunk(
                    id=f"{source_file.path}#imports",
                    file_path=source_file.path,
                    content=content,
                    start_line=1,
                    end_line=last_import_line,
                    kind="imports",
                    language=source_file.language.value,
                    tokens=estimate_tokens(content),
                    metadata={"modules": [i.module for i in file_imports][:40]},
                )
            )

    # 2. One chunk per top-level symbol; nested members are folded into the parent.
    covered: set[int] = set()
    for symbol in file_symbols:
        if symbol.parent and any(
            s.name == symbol.parent and s.start_line <= symbol.start_line <= s.end_line
            for s in file_symbols
        ):
            continue  # covered by the parent class chunk
        start = max(1, symbol.start_line)
        end = min(len(lines), max(symbol.end_line, symbol.start_line))
        if end - start + 1 > MAX_CHUNK_LINES:
            end = start + MAX_CHUNK_LINES - 1
        content = "\n".join(lines[start - 1 : end])
        if len(content.strip()) < 10:
            continue
        chunks.append(
            Chunk(
                id=f"{source_file.path}#{symbol.name}:{start}",
                file_path=source_file.path,
                content=content,
                start_line=start,
                end_line=end,
                kind=_kind_label(symbol.kind),
                symbol_name=symbol.name,
                parent=symbol.parent or "",
                language=source_file.language.value,
                tokens=estimate_tokens(content),
                metadata={
                    "signature": symbol.signature,
                    "docstring": symbol.docstring[:200],
                    "complexity": symbol.complexity,
                    "is_async": symbol.is_async,
                    "decorators": symbol.decorators,
                },
            )
        )
        covered.update(range(start, end + 1))

    # 3. Module-level code not covered by any symbol (config, wiring, side effects).
    remaining = [n for n in range(1, len(lines) + 1) if n not in covered]
    for start, end in _contiguous_ranges(remaining):
        if end - start + 1 < MIN_CHUNK_LINES:
            continue
        content = "\n".join(lines[start - 1 : min(end, start + MAX_CHUNK_LINES - 1)])
        if not content.strip():
            continue
        chunks.append(
            Chunk(
                id=f"{source_file.path}#module:{start}",
                file_path=source_file.path,
                content=content,
                start_line=start,
                end_line=min(end, start + MAX_CHUNK_LINES - 1),
                kind="module",
                language=source_file.language.value,
                tokens=estimate_tokens(content),
            )
        )

    if not chunks:
        content = "\n".join(lines[:MAX_CHUNK_LINES])
        chunks.append(
            Chunk(
                id=f"{source_file.path}#whole",
                file_path=source_file.path,
                content=content,
                start_line=1,
                end_line=min(len(lines), MAX_CHUNK_LINES),
                kind="module",
                language=source_file.language.value,
                tokens=estimate_tokens(content),
            )
        )
    return chunks


def _kind_label(kind: SymbolKind) -> str:
    return {
        SymbolKind.CLASS: "class",
        SymbolKind.FUNCTION: "function",
        SymbolKind.METHOD: "method",
        SymbolKind.ROUTE: "route",
        SymbolKind.MODEL: "model",
        SymbolKind.TEST: "test",
        SymbolKind.COMPONENT: "component",
        SymbolKind.CONSTANT: "constant",
        SymbolKind.MODULE: "module",
    }.get(kind, "function")


def _contiguous_ranges(numbers: list[int]) -> list[tuple[int, int]]:
    if not numbers:
        return []
    ranges: list[tuple[int, int]] = []
    start = previous = numbers[0]
    for value in numbers[1:]:
        if value == previous + 1:
            previous = value
            continue
        ranges.append((start, previous))
        start = previous = value
    ranges.append((start, previous))
    return ranges
