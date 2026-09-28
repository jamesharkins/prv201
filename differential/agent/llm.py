"""Thin, cached wrapper around the Anthropic Python SDK (brief §2.6, ADR-003).

* The key comes only from ``DIFFERENTIAL_API_KEY`` and is passed explicitly to the
  SDK client; ``ANTHROPIC_API_KEY`` is never read. The key is never logged,
  cached or written anywhere.
* Every response is cached under ``data/llm_cache/`` keyed by a SHA-256 hash of
  the full request (model, system, messages, tools, output schema, parameters),
  so evaluations replay deterministically. Claude Sonnet 5.5 rejects
  non-default sampling parameters, so caching is the reproducibility mechanism.
* Without a key, cached responses are still served (replay); anything uncached
  raises ``LLMUnavailable`` and callers fall back to offline behaviour.
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from differential.config import LLM_CACHE_DIR, LLMSettings, llm_settings

# List prices per million tokens (input, output), from the model documentation
# fetched 2026-09-28 (docs/research/sources_technical.yaml: claude_pricing).
PRICES = {
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-haiku-4-5": (1.0, 5.0),
}


class LLMUnavailable(RuntimeError):
    """No API key and no cached response for this request."""


@dataclass
class Usage:
    calls: int = 0
    cached_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0
    log: list[dict[str, Any]] = field(default_factory=list)

    def cost_usd(self, model: str) -> float:
        pin, pout = PRICES.get(model, PRICES["claude-sonnet-5-5"])
        return (self.input_tokens * pin + self.output_tokens * pout) / 1e6


def thinking_config(model: str) -> dict[str, Any] | None:
    """Lowest-latency thinking setting per model family (ADR-003)."""
    if model.startswith("claude-sonnet-5-5") or model.startswith("claude-opus-5-5"):
        return {"type": "between_tools"} if model.startswith("claude-sonnet-5-5") else None
    return None


def _hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


class LLMClient:
    def __init__(
        self,
        settings: LLMSettings | None = None,
        cache_dir: Path | None = None,
        sdk_client: Any | None = None,
    ) -> None:
        self.settings = settings or llm_settings()
        self.cache_dir = cache_dir or LLM_CACHE_DIR
        self.usage = Usage()
        self._client = sdk_client
        if self._client is None and self.settings.api_key:
            import anthropic

            self._client = anthropic.Anthropic(api_key=self.settings.api_key, max_retries=3)

    @property
    def live(self) -> bool:
        return self._client is not None

    @property
    def model(self) -> str:
        return self.settings.model

    # ------------------------------------------------------------- caching
    def _cache_path(self, key: str) -> Path:
        return self.cache_dir / key[:2] / f"{key}.json"

    def _cached(self, key: str) -> dict[str, Any] | None:
        p = self._cache_path(key)
        if p.exists():
            return dict(json.loads(p.read_text()))
        return None

    def _store(self, key: str, payload: dict[str, Any], response: dict[str, Any]) -> None:
        p = self._cache_path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        # The request payload never contains the API key.
        p.write_text(json.dumps({"request": payload, "response": response}, indent=1, default=str))

    def create(self, purpose: str, **params: Any) -> dict[str, Any]:
        """messages.create with caching. Returns the response as a plain dict."""
        payload = {"model": self.model, **params}
        key = _hash(payload)
        hit = self._cached(key)
        if hit is not None:
            self.usage.cached_calls += 1
            return dict(hit["response"])
        if not self.live:
            raise LLMUnavailable(f"no API key and no cached response ({purpose})")
        t0 = time.perf_counter()
        resp = self._client.messages.create(model=self.model, **params)  # type: ignore[union-attr]
        dt = time.perf_counter() - t0
        data = resp.to_dict() if hasattr(resp, "to_dict") else dict(resp)
        u = data.get("usage") or {}
        self.usage.calls += 1
        self.usage.input_tokens += int(u.get("input_tokens", 0) or 0)
        self.usage.output_tokens += int(u.get("output_tokens", 0) or 0)
        self.usage.seconds += dt
        self.usage.log.append({"purpose": purpose, "seconds": dt,
                               "input_tokens": u.get("input_tokens"),
                               "output_tokens": u.get("output_tokens")})
        self._store(key, payload, data)
        return data

    # ------------------------------------------------------------ helpers
    @staticmethod
    def text_of(response: dict[str, Any]) -> str:
        return "".join(b.get("text", "") for b in response.get("content", []) if b.get("type") == "text")

    def text(self, system: str, user: str, purpose: str = "text", max_tokens: int = 2000) -> str:
        params: dict[str, Any] = {
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        th = thinking_config(self.model)
        if th:
            params["thinking"] = th
        return self.text_of(self.create(purpose, **params))

    def structured(self, system: str, user: str, schema: dict[str, Any], purpose: str,
                   max_tokens: int = 2000) -> str:
        params: dict[str, Any] = {
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "output_config": {"format": {"type": "json_schema", "schema": schema}},
        }
        return self.text_of(self.create(purpose, **params))

    def vision(self, system: str, image_bytes: bytes, media_type: str, user: str,
               schema: dict[str, Any], purpose: str = "vision", max_tokens: int = 1000) -> str:
        data = base64.standard_b64encode(image_bytes).decode("ascii")
        params: dict[str, Any] = {
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}},
                    {"type": "text", "text": user},
                ],
            }],
            "output_config": {"format": {"type": "json_schema", "schema": schema}},
        }
        return self.text_of(self.create(purpose, **params))

    def tool_loop(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        handler: Callable[[str, dict[str, Any]], Any],
        max_turns: int = 8,
        max_tokens: int = 4000,
        purpose: str = "agent",
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Manual agentic loop (append-only history, tool_choice auto).

        Returns (messages including the final assistant turn, final response).
        ``handler(name, input)`` executes a tool and returns a JSON-serialisable result.
        """
        msgs = list(messages)
        final: dict[str, Any] = {}
        for _ in range(max_turns):
            params: dict[str, Any] = {"max_tokens": max_tokens, "system": system,
                                      "messages": msgs, "tools": tools}
            th = thinking_config(self.model)
            if th:
                params["thinking"] = th
            resp = self.create(purpose, **params)
            final = resp
            content = resp.get("content", [])
            msgs.append({"role": "assistant", "content": content})
            if resp.get("stop_reason") != "tool_use":
                break
            results = []
            for block in content:
                if block.get("type") != "tool_use":
                    continue
                try:
                    out = handler(block["name"], dict(block.get("input") or {}))
                    results.append({"type": "tool_result", "tool_use_id": block["id"],
                                    "content": json.dumps(out, default=str)})
                except Exception as exc:
                    results.append({"type": "tool_result", "tool_use_id": block["id"],
                                    "content": f"Error: {exc}", "is_error": True})
            msgs.append({"role": "user", "content": results})
        return msgs, final
