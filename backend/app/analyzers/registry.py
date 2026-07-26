"""Language-analyzer registry.

Adding a language: implement :class:`~app.analyzers.base.LanguageAnalyzer`,
import it here, and add it to ``_ANALYZERS``. See docs/adding-a-language.md.
"""

from __future__ import annotations

from app.analyzers.base import LanguageAnalyzer
from app.analyzers.javascript_analyzer import (
    JavaScriptAnalyzer,
    TSXAnalyzer,
    TypeScriptAnalyzer,
)
from app.analyzers.python_analyzer import PythonAnalyzer
from app.domain.types import Language

_ANALYZERS: dict[Language, LanguageAnalyzer] = {
    Language.PYTHON: PythonAnalyzer(),
    Language.JAVASCRIPT: JavaScriptAnalyzer(),
    Language.TYPESCRIPT: TypeScriptAnalyzer(),
    Language.TSX: TSXAnalyzer(),
}


def analyzer_for(language: Language) -> LanguageAnalyzer | None:
    return _ANALYZERS.get(language)


def analyzer_for_path(path: str) -> LanguageAnalyzer | None:
    return analyzer_for(Language.from_path(path))


def supported_languages() -> list[str]:
    return sorted({lang.value for lang in _ANALYZERS})
