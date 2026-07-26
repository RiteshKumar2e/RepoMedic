"""Provider selection with an explicit fallback chain.

Resolution order for a requested provider:

1. The provider named by the repository setting, if configured.
2. The deployment default (``DEFAULT_LLM_PROVIDER``), if configured.
3. Any other configured provider.
4. :class:`HeuristicProvider` — always available, offline, zero cost.
"""

from __future__ import annotations

from app.core.config import settings
from app.core.logging import get_logger
from app.llm.base import LLMProvider
from app.llm.providers import (
    GeminiProvider,
    HeuristicProvider,
    OpenAICompatibleProvider,
)

logger = get_logger(__name__)

DEFAULT_MODELS = {
    "gemini": "gemini-2.5-flash",
    "groq": "llama-3.3-70b-versatile",
    "local": "local",
    "heuristic": "heuristic",
}


def _build(provider: str, model: str | None) -> LLMProvider | None:
    resolved_model = model or DEFAULT_MODELS.get(provider, settings.default_llm_model)
    if provider == "gemini":
        return GeminiProvider(model=resolved_model, api_key=settings.gemini_api_key)
    if provider == "groq":
        return OpenAICompatibleProvider(
            name="groq",
            model=resolved_model,
            api_key=settings.groq_api_key,
            base_url="https://api.groq.com/openai/v1",
        )
    if provider == "local":
        return OpenAICompatibleProvider(
            name="local",
            model=resolved_model,
            api_key="local",
            base_url=settings.local_llm_base_url,
        )
    if provider == "heuristic":
        return HeuristicProvider()
    return None


def get_provider(
    preferred: str | None = None, model: str | None = None
) -> LLMProvider:
    candidates = [
        preferred,
        settings.default_llm_provider,
        "gemini",
        "groq",
        "local",
    ]
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        provider = _build(candidate, model if candidate == (preferred or candidate) else None)
        if provider is not None and provider.available():
            if candidate != (preferred or settings.default_llm_provider):
                logger.info("llm.fallback", requested=preferred, using=candidate)
            return provider

    logger.info("llm.using_heuristic_provider", reason="no LLM API key configured")
    return HeuristicProvider()


def provider_status() -> dict[str, bool]:
    """Which providers are usable right now (surfaced in Settings)."""
    status: dict[str, bool] = {}
    for name in ("gemini", "groq", "local", "heuristic"):
        provider = _build(name, None)
        status[name] = bool(provider and provider.available())
    return status
