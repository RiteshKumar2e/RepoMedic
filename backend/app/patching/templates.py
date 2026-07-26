"""Deterministic template fixes.

For a set of defects the correct repair is unambiguous and mechanical. Those get
a template patch: no model call, no cost, no variance, and a confidence prior
higher than any generated suggestion. The LLM fix generator handles everything
that genuinely requires judgement.

Each template receives the exact source line(s) the finding points at and
returns replacement text, or ``None`` if the shape does not match.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Optional

from app.domain.types import PatchProposal, UnifiedFinding
from app.models.enums import RiskLevel


@dataclass(slots=True)
class TemplateResult:
    suggested_code: str
    explanation: str
    expected_impact: str
    side_effects: list[str]
    risk_level: RiskLevel = RiskLevel.LOW


Template = Callable[[str], Optional[TemplateResult]]


# --------------------------------------------------------------------------- #
# Individual templates
# --------------------------------------------------------------------------- #
def _restore_tls_verification(block: str) -> Optional[TemplateResult]:
    if not re.search(r"verify\s*=\s*False", block):
        return None
    updated = re.sub(r",?\s*verify\s*=\s*False", "", block)
    updated = re.sub(r"\(\s*,", "(", updated)
    return TemplateResult(
        suggested_code=updated,
        explanation=(
            "Removed `verify=False` so the TLS certificate chain is validated again. "
            "Without it, any certificate is accepted and the connection offers no "
            "protection against interception."
        ),
        expected_impact=(
            "Requests to hosts with an untrusted certificate now fail loudly instead of "
            "succeeding insecurely."
        ),
        side_effects=[
            "If the endpoint uses a private CA, pass `verify='/path/to/ca-bundle.pem'` "
            "instead of disabling verification."
        ],
    )


def _add_request_timeout(block: str) -> Optional[TemplateResult]:
    if "timeout" in block:
        return None
    match = re.search(r"(requests|httpx)\.(get|post|put|delete|patch|request)\s*\(", block)
    if not match:
        return None
    closing = block.rfind(")")
    if closing == -1:
        return None

    head, tail = block[:closing], block[closing + 1 :]
    stripped = head.rstrip()
    if not stripped:
        return None

    # Detect a multi-line call whose ")" sits on its own line, so the inserted
    # argument matches the existing formatting instead of collapsing the call.
    trailing = head[len(stripped) :]
    closing_on_own_line = "\n" in trailing
    closing_indent = trailing.rsplit("\n", 1)[-1] if closing_on_own_line else ""

    if closing_on_own_line:
        argument_indent = closing_indent + "    "
        for line in block.splitlines()[1:]:
            if line.strip():
                argument_indent = line[: len(line) - len(line.lstrip())]
                break
        separator = "" if stripped.endswith((",", "(")) else ","
        updated = (
            f"{stripped}{separator}\n{argument_indent}timeout=10,\n{closing_indent}){tail}"
        )
    else:
        if stripped.endswith("("):
            separator = ""
        elif stripped.endswith(","):
            separator = " "
        else:
            separator = ", "
        updated = f"{stripped}{separator}timeout=10){tail}"

    return TemplateResult(
        suggested_code=updated,
        explanation=(
            "Added an explicit 10-second timeout. `requests` has no default timeout, so a "
            "hung upstream holds the calling worker open indefinitely."
        ),
        expected_impact="Slow upstreams now raise `Timeout` instead of blocking a worker forever.",
        side_effects=["Tune the value to the upstream's real p99 latency."],
    )


def _safe_yaml_load(block: str) -> Optional[TemplateResult]:
    if "yaml.load" not in block or "safe_load" in block:
        return None
    updated = re.sub(r"yaml\.load\s*\(", "yaml.safe_load(", block)
    updated = re.sub(r",\s*Loader\s*=\s*[\w.]+", "", updated)
    return TemplateResult(
        suggested_code=updated,
        explanation=(
            "Switched to `yaml.safe_load`. The default loader constructs arbitrary Python "
            "objects, which makes parsing an untrusted YAML document remote code execution."
        ),
        expected_impact="YAML parsing is restricted to plain data types.",
        side_effects=["Documents relying on Python-specific YAML tags will now fail to load."],
    )


def _literal_eval(block: str) -> Optional[TemplateResult]:
    if not re.search(r"(?<![\w.])eval\s*\(", block):
        return None
    updated = re.sub(r"(?<![\w.])eval\s*\(", "ast.literal_eval(", block)
    return TemplateResult(
        suggested_code=updated,
        explanation=(
            "Replaced `eval()` with `ast.literal_eval()`, which parses Python literals only "
            "and cannot execute code, calls or attribute access."
        ),
        expected_impact="Malicious input raises `ValueError` instead of executing.",
        side_effects=[
            "Requires `import ast`.",
            "Inputs that were expressions rather than literals will now raise — use `json.loads` "
            "if the data is JSON.",
        ],
        risk_level=RiskLevel.MEDIUM,
    )


def _bare_except(block: str) -> Optional[TemplateResult]:
    if not re.search(r"except\s*:", block):
        return None
    updated = re.sub(r"except\s*:", "except Exception as exc:", block)
    if re.search(r"^\s*pass\s*$", updated, re.M):
        indent = re.search(r"^(\s*)pass", updated, re.M)
        pad = indent.group(1) if indent else "    "
        updated = re.sub(
            r"^\s*pass\s*$",
            f'{pad}logger.exception("unhandled error: %s", exc)\n{pad}raise',
            updated,
            count=1,
            flags=re.M,
        )
    return TemplateResult(
        suggested_code=updated,
        explanation=(
            "Narrowed `except:` to `except Exception` so `KeyboardInterrupt` and `SystemExit` "
            "propagate, and replaced the silent `pass` with a log line plus a re-raise so the "
            "failure is visible."
        ),
        expected_impact="Failures are logged with a traceback instead of disappearing.",
        side_effects=[
            "Requires a module-level `logger`.",
            "Callers now see the exception — confirm they handle it.",
        ],
        risk_level=RiskLevel.MEDIUM,
    )


def _jwt_verify(block: str) -> Optional[TemplateResult]:
    if "jwt.decode(" not in block:
        return None
    if "algorithms" in block and "verify" not in block:
        return None
    updated = re.sub(
        r"jwt\.decode\(\s*([^,)]+)\s*\)",
        r"jwt.decode(\1, secret, algorithms=['HS256'])",
        block,
    )
    if updated == block:
        updated = re.sub(r"(jwt\.decode\([^)]*)\)", r"\1, algorithms=['HS256'])", block)
    if updated == block:
        return None
    return TemplateResult(
        suggested_code=updated,
        explanation=(
            "Token claims are now verified against a signing secret with an explicit algorithm "
            "allowlist. Decoding without verification lets any client forge claims, including "
            "elevated roles."
        ),
        expected_impact="Forged or tampered tokens are rejected.",
        side_effects=[
            "`secret` must be the same value used to sign tokens — load it from configuration.",
            "Adjust the algorithm to match your issuer.",
        ],
        risk_level=RiskLevel.MEDIUM,
    )


def _permissive_cors(block: str) -> Optional[TemplateResult]:
    if '"*"' not in block and "'*'" not in block:
        return None
    if "allow_origins" not in block and "origins" not in block:
        return None
    updated = re.sub(r"\[\s*[\"']\*[\"']\s*\]", "[settings.frontend_url]", block)
    if updated == block:
        return None
    return TemplateResult(
        suggested_code=updated,
        explanation=(
            "Replaced the wildcard origin with an explicit allowlist. `*` lets any website "
            "call this API from a victim's browser."
        ),
        expected_impact="Only the configured frontend origin can make cross-origin calls.",
        side_effects=["Add every legitimate origin (staging, preview deployments) to the list."],
    )


def _hardcoded_secret(block: str) -> Optional[TemplateResult]:
    match = re.search(
        r"""(?i)^(\s*)([A-Za-z_][\w]*)\s*[:=]\s*['"]([^'"]{8,})['"]""", block, re.M
    )
    if not match:
        return None
    indent, name, _value = match.groups()
    env_name = re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_")
    updated = re.sub(
        r"""(?i)^(\s*)([A-Za-z_][\w]*)\s*([:=])\s*['"][^'"]{8,}['"]""",
        rf'\1\2 \3 os.environ["{env_name}"]',
        block,
        count=1,
        flags=re.M,
    )
    return TemplateResult(
        suggested_code=updated,
        explanation=(
            f"Moved `{name}` out of source and into the `{env_name}` environment variable. The "
            "committed value is already compromised and must be rotated separately — this change "
            "stops the next one from leaking."
        ),
        expected_impact="The credential is supplied at deploy time; source contains no secret.",
        side_effects=[
            f"ROTATE the exposed credential now — removing it from source does not remove it from git history.",
            f"Set `{env_name}` in every environment, and add it to `.env.example`.",
            "Requires `import os`.",
        ],
        risk_level=RiskLevel.MEDIUM,
    )


def _dangerous_inner_html(block: str) -> Optional[TemplateResult]:
    if "innerHTML" not in block:
        return None
    updated = re.sub(r"\.innerHTML(\s*)=", r".textContent\1=", block)
    if updated == block:
        return None
    return TemplateResult(
        suggested_code=updated,
        explanation=(
            "Switched `innerHTML` to `textContent`, which inserts the value as text. The browser "
            "no longer parses it as markup, so embedded `<script>` or `onerror` payloads cannot run."
        ),
        expected_impact="User-supplied values render literally instead of executing.",
        side_effects=[
            "If the value is intentionally HTML, sanitise it with DOMPurify rather than reverting."
        ],
    )


def _empty_catch(block: str) -> Optional[TemplateResult]:
    # The catch is usually preceded by the try's closing brace on the same line
    # (`} catch (error) {}`), so that prefix has to be part of the match.
    pattern = re.compile(r"^([ \t]*)(\}\s*)?catch\s*\(([^)]*)\)\s*\{\s*\}", re.M)
    match = pattern.search(block)
    if not match:
        return None

    indent = match.group(1)
    closing_brace = match.group(2) or ""
    binding = (match.group(3).strip() or "error")
    updated = pattern.sub(
        f"{indent}{closing_brace}catch ({binding}) {{\n"
        f"{indent}  console.error('operation failed', {binding});\n"
        f"{indent}  throw {binding};\n"
        f"{indent}}}",
        block,
        count=1,
    )
    return TemplateResult(
        suggested_code=updated,
        explanation=(
            "The empty catch discarded the error. It is now logged with context and rethrown so "
            "the caller can react and the failure is traceable."
        ),
        expected_impact="Failures surface in logs and propagate instead of being silently ignored.",
        side_effects=["Callers must handle the rethrown error — check the call sites."],
        risk_level=RiskLevel.MEDIUM,
    )


# --------------------------------------------------------------------------- #
# Rule → template mapping
# --------------------------------------------------------------------------- #
TEMPLATES: dict[str, Template] = {
    "python.tls-verification-disabled": _restore_tls_verification,
    "B501": _restore_tls_verification,
    "S501": _restore_tls_verification,
    "python.missing-timeout": _add_request_timeout,
    "S113": _add_request_timeout,
    "B506": _safe_yaml_load,
    "S506": _safe_yaml_load,
    "python.dangerous-call.yaml-load": _safe_yaml_load,
    "python.dangerous-call.eval": _literal_eval,
    "B307": _literal_eval,
    "S307": _literal_eval,
    "python.swallowed-exception": _bare_except,
    "E722": _bare_except,
    "js.jwt-unverified": _jwt_verify,
    "js.jwt-missing-algorithms": _jwt_verify,
    "python.permissive-cors": _permissive_cors,
    "js.xss-inner-html": _dangerous_inner_html,
    "js.empty-catch": _empty_catch,
}

# Rule prefixes that map to the hardcoded-secret template.
SECRET_RULE_PREFIXES = ("secret/", "S105", "S106", "S107", "B105", "B106", "B107")


def template_patch(finding: UnifiedFinding, source: str) -> Optional[PatchProposal]:
    """Build a deterministic patch for ``finding``, or ``None`` if no template fits."""
    from app.patching.differ import build_proposal

    template = TEMPLATES.get(finding.rule_id)
    if template is None:
        tail = finding.rule_id.rsplit(".", 1)[-1].rsplit("/", 1)[-1]
        template = TEMPLATES.get(tail)
    if template is None and finding.rule_id.startswith(SECRET_RULE_PREFIXES):
        template = _hardcoded_secret
    if template is None:
        return None

    lines = source.splitlines()
    start = max(1, min(finding.start_line, len(lines)))
    end = max(start, min(finding.end_line, len(lines)))
    block = "\n".join(lines[start - 1 : end])

    result = template(block)
    if result is None or result.suggested_code.strip() == block.strip():
        return None

    proposal = build_proposal(
        file_path=finding.file_path,
        source=source,
        start_line=start,
        end_line=end,
        suggested_code=result.suggested_code,
        explanation=result.explanation,
        expected_impact=result.expected_impact,
        side_effects=result.side_effects,
        generated_by="template",
    )
    if proposal is not None:
        proposal.risk_level = result.risk_level
    return proposal
