"""Structured logging with automatic secret redaction."""

from __future__ import annotations

import logging
import re
import sys
from typing import Any

import structlog

from app.core.config import settings

# Patterns scrubbed from every log record before it leaves the process.
_REDACTION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{16,}"), "<redacted:github-token>"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), "<redacted:github-pat>"),
    (re.compile(r"sk-(?:proj-)?[A-Za-z0-9_\-]{20,}"), "<redacted:openai-key>"),
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"), "<redacted:anthropic-key>"),
    (re.compile(r"gsk_[A-Za-z0-9]{20,}"), "<redacted:groq-key>"),
    (re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"), "<redacted:jwt>"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]+?-----END [A-Z ]*PRIVATE KEY-----"), "<redacted:private-key>"),
]

_SENSITIVE_KEYS = {
    "token", "access_token", "refresh_token", "authorization", "password",
    "secret", "api_key", "client_secret", "private_key", "encryption_key",
}


def redact(value: str) -> str:
    for pattern, replacement in _REDACTION_PATTERNS:
        value = pattern.sub(replacement, value)
    return value


def _redaction_processor(_logger: Any, _name: str, event_dict: dict) -> dict:
    for key, value in list(event_dict.items()):
        if key.lower() in _SENSITIVE_KEYS and value:
            event_dict[key] = "<redacted>"
        elif isinstance(value, str):
            event_dict[key] = redact(value)
    return event_dict


def configure_logging() -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)

    renderer = (
        structlog.processors.JSONRenderer()
        if settings.is_production
        else structlog.dev.ConsoleRenderer(colors=False)
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _redaction_processor,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
