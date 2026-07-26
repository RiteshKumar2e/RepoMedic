"""Concrete LLM providers.

* :class:`GeminiProvider` — Google Gemini ``generateContent`` API.
* :class:`OpenAICompatibleProvider` — Groq and any local server that speaks
  ``/chat/completions`` (Ollama, vLLM, LM Studio, llama.cpp). The name refers to
  the wire protocol, which those vendors implement; OpenAI itself is not a
  configured provider.
* :class:`HeuristicProvider` — deterministic offline fallback. It is **not** a
  language model: it applies cross-file heuristics the AST rules do not cover
  and returns the same JSON contract, so the pipeline stays exercisable with no
  API key, no network, and no cost. Findings it produces are labelled as such.
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.llm.base import (
    ChatMessage,
    LLMResponse,
    LLMUnavailable,
    approximate_tokens,
)

logger = get_logger(__name__)

_TIMEOUT = httpx.Timeout(120.0, connect=10.0)


class GeminiProvider:
    """Google Gemini via the native ``generateContent`` endpoint.

    The native endpoint is used rather than Gemini's OpenAI compatibility shim
    because it reports real token counts in ``usageMetadata``, which the cost
    budget depends on.
    """

    name = "gemini"

    def __init__(self, model: str = "gemini-2.5-flash", api_key: str = "") -> None:
        self.model = model
        self._api_key = api_key or settings.gemini_api_key
        self._base_url = settings.gemini_base_url.rstrip("/")

    def available(self) -> bool:
        return bool(self._api_key)

    async def complete(
        self,
        *,
        system: str,
        messages: list[ChatMessage],
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> LLMResponse:
        if not self.available():
            raise LLMUnavailable("GEMINI_API_KEY is not configured")

        payload: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [
                # Gemini names the assistant turn "model", not "assistant".
                {
                    "role": "model" if m.role == "assistant" else "user",
                    "parts": [{"text": m.content}],
                }
                for m in messages
            ],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
                "responseMimeType": "application/json",
            },
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(
                f"{self._base_url}/models/{self.model}:generateContent",
                headers={
                    "x-goog-api-key": self._api_key,
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        if response.status_code >= 400:
            raise LLMUnavailable(
                f"Gemini API error {response.status_code}",
                details={"body": response.text[:400]},
            )
        data = response.json()
        candidates = data.get("candidates") or [{}]
        parts = (candidates[0].get("content") or {}).get("parts") or []
        # Thinking models interleave "thought" parts; only answer parts are text.
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        usage = data.get("usageMetadata", {})
        return LLMResponse(
            text=text,
            provider=self.name,
            model=data.get("modelVersion", self.model),
            prompt_tokens=int(usage.get("promptTokenCount", 0)),
            completion_tokens=int(usage.get("candidatesTokenCount", 0)),
            stop_reason=candidates[0].get("finishReason", ""),
            raw=data,
        )


class OpenAICompatibleProvider:
    """Works with Groq and any local OpenAI-shaped server.

    "OpenAI-compatible" names the ``/chat/completions`` wire protocol, not the
    vendor — OpenAI itself is not a configured provider.
    """

    def __init__(self, *, name: str, model: str, api_key: str, base_url: str) -> None:
        self.name = name
        self.model = model
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    def available(self) -> bool:
        return bool(self._api_key and self._base_url)

    async def complete(
        self,
        *,
        system: str,
        messages: list[ChatMessage],
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> LLMResponse:
        if not self.available():
            raise LLMUnavailable(f"{self.name} provider is not configured")

        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system},
                *[{"role": m.role, "content": m.content} for m in messages],
            ],
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(
                f"{self._base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        if response.status_code >= 400:
            raise LLMUnavailable(
                f"{self.name} API error {response.status_code}",
                details={"body": response.text[:400]},
            )
        data = response.json()
        choices = data.get("choices") or [{}]
        text = (choices[0].get("message") or {}).get("content", "")
        usage = data.get("usage", {})
        return LLMResponse(
            text=text or "",
            provider=self.name,
            model=data.get("model", self.model),
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            stop_reason=choices[0].get("finish_reason", ""),
            raw=data,
        )


class HeuristicProvider:
    """Offline reviewer used when no API key is configured.

    It answers the reviewer prompt contract with deterministic cross-cutting
    checks over the supplied diff: missing test coverage for changed source
    files, unresolved TODO/FIXME markers introduced by the change, layering
    violations inferred from import paths, and oversized new functions. It never
    claims to be a language model — the orchestrator labels its findings
    ``heuristic`` and the scoring layer discounts them accordingly.
    """

    name = "heuristic"
    model = "heuristic"

    def available(self) -> bool:
        return True

    async def complete(
        self,
        *,
        system: str,
        messages: list[ChatMessage],
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> LLMResponse:
        prompt = "\n".join(m.content for m in messages)
        reviewer = _reviewer_from_system(system)
        findings = _heuristic_findings(prompt, reviewer)
        text = json.dumps({"findings": findings}, indent=2)
        return LLMResponse(
            text=text,
            provider=self.name,
            model=self.model,
            prompt_tokens=approximate_tokens(prompt + system),
            completion_tokens=approximate_tokens(text),
            stop_reason="end_turn",
        )


# --------------------------------------------------------------------------- #
# Heuristic reviewer implementation
# --------------------------------------------------------------------------- #
_DIFF_HEADER_RE = re.compile(r"^### (?P<path>\S+) \((?P<status>\w+)")
_ADDED_RE = re.compile(r"^\+(?!\+\+)(?P<content>.*)$")
_TODO_RE = re.compile(r"(?i)\b(todo|fixme|hack|xxx)\b[: ]")
_FUNC_DEF_RE = re.compile(r"^\s*(?:async\s+)?(?:def|function|const\s+\w+\s*=\s*(?:async\s*)?\()")

_SOURCE_SUFFIXES = (".py", ".ts", ".tsx", ".js", ".jsx")
_TEST_MARKERS = ("test_", "_test.", ".test.", ".spec.", "/tests/", "__tests__")

# Layering rules inferred from conventional directory names.
_LAYER_ORDER = {"api": 0, "routers": 0, "routes": 0, "services": 1, "domain": 2, "models": 3, "db": 3}


def _reviewer_from_system(system: str) -> str:
    lowered = system.lower()
    for reviewer in ("architecture", "security", "performance", "reliability", "testing"):
        if reviewer in lowered:
            return reviewer
    return "generic"


def _parse_diff_sections(prompt: str) -> dict[str, list[tuple[int, str]]]:
    """Map file path → list of ``(line_number_hint, added_line)``."""
    sections: dict[str, list[tuple[int, str]]] = {}
    current: str | None = None
    line_number = 0
    for raw in prompt.splitlines():
        header = _DIFF_HEADER_RE.match(raw)
        if header:
            current = header.group("path")
            sections.setdefault(current, [])
            line_number = 0
            continue
        if current is None:
            continue
        if raw.startswith("@@"):
            match = re.search(r"\+(\d+)", raw)
            line_number = int(match.group(1)) if match else 0
            continue
        added = _ADDED_RE.match(raw)
        if added:
            line_number += 1
            sections[current].append((line_number, added.group("content")))
        elif raw.startswith(" ") or raw.startswith("-"):
            if raw.startswith(" "):
                line_number += 1
    return sections


def _heuristic_findings(prompt: str, reviewer: str) -> list[dict]:
    sections = _parse_diff_sections(prompt)
    findings: list[dict] = []
    changed_paths = list(sections)

    if reviewer == "testing":
        tests_changed = [p for p in changed_paths if any(m in p for m in _TEST_MARKERS)]
        source_changed = [
            p for p in changed_paths
            if p.endswith(_SOURCE_SUFFIXES) and not any(m in p for m in _TEST_MARKERS)
        ]
        for path in source_changed:
            stem = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
            if any(stem in test_path for test_path in tests_changed):
                continue
            findings.append(
                {
                    "title": f"No test accompanies the change to {path}",
                    "description": (
                        f"`{path}` was modified but no test file referencing `{stem}` changed in "
                        "this pull request. New behaviour ships without a regression guard, so a "
                        "later refactor can silently revert it."
                    ),
                    "category": "testing",
                    "severity": "medium",
                    "file_path": path,
                    "start_line": 1,
                    "end_line": 1,
                    "confidence": 0.7,
                    "risk": "Regressions in this code path will not be caught by CI.",
                    "recommendation": (
                        f"Add tests covering the new branches in `{stem}`, including the failure "
                        "and boundary cases."
                    ),
                    "rule_id": "heuristic.missing-test",
                }
            )

    if reviewer in ("architecture", "generic"):
        for path, added in sections.items():
            layer = _layer_of(path)
            if layer is None:
                continue
            for line_number, content in added:
                match = re.search(r"from\s+([\w.]+)\s+import|import\s+([\w./]+)|from\s+['\"]([^'\"]+)['\"]", content)
                if not match:
                    continue
                target = next((g for g in match.groups() if g), "")
                target_layer = _layer_of(target.replace(".", "/"))
                if target_layer is None or target_layer >= layer:
                    continue
                findings.append(
                    {
                        "title": f"Layering violation: {path} imports from a higher layer",
                        "description": (
                            f"`{path}` sits in the `{_layer_name(layer)}` layer but imports "
                            f"`{target}` from the `{_layer_name(target_layer)}` layer. Dependencies "
                            "should point inward; this edge creates a cycle risk and makes the "
                            "lower layer untestable in isolation."
                        ),
                        "category": "architecture",
                        "severity": "medium",
                        "file_path": path,
                        "start_line": line_number,
                        "end_line": line_number,
                        "confidence": 0.55,
                        "risk": "Circular dependencies and modules that cannot be tested standalone.",
                        "recommendation": (
                            "Invert the dependency: define the interface in the lower layer and "
                            "inject the implementation from the composition root."
                        ),
                        "rule_id": "heuristic.layering-violation",
                    }
                )
                break

    if reviewer in ("reliability", "generic"):
        for path, added in sections.items():
            for line_number, content in added:
                if _TODO_RE.search(content):
                    findings.append(
                        {
                            "title": "Unresolved TODO introduced by this change",
                            "description": (
                                f"The change adds `{content.strip()[:120]}`. Markers merged into the "
                                "default branch tend to become permanent; if the work is required "
                                "for correctness, it is a known defect shipping to production."
                            ),
                            "category": "reliability",
                            "severity": "low",
                            "file_path": path,
                            "start_line": line_number,
                            "end_line": line_number,
                            "confidence": 0.8,
                            "risk": "Known-incomplete behaviour reaches production undocumented.",
                            "recommendation": "Complete the work or link a tracked issue in the comment.",
                            "rule_id": "heuristic.unresolved-todo",
                        }
                    )
                    break

    if reviewer in ("performance", "generic"):
        for path, added in sections.items():
            if len(added) > 120:
                findings.append(
                    {
                        "title": f"Large single-file change in {path} ({len(added)} added lines)",
                        "description": (
                            f"{len(added)} lines were added to one file in this pull request. Large "
                            "single-file additions are correlated with missed review defects and "
                            "usually indicate more than one responsibility landing at once."
                        ),
                        "category": "code_quality",
                        "severity": "low",
                        "file_path": path,
                        "start_line": added[0][0] if added else 1,
                        "end_line": added[-1][0] if added else 1,
                        "confidence": 0.6,
                        "risk": "Review fatigue; defects slip through in high-volume diffs.",
                        "recommendation": "Split cohesive units into separate modules and pull requests.",
                        "rule_id": "heuristic.large-change",
                    }
                )
    return findings


def _layer_of(path: str) -> int | None:
    for segment in path.split("/"):
        if segment in _LAYER_ORDER:
            return _LAYER_ORDER[segment]
    return None


def _layer_name(level: int) -> str:
    return {0: "api", 1: "service", 2: "domain", 3: "data"}.get(level, "unknown")
