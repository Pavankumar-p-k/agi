"""The model adapter: the one place in MJ where a prompt leaves the process.

Decided 2026-10-22 (docs/09 §5): **local-first**, behind an
OpenAI-compatible adapter, hosted providers pluggable. The contract is four
environment variables, read here and nowhere else:

    MJ_MODEL_PROVIDER        provider label; its *presence* is the enable
                             switch ("ollama", "lmstudio", "openai-compatible",
                             "hosted-..."). Unset => no model is ever contacted.
    MJ_MODEL_BASE_URL        OpenAI-compatible base URL, e.g.
                             http://127.0.0.1:11434/v1
    MJ_MODEL_NAME            model name, e.g. llama3.1:8b
    MJ_MODEL_API_KEY         optional bearer token; local servers ignore it
    MJ_MODEL_TIMEOUT_S       request deadline (default 30; <= 0 -> default)
    MJ_MODEL_RESPONSE_FORMAT json_schema (default) | json_object | off

What this module deliberately is *not*: a capability, a planner, a tool
runner, or a place that can read the store, the policy file, the broker or
the audit log. It sends exactly one chat request and returns the parsed JSON
object. Everything the model says is therefore untrusted input, which is why
`mj.brain.reasoner` validates it against the registry before a plan exists.

Only the standard library is used (urllib) so the hashed lockfile does not
grow. There is no retry loop: a model failure falls back to the deterministic
planner, or to one question for the user — cheaper and more honest than
retrying a flaky endpoint inside a planning step.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

DEFAULT_TIMEOUT_S = 30.0
RESPONSE_FORMATS = ("json_schema", "json_object", "off")
#: A model response larger than this is not a plan; refuse to buffer it.
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class ModelError(RuntimeError):
    """Transport, configuration or response-shape failure.

    Never carries the API key: messages are built from exception types and
    HTTP status codes, not from the request.
    """


@dataclass(frozen=True)
class ModelConfig:
    provider: str
    base_url: str
    model: str
    api_key: str | None
    timeout_s: float
    response_format: str

    @property
    def endpoint(self) -> str:
        return self.base_url.rstrip("/") + "/chat/completions"

    def describe(self) -> dict[str, Any]:
        """Public description — for `mj status`, logs and audit payloads.

        Carries no secret: the presence of a key is reported, never its value.
        """
        return {
            "provider": self.provider,
            "endpoint": self.endpoint,
            "model": self.model,
            "api_key_set": bool(self.api_key),
            "timeout_s": self.timeout_s,
            "response_format": self.response_format,
        }


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def _timeout() -> float:
    raw = _env("MJ_MODEL_TIMEOUT_S")
    if not raw:
        return DEFAULT_TIMEOUT_S
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_TIMEOUT_S
    return value if value > 0 else DEFAULT_TIMEOUT_S


def config_from_env() -> ModelConfig | None:
    """Return the configured model, or None when no provider is configured.

    When MJ_MODEL_PROVIDER *is* set but the rest is incomplete, this raises
    ModelError instead of silently pretending no model exists: a half-typed
    configuration is a mistake the operator should see, not a quiet downgrade.
    """
    provider = _env("MJ_MODEL_PROVIDER")
    if not provider:
        return None
    base_url = _env("MJ_MODEL_BASE_URL")
    model_name = _env("MJ_MODEL_NAME")
    missing = [
        name
        for name, value in (
            ("MJ_MODEL_BASE_URL", base_url),
            ("MJ_MODEL_NAME", model_name),
        )
        if not value
    ]
    if missing:
        raise ModelError(
            f"MJ_MODEL_PROVIDER={provider!r} is set but {', '.join(missing)} is empty; "
            "a model is only used when the whole contract is present"
        )
    if not base_url.startswith(("http://", "https://")):
        raise ModelError(
            f"MJ_MODEL_BASE_URL must be an http(s) URL (got {base_url!r}); "
            "e.g. http://127.0.0.1:11434/v1"
        )
    fmt = _env("MJ_MODEL_RESPONSE_FORMAT").lower() or "json_schema"
    if fmt not in RESPONSE_FORMATS:
        raise ModelError(
            f"MJ_MODEL_RESPONSE_FORMAT={fmt!r} is not one of {RESPONSE_FORMATS}"
        )
    return ModelConfig(
        provider=provider,
        base_url=base_url,
        model=model_name,
        api_key=_env("MJ_MODEL_API_KEY") or None,
        timeout_s=_timeout(),
        response_format=fmt,
    )


def _request_body(
    cfg: ModelConfig,
    system: str,
    user: str,
    schema: dict[str, Any],
    max_tokens: int,
    temperature: float,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": cfg.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if cfg.response_format == "json_schema":
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "mj_plan", "strict": True, "schema": schema},
        }
    elif cfg.response_format == "json_object":
        body["response_format"] = {"type": "json_object"}
    return body


def _extract_content(raw: str) -> str:
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ModelError(
            f"model response is larger than {MAX_RESPONSE_BYTES} bytes; refusing to parse it"
        )
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ModelError(f"model response was not JSON: {exc.msg}") from None
    try:
        content = envelope["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise ModelError(
            "model response has no choices[0].message.content (not an "
            "OpenAI-compatible chat completion)"
        ) from None
    if not isinstance(content, str):
        raise ModelError("model content is not a string")
    return content


def _strip_fences(text: str) -> str:
    """Tolerate ```json ... ``` around the object; some local servers add it."""
    body = text.strip()
    if body.startswith("```"):
        body = body.split("\n", 1)[1] if "\n" in body else ""
        if body.rstrip().endswith("```"):
            body = body.rstrip()[: -len("```")]
    return body.strip()


def parse_json_object(content: str) -> dict[str, Any]:
    """Parse the model's content as one JSON object (no prose, no array)."""
    body = _strip_fences(content)
    start, end = body.find("{"), body.rfind("}")
    if start < 0 or end < start:
        raise ModelError("model content contains no JSON object")
    try:
        data = json.loads(body[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ModelError(f"model content is not valid JSON: {exc.msg}") from None
    if not isinstance(data, dict):
        raise ModelError("model content is not a JSON object")
    return data


def chat_json(
    cfg: ModelConfig,
    *,
    system: str,
    user: str,
    schema: dict[str, Any],
    max_tokens: int = 900,
    temperature: float = 0.0,
) -> dict[str, Any]:
    """Send one chat completion and return its content as a JSON object."""
    body = _request_body(cfg, system, user, schema, max_tokens, temperature)
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if cfg.api_key:
        headers["Authorization"] = f"Bearer {cfg.api_key}"
    request = urllib.request.Request(
        cfg.endpoint,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=cfg.timeout_s) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raise ModelError(f"model endpoint returned HTTP {exc.code}") from None
    except urllib.error.URLError as exc:
        raise ModelError(f"model endpoint unreachable: {exc.reason}") from None
    except (TimeoutError, OSError) as exc:
        # socket.timeout is an OSError; keep the type, never the request.
        raise ModelError(f"model request failed: {type(exc).__name__}") from None
    return parse_json_object(_extract_content(raw))


def status() -> dict[str, Any]:
    """Honest one-line readiness for `mj status`; never raises."""
    try:
        cfg = config_from_env()
    except ModelError as exc:
        return {"configured": False, "error": str(exc)}
    if cfg is None:
        return {
            "configured": False,
            "hint": "set MJ_MODEL_PROVIDER, MJ_MODEL_BASE_URL and MJ_MODEL_NAME to "
            "enable reasoned planning; unset means no model is ever contacted",
        }
    return {"configured": True, **cfg.describe()}
