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
* Prompt caching (ADR-050): live requests mark the fixed prefix (tool schemas and
  system prompt) with a ``cache_control`` breakpoint, and multi-turn tool loops also
  use top-level automatic caching so each turn reads the conversation so far. The
  markers are added only to the request sent to the API; the response-cache key is
  computed without them, so replay and offline behaviour are unchanged.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from differential.config import LLM_CACHE_DIR, LLMSettings, llm_settings

# List prices in USD per million tokens: (input, 5-minute cache write, cache read,
# output), from the pricing documentation fetched 2026-11-17
# (docs/research/sources_technical.yaml: claude_pricing). Claude Haiku 5.5 is the
# row for prompts up to 100,000 tokens; every prompt in this project is far below it.
PRICES = {
    "claude-sonnet-5-5": (2.0, 2.5, 0.10, 10.0),
    "claude-sonnet-5": (2.0, 2.5, 0.20, 10.0),
    "claude-opus-5-5": (4.0, 5.0, 0.20, 20.0),
    "claude-haiku-5-5": (0.10, 0.125, 0.01, 0.50),
    "claude-haiku-4-5": (1.0, 1.25, 0.10, 5.0),
}

EPHEMERAL = {"type": "ephemeral"}


class LLMUnavailable(RuntimeError):
    """No API key and no cached response for this request."""


@dataclass
class Usage:
    """Token counts from the API's usage fields. ``input_tokens`` is the uncached part
    of the prompt; cache writes and reads are counted separately, as the API bills them."""

    calls: int = 0
    cached_calls: int = 0
    input_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0
    log: list[dict[str, Any]] = field(default_factory=list)

    def add(self, u: dict[str, Any]) -> None:
        self.input_tokens += int(u.get("input_tokens") or 0)
        self.cache_write_tokens += int(u.get("cache_creation_input_tokens") or 0)
        self.cache_read_tokens += int(u.get("cache_read_input_tokens") or 0)
        self.output_tokens += int(u.get("output_tokens") or 0)

    def tokens(self) -> dict[str, int]:
        return {"input": self.input_tokens, "cache_write": self.cache_write_tokens,
                "cache_read": self.cache_read_tokens, "output": self.output_tokens}

    def cost_usd(self, model: str) -> float:
        pin, pwrite, pread, pout = PRICES.get(model, PRICES["claude-sonnet-5-5"])
        return (self.input_tokens * pin + self.cache_write_tokens * pwrite
                + self.cache_read_tokens * pread + self.output_tokens * pout) / 1e6


def thinking_config(model: str) -> dict[str, Any] | None:
    """Lowest-latency thinking setting per model family (ADR-003)."""
    if model.startswith("claude-sonnet-5-5") or model.startswith("claude-opus-5-5"):
        return {"type": "between_tools"} if model.startswith("claude-sonnet-5-5") else None
    return None


def _hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def with_cache_control(params: dict[str, Any], conversation: bool = False) -> dict[str, Any]:
    """The request as sent to the API, with prompt-caching breakpoints.

    One explicit breakpoint on the last system block caches the tool schemas and the
    system prompt together (tools render before system). With ``conversation`` the
    top-level automatic breakpoint also caches the growing message history, so each
    turn of a tool loop reads everything before it. Prefixes shorter than the model's
    minimum are simply not cached. ``params`` is not modified.
    """
    out = dict(params)
    system = out.get("system")
    if isinstance(system, str) and system:
        out["system"] = [{"type": "text", "text": system, "cache_control": dict(EPHEMERAL)}]
    elif isinstance(system, list) and system:
        blocks = copy.deepcopy(system)
        blocks[-1]["cache_control"] = dict(EPHEMERAL)
        out["system"] = blocks
    if conversation:
        out["cache_control"] = dict(EPHEMERAL)
    return out


class LLMClient:
    def __init__(
        self,
        settings: LLMSettings | None = None,
        cache_dir: Path | None = None,
        sdk_client: Any | None = None,
    ) -> None:
        self.settings = settings or llm_settings()
        self.cache_dir = cache_dir or LLM_CACHE_DIR
        self.usage = Usage()   # live API calls made by this client (billed now)
        self.served = Usage()  # every response served, live or replayed (its original usage)
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

    def create(self, purpose: str, cache_conversation: bool = False,
               **params: Any) -> dict[str, Any]:
        """messages.create with response caching and prompt caching.

        Returns the response as a plain dict. The response-cache key covers the request
        without its prompt-caching markers, which do not change what the model sees.
        """
        payload = {"model": self.model, **params}
        key = _hash(payload)
        hit = self._cached(key)
        if hit is not None:
            self.usage.cached_calls += 1
            self.served.calls += 1
            self.served.add(dict(hit["response"].get("usage") or {}))
            return dict(hit["response"])
        if not self.live:
            raise LLMUnavailable(f"no API key and no cached response ({purpose})")
        t0 = time.perf_counter()
        request = with_cache_control(params, conversation=cache_conversation)
        resp = self._client.messages.create(model=self.model, **request)  # type: ignore[union-attr]
        dt = time.perf_counter() - t0
        data = resp.to_dict() if hasattr(resp, "to_dict") else dict(resp)
        u = data.get("usage") or {}
        self.usage.calls += 1
        self.usage.add(u)
        self.usage.seconds += dt
        self.served.calls += 1
        self.served.add(u)
        self.usage.log.append({"purpose": purpose, "seconds": dt,
                               "input_tokens": u.get("input_tokens"),
                               "cache_write_tokens": u.get("cache_creation_input_tokens"),
                               "cache_read_tokens": u.get("cache_read_input_tokens"),
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
            resp = self.create(purpose, cache_conversation=True, **params)
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
