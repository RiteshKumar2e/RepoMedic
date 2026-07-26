"""Language adapters. Adding a language means adding one module here."""

from app.analyzers.base import LanguageAnalyzer, ParseResult
from app.analyzers.registry import (
    analyzer_for,
    analyzer_for_path,
    supported_languages,
)

__all__ = [
    "LanguageAnalyzer",
    "ParseResult",
    "analyzer_for",
    "analyzer_for_path",
    "supported_languages",
]
