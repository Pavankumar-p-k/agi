"""Model Adapters — common interface for calling different LLM providers.

Adapters support two modes:
  - generate() with tool schemas → used by +Architecture mode
  - generate() without tool schemas → used by raw mode

Current implementations:
  - OllamaAdapter: direct HTTP to Ollama SSE endpoint
  - OpenAIAdapter: OpenAI-compatible API (OpenAI, Groq, OpenRouter)
  - AnthropicAdapter: Anthropic Messages API
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


# ── Base Adapter ────────────────────────────────────────────────────


class ModelAdapter(ABC):
    """Abstract interface for LLM model adapters.

    Subclasses implement the actual API call for each provider.
    """

    def __init__(self, model_id: str, endpoint: str, max_tokens: int = 4096, temperature: float = 0.0):
        self.model_id = model_id
        self.endpoint = endpoint.rstrip("/")
        self.max_tokens = max_tokens
        self.temperature = temperature

    @abstractmethod
    async def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        timeout: int = 120,
    ) -> tuple[str, list[dict[str, Any]]]:
        """Call the model and return (content, tool_calls).

        Args:
            messages: conversation history in OpenAI format
            tools: optional list of tool schemas (OpenAI function-calling format)
            timeout: request timeout in seconds

        Returns:
            (content, tool_calls) where content is the text response and
            tool_calls is a list of {"name": ..., "arguments": {...}} dicts.
        """
        ...

    async def generate_raw(
        self,
        prompt: str,
        timeout: int = 120,
    ) -> str:
        """Simple single-turn prompt (no tool schemas). Used for raw mode."""
        messages = [{"role": "user", "content": prompt}]
        content, _ = await self.generate(messages, tools=None, timeout=timeout)
        return content


# ── Ollama Adapter ──────────────────────────────────────────────────


class OllamaAdapter(ModelAdapter):
    """Adapter for Ollama's native SSE streaming API."""

    async def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        timeout: int = 120,
    ) -> tuple[str, list[dict[str, Any]]]:
        import httpx

        payload: dict[str, Any] = {
            "model": self.model_id,
            "messages": messages,
            "stream": True,
            "options": {
                "num_predict": self.max_tokens,
                "temperature": self.temperature,
            },
        }
        if tools:
            payload["tools"] = tools

        full_content = ""
        tool_calls: list[dict[str, Any]] = []

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST", f"{self.endpoint}/api/chat", json=payload,
                ) as resp:
                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        msg = chunk.get("message", {})
                        if msg.get("content"):
                            full_content += msg["content"]
                        if msg.get("tool_calls"):
                            for tc in msg["tool_calls"]:
                                name = tc["function"]["name"]
                                args_raw = tc["function"].get("arguments", {})
                                if isinstance(args_raw, str):
                                    try:
                                        args_raw = json.loads(args_raw)
                                    except json.JSONDecodeError:
                                        args_raw = {}
                                tool_calls.append({"name": name, "arguments": args_raw})
        except Exception as e:
            logger.warning("Ollama call failed: %s", e)
            return "", []

        return full_content, tool_calls


# ── OpenAI-Compatible Adapter ───────────────────────────────────────


class OpenAIAdapter(ModelAdapter):
    """Adapter for OpenAI-compatible chat completion APIs.

    Supports: OpenAI, Groq, OpenRouter, etc.
    Uses the `api_key` from environment or passed explicitly.
    """

    def __init__(
        self,
        model_id: str,
        endpoint: str,
        api_key: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ):
        super().__init__(model_id, endpoint, max_tokens, temperature)
        self.api_key = api_key

    async def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        timeout: int = 120,
    ) -> tuple[str, list[dict[str, Any]]]:
        import httpx

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload: dict[str, Any] = {
            "model": self.model_id,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        if tools:
            payload["tools"] = tools

        full_content = ""
        tool_calls: list[dict[str, Any]] = []

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    f"{self.endpoint}/v1/chat/completions",
                    headers=headers,
                    json=payload,
                )
                data = resp.json()
                choice = data.get("choices", [{}])[0]
                msg = choice.get("message", {})
                full_content = msg.get("content", "") or ""
                if msg.get("tool_calls"):
                    for tc in msg["tool_calls"]:
                        name = tc["function"]["name"]
                        args_raw = tc["function"].get("arguments", "{}")
                        if isinstance(args_raw, str):
                            try:
                                args_raw = json.loads(args_raw)
                            except json.JSONDecodeError:
                                args_raw = {}
                        tool_calls.append({"name": name, "arguments": args_raw})
        except Exception as e:
            logger.warning("OpenAI call failed: %s", e)
            return "", []

        return full_content, tool_calls


# ── Anthropic Adapter ───────────────────────────────────────────────


class AnthropicAdapter(ModelAdapter):
    """Adapter for Anthropic Messages API.

    Requires ANTHROPIC_API_KEY environment variable.
    Converts OpenAI-format tool schemas to Anthropic tool_use format.
    """

    def __init__(
        self,
        model_id: str,
        endpoint: str = "https://api.anthropic.com",
        api_key: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ):
        super().__init__(model_id, endpoint, max_tokens, temperature)
        self.api_key = api_key

    async def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        timeout: int = 120,
    ) -> tuple[str, list[dict[str, Any]]]:
        import httpx

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }

        # Extract system message if present
        system: str | None = None
        anon_messages = []
        for m in messages:
            if m.get("role") == "system":
                system = m["content"]
            else:
                anon_messages.append(m)

        payload: dict[str, Any] = {
            "model": self.model_id,
            "messages": anon_messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        if system:
            payload["system"] = system

        if tools:
            # Convert OpenAI tool format to Anthropic format
            anthropic_tools = []
            for t in tools:
                fn = t.get("function", t)
                anthropic_tools.append({
                    "name": fn.get("name", ""),
                    "description": fn.get("description", ""),
                    "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
                })
            payload["tools"] = anthropic_tools

        full_content = ""
        tool_calls: list[dict[str, Any]] = []

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    f"{self.endpoint}/v1/messages",
                    headers=headers,
                    json=payload,
                )
                data = resp.json()
                for block in data.get("content", []):
                    if block.get("type") == "text":
                        full_content += block.get("text", "")
                    elif block.get("type") == "tool_use":
                        tool_calls.append({
                            "name": block.get("name", ""),
                            "arguments": block.get("input", {}),
                        })
        except Exception as e:
            logger.warning("Anthropic call failed: %s", e)
            return "", []

        return full_content, tool_calls


# ── Factory ─────────────────────────────────────────────────────────


def create_adapter(
    model_id: str,
    provider: str = "ollama",
    endpoint: str = "",
    api_key: str = "",
    **kwargs: Any,
) -> ModelAdapter:
    """Create the appropriate adapter for a given provider.

    Args:
        model_id: model identifier (e.g. "qwen2.5:7b", "gpt-4o")
        provider: one of "ollama", "openai", "anthropic"
        endpoint: API endpoint URL (defaults per provider)
        api_key: API key (falls back to env var per provider)

    Returns:
        Configured ModelAdapter instance.
    """
    provider = provider.lower()

    if provider == "ollama":
        url = endpoint or "http://localhost:11434"
        return OllamaAdapter(model_id, url, **kwargs)

    elif provider == "openai":
        url = endpoint or "https://api.openai.com"
        key = api_key or ""
        return OpenAIAdapter(model_id, url, api_key=key, **kwargs)

    elif provider in ("anthropic", "claude"):
        url = endpoint or "https://api.anthropic.com"
        key = api_key or ""
        return AnthropicAdapter(model_id, url, api_key=key, **kwargs)

    else:
        raise ValueError(f"Unknown provider: {provider}. Supported: ollama, openai, anthropic")
