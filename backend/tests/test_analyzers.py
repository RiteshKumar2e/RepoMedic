from __future__ import annotations

from app.analyzers.javascript_analyzer import JavaScriptAnalyzer
from app.analyzers.python_analyzer import PythonAnalyzer


def test_python_analyzer_parse_and_extract():
    code = """
import os

class DiscountService:
    def apply_discount(self, code: str) -> float:
        query = f"SELECT * FROM discounts WHERE code = '{code}'"
        return 0.0
"""
    analyzer = PythonAnalyzer()
    parse_res = analyzer.parse(code, "service.py")
    assert parse_res.ok is True

    symbols = analyzer.extract_symbols(parse_res)
    assert any(s.name == "DiscountService" for s in symbols)
    assert any(s.name == "apply_discount" for s in symbols)

    imports = analyzer.extract_imports(parse_res)
    assert any(i.module == "os" for i in imports)


def test_javascript_analyzer_parse():
    code = """
import { useState } from 'react';

export function Header() {
    return <h1>RepoMedic</h1>;
}
"""
    analyzer = JavaScriptAnalyzer()
    parse_res = analyzer.parse(code, "Header.tsx")
    assert parse_res.ok is True
