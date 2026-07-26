"""LLM provider contract, token accounting and cost estimation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable

from app.core.errors import RepoMedicError


class LLMUnavailable(RepoMedicError):
    status_code = 503
    code = "llm_unavailable"


@dataclass(slots=True)
class ChatMessage:
    role: str  # "user" | "assistant"
    content: str


@dataclass(slots=True)
class LLMResponse:
    text: str
    provider: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    stop_reason: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def json_payload(self) -> Any:
        """Parse the response as JSON, tolerating prose and code fences around it."""
        return extract_json(self.text)


@runtime_checkable
class LLMProvider(Protocol):
    name: str
    model: str

    def available(self) -> bool: ...

    async def complete(
        self,
        *,
        system: str,
        messages: list[ChatMessage],
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> LLMResponse: ...


# --------------------------------------------------------------------------- #
# Pricing (USD per 1M tokens). Used for budget enforcement and cost reporting.
# Update as provider pricing changes; unknown models fall back to a mid estimate.
# --------------------------------------------------------------------------- #
PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-5": (15.0, 75.0),
    "claude-sonnet-5": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.6),
    "llama-3.3-70b-versatile": (0.59, 0.79),
    "llama-3.1-8b-instant": (0.05, 0.08),
    "local": (0.0, 0.0),
    "heuristic": (0.0, 0.0),
}
_DEFAULT_PRICE = (3.0, 15.0)


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    prompt_price, completion_price = PRICING.get(model, _DEFAULT_PRICE)
    for known, price in PRICING.items():
        if model.startswith(known):
            prompt_price, completion_price = price
            break
    return round(
        (prompt_tokens / 1_000_000) * prompt_price
        + (completion_tokens / 1_000_000) * completion_price,
        6,
    )


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str) -> Any:
    """Best-effort JSON extraction from a model response."""
    if not text:
        return None
    candidates: list[str] = []

    fenced = _FENCE_RE.findall(text)
    candidates.extend(block.strip() for block in fenced)
    candidates.append(text.strip())

    for opener, closer in (("[", "]"), ("{", "}")):
        start, end = text.find(opener), text.rfind(closer)
        if 0 <= start < end:
            candidates.append(text[start : end + 1])

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
    return None


def approximate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


@dataclass
class UsageTracker:
    """Accumulates token usage and enforces the per-analysis cost budget."""

    budget_usd: float
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost: float = 0.0
    calls: int = 0
    model: str = ""

    def record(self, response: LLMResponse) -> None:
        self.prompt_tokens += response.prompt_tokens
        self.completion_tokens += response.completion_tokens
        self.calls += 1
        self.model = response.model
        self.cost += estimate_cost(response.model, response.prompt_tokens, response.completion_tokens)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def exhausted(self) -> bool:
        return self.budget_usd > 0 and self.cost >= self.budget_usd

    def remaining(self) -> float:
        return max(0.0, self.budget_usd - self.cost)

    def snapshot(self) -> dict[str, float | int | str]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "estimated_cost": round(self.cost, 6),
            "calls": self.calls,
            "budget_usd": self.budget_usd,
            "model": self.model,
        }


Optional_ = Optional  # re-export guard for type checkers
