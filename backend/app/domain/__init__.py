"""Framework-free domain types shared by analyzers, scanners, agents and patching."""

from app.domain.types import (
    AnalysisContext,
    CallRef,
    FileChange,
    ImportRef,
    Language,
    PatchProposal,
    SourceFile,
    Symbol,
    SymbolKind,
    UnifiedFinding,
    fingerprint_finding,
)

__all__ = [
    "AnalysisContext",
    "CallRef",
    "FileChange",
    "ImportRef",
    "Language",
    "PatchProposal",
    "SourceFile",
    "Symbol",
    "SymbolKind",
    "UnifiedFinding",
    "fingerprint_finding",
]
