"""Language adapters. Adding a language means adding one module here."""

from app.analyzers.base import LanguageAnalyzer, ParseResult  # noqa: F401
from app.analyzers.registry import (  # noqa: F401
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
