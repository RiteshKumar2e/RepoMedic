"""Ad-hoc harness: run a template fix against the fixture and report why it failed.

Usage: python scripts/debug_template.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.analyzers.registry import analyzer_for_path  # noqa: E402
from app.domain.types import UnifiedFinding  # noqa: E402
from app.models.enums import FindingCategory, FindingSource, Severity  # noqa: E402
from app.patching.differ import apply_proposal  # noqa: E402
from app.patching.templates import template_patch  # noqa: E402

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "ecommerce-api-demo"
TARGET = "app/routes/checkout.py"

source = (FIXTURE / TARGET).read_text(encoding="utf-8")
lines = source.splitlines()

# Locate the requests.post call the missing-timeout rule fires on.
start = next(i for i, line in enumerate(lines, 1) if "charge = requests.post(" in line)
end = next(i for i in range(start, len(lines) + 1) if lines[i - 1].strip() == ")")

finding = UnifiedFinding(
    title="Outbound HTTP call without a timeout",
    description="",
    category=FindingCategory.RELIABILITY,
    severity=Severity.MEDIUM,
    file_path=TARGET,
    start_line=start,
    end_line=end,
    source=FindingSource.AST_RULES,
    rule_id="python.missing-timeout",
)

print(f"--- finding range: {start}-{end}")
print("--- original block ---")
print("\n".join(lines[start - 1 : end]))

proposal = template_patch(finding, source)
if proposal is None:
    print("\n!! template produced no proposal")
    raise SystemExit(1)

print("\n--- suggested block ---")
print(proposal.suggested_code)

updated, error = apply_proposal(source, proposal)
print("\n--- apply_proposal ---")
print("error:", error or "(none)")

if updated is not None:
    analyzer = analyzer_for_path(TARGET)
    ok, message = analyzer.validate_syntax(updated)
    print("syntax ok:", ok, message)
else:
    # Show exactly what the syntax checker rejects.
    candidate = "\n".join(
        lines[: start - 1] + proposal.suggested_code.splitlines() + lines[end:]
    )
    analyzer = analyzer_for_path(TARGET)
    ok, message = analyzer.validate_syntax(candidate)
    print("direct splice syntax ok:", ok, message)
    print("\n--- spliced region ---")
    print("\n".join(candidate.splitlines()[start - 3 : end + 3]))
