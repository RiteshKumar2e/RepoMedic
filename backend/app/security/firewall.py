"""AI firewall: prompt-injection detection and context sanitisation.

Repository content is **untrusted input**. Anything a contributor can write —
source comments, README text, PR descriptions, test fixtures — can attempt to
steer the reviewer agents. This module:

1. Detects injection attempts and reports them as security findings.
2. Neutralises the payload before the text is placed in a prompt.
3. Wraps every untrusted blob in explicit data delimiters so the model is told,
   structurally, that the content is data and not instructions.
"""

from __future__ import annotations

import base64
import binascii
import re
import unicodedata
from dataclasses import dataclass, field

# Direct instruction-override attempts.
_INSTRUCTION_PATTERNS: list[tuple[str, re.Pattern[str], float]] = [
    ("ignore-previous", re.compile(r"(?i)\b(ignore|disregard|forget)\s+(all\s+)?(the\s+)?(previous|prior|above|earlier|system)\s+(instructions?|prompts?|rules?|messages?)"), 0.95),
    ("reveal-system-prompt", re.compile(r"(?i)\b(reveal|print|show|output|repeat|dump)\s+(me\s+)?(your|the)\s+(system\s+)?(prompt|instructions?|rules?|configuration)"), 0.95),
    ("exfiltrate-secrets", re.compile(r"(?i)\b(send|post|upload|exfiltrate|leak|email|transmit)\s+(the\s+)?(repo(sitory)?|env(ironment)?|\.env|secrets?|credentials?|tokens?|api[\s_-]?keys?)"), 0.98),
    ("approve-code", re.compile(r"(?i)\b(approve|accept|pass|lgtm)\s+(this|the)\s+(code|pr|pull request|change|patch)\b"), 0.8),
    ("mark-safe", re.compile(r"(?i)\b(mark|flag|treat|classify|report)\s+(this|it|the\s+\w+)\s+(as\s+)?(safe|secure|clean|not\s+a\s+(vulnerability|issue)|false\s+positive)"), 0.9),
    ("suppress-findings", re.compile(r"(?i)\b(do\s+not|don't|never)\s+(report|flag|mention|include|raise)\s+"), 0.85),
    ("role-override", re.compile(r"(?i)\b(you\s+are\s+now|from\s+now\s+on\s+you|act\s+as|pretend\s+to\s+be|new\s+persona)\b"), 0.7),
    ("developer-message", re.compile(r"(?i)<\s*/?\s*(system|assistant|developer)\s*>|\[\s*(system|assistant|developer)\s*\]|###\s*(system|instruction)"), 0.75),
    ("tool-abuse", re.compile(r"(?i)\b(execute|run|eval)\s+(the\s+)?following\s+(command|code|shell|script)"), 0.8),
]

# Zero-width / bidirectional control characters used to hide payloads.
_INVISIBLE_CHARS = {
    "​", "‌", "‍", "⁠", "﻿",
    "‪", "‫", "‬", "‭", "‮",
    "⁦", "⁧", "⁨", "⁩",
}
_INVISIBLE_RE = re.compile("[" + "".join(_INVISIBLE_CHARS) + "]")

_HTML_COMMENT_RE = re.compile(r"<!--(.*?)-->", re.DOTALL)
_BASE64_RE = re.compile(r"\b([A-Za-z0-9+/]{40,}={0,2})\b")

DATA_OPEN = "<<<UNTRUSTED_REPOSITORY_CONTENT>>>"
DATA_CLOSE = "<<<END_UNTRUSTED_REPOSITORY_CONTENT>>>"


@dataclass(slots=True)
class InjectionMatch:
    rule_id: str
    description: str
    line: int
    excerpt: str
    confidence: float
    technique: str = "instruction"


@dataclass(slots=True)
class FirewallReport:
    matches: list[InjectionMatch] = field(default_factory=list)
    sanitized: str = ""
    invisible_characters_removed: int = 0
    delimiters_stripped: int = 0

    @property
    def is_suspicious(self) -> bool:
        return bool(self.matches)

    @property
    def max_confidence(self) -> float:
        return max((m.confidence for m in self.matches), default=0.0)


def _decode_base64_candidates(text: str) -> list[tuple[str, str]]:
    """Return ``(payload, decoded)`` for base64 blobs that decode to readable text."""
    decoded: list[tuple[str, str]] = []
    for match in _BASE64_RE.finditer(text):
        candidate = match.group(1)
        try:
            raw = base64.b64decode(candidate + "=" * (-len(candidate) % 4), validate=True)
            text_value = raw.decode("utf-8")
        except (binascii.Error, UnicodeDecodeError, ValueError):
            continue
        printable = sum(c.isprintable() or c.isspace() for c in text_value)
        if len(text_value) >= 12 and printable / len(text_value) > 0.9:
            decoded.append((candidate, text_value))
    return decoded


def scan_for_injection(content: str, *, source_label: str = "content") -> FirewallReport:
    """Detect prompt-injection attempts in untrusted text."""
    report = FirewallReport()
    if not content:
        report.sanitized = ""
        return report

    normalized = unicodedata.normalize("NFKC", content)
    lines = normalized.splitlines()

    # 1. Direct instruction patterns.
    for index, line in enumerate(lines, start=1):
        for rule_id, pattern, confidence in _INSTRUCTION_PATTERNS:
            if pattern.search(line):
                report.matches.append(
                    InjectionMatch(
                        rule_id=rule_id,
                        description=f"Instruction-like directive found in {source_label}",
                        line=index,
                        excerpt=line.strip()[:200],
                        confidence=confidence,
                    )
                )

    # 2. Hidden HTML comments carrying instructions.
    for match in _HTML_COMMENT_RE.finditer(normalized):
        inner = match.group(1)
        for rule_id, pattern, confidence in _INSTRUCTION_PATTERNS:
            if pattern.search(inner):
                report.matches.append(
                    InjectionMatch(
                        rule_id=f"hidden-html:{rule_id}",
                        description="Instructions concealed inside an HTML comment",
                        line=normalized[: match.start()].count("\n") + 1,
                        excerpt=inner.strip()[:200],
                        confidence=min(0.99, confidence + 0.05),
                        technique="hidden-html",
                    )
                )
                break

    # 3. Base64-encoded instructions.
    for payload, decoded_text in _decode_base64_candidates(normalized):
        # Encoded payloads score a flat high confidence: deliberately obfuscating
        # an instruction is itself the signal, whatever the underlying pattern.
        for rule_id, pattern, _confidence in _INSTRUCTION_PATTERNS:
            if pattern.search(decoded_text):
                report.matches.append(
                    InjectionMatch(
                        rule_id=f"base64:{rule_id}",
                        description="Base64-encoded instructions embedded in repository content",
                        line=normalized[: normalized.find(payload)].count("\n") + 1,
                        excerpt=decoded_text.strip()[:200],
                        confidence=0.9,
                        technique="encoded",
                    )
                )
                break

    # 4. Invisible / bidi obfuscation.
    invisible_hits = _INVISIBLE_RE.findall(content)
    if invisible_hits:
        line = next(
            (i for i, ln in enumerate(content.splitlines(), 1) if _INVISIBLE_RE.search(ln)), 1
        )
        report.matches.append(
            InjectionMatch(
                rule_id="unicode-obfuscation",
                description=(
                    f"{len(invisible_hits)} zero-width or bidirectional control characters found — "
                    "a known technique for hiding text from human reviewers"
                ),
                line=line,
                excerpt="<invisible characters>",
                confidence=0.85,
                technique="unicode",
            )
        )

    report.sanitized, report.invisible_characters_removed, report.delimiters_stripped = _neutralize(
        normalized
    )
    return report


def _neutralize(text: str) -> tuple[str, int, int]:
    """Strip invisible characters and break out of our own data delimiters."""
    invisible_count = len(_INVISIBLE_RE.findall(text))
    cleaned = _INVISIBLE_RE.sub("", text)

    delimiters_stripped = 0
    for token in (DATA_OPEN, DATA_CLOSE):
        delimiters_stripped += cleaned.count(token)
        cleaned = cleaned.replace(token, "[delimiter-removed]")
    return cleaned, invisible_count, delimiters_stripped  # type: ignore[return-value]


def sanitize_for_llm(content: str, *, source_label: str = "file") -> tuple[str, FirewallReport]:
    """Return prompt-safe text wrapped in explicit data delimiters."""
    from app.security.secrets import redact_secrets

    report = scan_for_injection(content, source_label=source_label)
    redacted, _ = redact_secrets(report.sanitized)
    wrapped = f"{DATA_OPEN}\n{redacted}\n{DATA_CLOSE}"
    return wrapped, report
