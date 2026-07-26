"""Secret detection and redaction.

Two jobs:

1. Report hardcoded credentials as security findings.
2. Guarantee no credential reaches an LLM provider — every string sent outward
   passes through :func:`redact_secrets` first.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from dataclasses import dataclass

# (rule id, human label, compiled pattern, capture group holding the secret)
_PATTERNS: list[tuple[str, str, re.Pattern[str], int]] = [
    ("aws-access-key", "AWS access key ID", re.compile(r"\b((?:AKIA|ASIA)[0-9A-Z]{16})\b"), 1),
    ("aws-secret-key", "AWS secret access key",
     re.compile(r"""(?i)aws_?secret_?access_?key\s*[:=]\s*['"]?([A-Za-z0-9/+=]{40})['"]?"""), 1),
    ("github-token", "GitHub token", re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{16,})\b"), 1),
    ("github-pat", "GitHub fine-grained PAT", re.compile(r"\b(github_pat_[A-Za-z0-9_]{20,})\b"), 1),
    ("openai-key", "OpenAI API key", re.compile(r"\b(sk-(?:proj-)?[A-Za-z0-9_\-]{20,})\b"), 1),
    ("anthropic-key", "Anthropic API key", re.compile(r"\b(sk-ant-[A-Za-z0-9_\-]{20,})\b"), 1),
    ("groq-key", "Groq API key", re.compile(r"\b(gsk_[A-Za-z0-9]{20,})\b"), 1),
    ("slack-token", "Slack token", re.compile(r"\b(xox[baprs]-[A-Za-z0-9\-]{10,})\b"), 1),
    ("stripe-key", "Stripe secret key", re.compile(r"\b(sk_(?:live|test)_[A-Za-z0-9]{16,})\b"), 1),
    ("google-api-key", "Google API key", re.compile(r"\b(AIza[0-9A-Za-z_\-]{35})\b"), 1),
    ("private-key", "Private key block",
     re.compile(r"(-----BEGIN (?:RSA |EC |OPENSSH |PGP |DSA )?PRIVATE KEY-----)"), 1),
    ("jwt", "JSON Web Token",
     re.compile(r"\b(eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,})\b"), 1),
    ("db-url", "Database URL with inline credentials",
     re.compile(r"\b((?:postgres|postgresql|mysql|mongodb(?:\+srv)?|redis|amqp)://[^\s:@/]+:[^\s:@/]+@[^\s'\"]+)"), 1),
    ("generic-assignment", "Hardcoded credential assignment",
     re.compile(
         r"""(?i)\b(?:api[_-]?key|apikey|secret[_-]?key|access[_-]?token|auth[_-]?token"""
         r"""|password|passwd|client[_-]?secret|private[_-]?key)\s*[:=]\s*['"]([^'"\s]{12,})['"]"""
     ), 1),
]

# Values that look like secrets but are placeholders — suppress the noise.
_PLACEHOLDER_RE = re.compile(
    r"(?i)^(?:your[_-]?|my[_-]?|example|placeholder|changeme|dummy|test|fake|sample|xxx+|\.{3,}|<.*>|\$\{.*\}|process\.env)",
)
_PLACEHOLDER_VALUES = {
    "password", "secret", "token", "apikey", "api_key", "null", "none", "undefined",
    "redacted", "removed", "todo", "string",
}


@dataclass(slots=True)
class SecretMatch:
    rule_id: str
    label: str
    line: int
    column: int
    preview: str  # already masked — the raw value never leaves this module
    entropy: float
    file_path: str = ""

    @property
    def confidence(self) -> float:
        base = 0.9 if self.rule_id != "generic-assignment" else 0.65
        if self.entropy >= 4.0:
            base += 0.05
        return min(base, 0.99)


def shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    counts: dict[str, int] = {}
    for char in value:
        counts[char] = counts.get(char, 0) + 1
    length = len(value)
    return -sum((c / length) * math.log2(c / length) for c in counts.values())


def _is_placeholder(value: str) -> bool:
    stripped = value.strip()
    if stripped.lower() in _PLACEHOLDER_VALUES:
        return True
    if _PLACEHOLDER_RE.match(stripped):
        return True
    # Repeated single characters ("aaaaaaaa", "00000000") are never real secrets.
    return len(set(stripped)) <= 2


def mask(value: str) -> str:
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}{'*' * max(4, len(value) - 8)}{value[-4:]}"


def detect_secrets(content: str, file_path: str = "") -> list[SecretMatch]:
    """Find hardcoded credentials in a text blob."""
    matches: list[SecretMatch] = []
    seen: set[tuple[str, int]] = set()

    for line_number, line in enumerate(content.splitlines(), start=1):
        if len(line) > 4000:
            continue
        for rule_id, label, pattern, group in _PATTERNS:
            for match in pattern.finditer(line):
                value = match.group(group)
                if not value or _is_placeholder(value):
                    continue
                entropy = shannon_entropy(value)
                # Generic assignments need real randomness to count.
                if rule_id == "generic-assignment" and entropy < 3.0:
                    continue
                key = (rule_id, line_number)
                if key in seen:
                    continue
                seen.add(key)
                matches.append(
                    SecretMatch(
                        rule_id=rule_id,
                        label=label,
                        line=line_number,
                        column=match.start(group) + 1,
                        preview=mask(value),
                        entropy=round(entropy, 2),
                        file_path=file_path,
                    )
                )
    return matches


def redact_secrets(content: str) -> tuple[str, int]:
    """Replace every detected secret with a placeholder.

    Returns the sanitized text and how many replacements were made. This runs on
    **all** content before it is sent to an LLM provider.
    """
    redacted = content
    count = 0
    for rule_id, _label, pattern, group in _PATTERNS:
        def _replace(match: re.Match[str], _rule=rule_id, _group=group) -> str:
            value = match.group(_group)
            if not value or _is_placeholder(value):
                return match.group(0)
            nonlocal count
            count += 1
            return match.group(0).replace(value, f"<REDACTED:{_rule}>")

        redacted = pattern.sub(_replace, redacted)
    return redacted, count


def redact_all(chunks: Iterable[str]) -> tuple[list[str], int]:
    total = 0
    output: list[str] = []
    for chunk in chunks:
        cleaned, count = redact_secrets(chunk)
        total += count
        output.append(cleaned)
    return output, total
