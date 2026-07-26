"""Deterministic template fixes must always produce parseable code.

A template that emits syntactically invalid output is worse than no template at
all — it burns reviewer trust. Every template is checked here against a realistic
input, and the result is re-parsed with the language's own analyzer.
"""

from __future__ import annotations

import pytest

from app.analyzers.registry import analyzer_for_path
from app.domain.types import UnifiedFinding
from app.models.enums import FindingCategory, FindingSource, Severity
from app.patching.differ import apply_proposal
from app.patching.templates import template_patch


def _finding(rule_id: str, path: str, start: int, end: int) -> UnifiedFinding:
    return UnifiedFinding(
        title=rule_id,
        description="",
        category=FindingCategory.SECURITY,
        severity=Severity.MEDIUM,
        file_path=path,
        start_line=start,
        end_line=end,
        source=FindingSource.AST_RULES,
        rule_id=rule_id,
    )


def _assert_valid_patch(source: str, rule_id: str, path: str, start: int, end: int) -> str:
    finding = _finding(rule_id, path, start, end)
    proposal = template_patch(finding, source)
    assert proposal is not None, f"{rule_id}: no template patch produced"

    updated, error = apply_proposal(source, proposal)
    assert updated is not None, f"{rule_id}: patch did not apply — {error}"

    analyzer = analyzer_for_path(path)
    ok, message = analyzer.validate_syntax(updated)
    assert ok, f"{rule_id}: patched source does not parse — {message}"
    assert updated != source
    return updated


MULTILINE_REQUEST = '''import requests


def charge(total):
    response = requests.post(
        "https://api.example.com/charges",
        auth=("key", ""),
        data={"amount": total},
    )
    return response
'''

SINGLE_LINE_REQUEST = '''import requests


def fetch(url):
    return requests.get(url)
'''

TRAILING_COMMA_REQUEST = '''import requests


def fetch(url):
    return requests.get(url,)
'''


def test_missing_timeout_multiline_call():
    """Regression: this previously emitted `},, timeout=10)`."""
    updated = _assert_valid_patch(MULTILINE_REQUEST, "python.missing-timeout", "api.py", 5, 9)
    assert "timeout=10" in updated
    assert ",," not in updated
    # Multi-line formatting is preserved rather than collapsed onto one line.
    assert "\n        timeout=10,\n" in updated


def test_missing_timeout_single_line_call():
    updated = _assert_valid_patch(SINGLE_LINE_REQUEST, "python.missing-timeout", "api.py", 5, 5)
    assert "requests.get(url, timeout=10)" in updated


def test_missing_timeout_trailing_comma_call():
    updated = _assert_valid_patch(TRAILING_COMMA_REQUEST, "python.missing-timeout", "api.py", 5, 5)
    assert ",," not in updated
    assert "timeout=10" in updated


def test_missing_timeout_is_not_reapplied():
    source = 'import requests\n\n\ndef fetch(url):\n    return requests.get(url, timeout=5)\n'
    assert template_patch(_finding("python.missing-timeout", "api.py", 5, 5), source) is None


def test_tls_verification_restored():
    source = (
        "import requests\n\n\ndef fetch(url):\n"
        '    return requests.get(url, verify=False, timeout=10)\n'
    )
    updated = _assert_valid_patch(source, "python.tls-verification-disabled", "api.py", 5, 5)
    assert "verify=False" not in updated


def test_yaml_safe_load():
    source = "import yaml\n\n\ndef load(raw):\n    return yaml.load(raw)\n"
    updated = _assert_valid_patch(source, "B506", "conf.py", 5, 5)
    assert "yaml.safe_load(raw)" in updated


def test_eval_becomes_literal_eval():
    source = "def parse(raw):\n    return eval(raw)\n"
    updated = _assert_valid_patch(source, "python.dangerous-call.eval", "parse.py", 2, 2)
    assert "ast.literal_eval(raw)" in updated


def test_bare_except_is_narrowed():
    source = (
        "def run():\n"
        "    try:\n"
        "        work()\n"
        "    except:\n"
        "        pass\n"
    )
    updated = _assert_valid_patch(source, "python.swallowed-exception", "run.py", 4, 5)
    assert "except Exception as exc:" in updated
    assert "raise" in updated


def test_permissive_cors_is_narrowed():
    source = (
        "def setup(app):\n"
        "    app.add_middleware(\n"
        "        CORSMiddleware,\n"
        '        allow_origins=["*"],\n'
        "        allow_credentials=True,\n"
        "    )\n"
    )
    updated = _assert_valid_patch(source, "python.permissive-cors", "conf.py", 2, 6)
    assert '["*"]' not in updated
    assert "settings.frontend_url" in updated


def test_inner_html_becomes_text_content():
    source = (
        "export function render(el, order) {\n"
        "  el.innerHTML = `<h2>${order.id}</h2>`;\n"
        "}\n"
    )
    updated = _assert_valid_patch(source, "js.xss-inner-html", "render.ts", 2, 2)
    assert ".textContent =" in updated


def test_empty_catch_is_filled():
    source = (
        "export async function save(row) {\n"
        "  try {\n"
        "    await db.write(row);\n"
        "  } catch (error) {}\n"
        "}\n"
    )
    updated = _assert_valid_patch(source, "js.empty-catch", "save.ts", 4, 4)
    assert "console.error" in updated
    assert "throw error" in updated


def test_unknown_rule_yields_no_template():
    source = "def noop():\n    return 1\n"
    assert template_patch(_finding("python.some-unmapped-rule", "x.py", 1, 2), source) is None


@pytest.mark.parametrize(
    "rule_id",
    ["secret/generic-assignment", "S105", "B106"],
)
def test_hardcoded_secret_moves_to_environment(rule_id: str):
    source = 'API_KEY = "aK9x7Qw2LmZp4Rt8"\n'
    updated = _assert_valid_patch(source, rule_id, "conf.py", 1, 1)
    assert "os.environ" in updated
    assert "aK9x7Qw2LmZp4Rt8" not in updated
