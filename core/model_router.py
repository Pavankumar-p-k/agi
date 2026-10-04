"""Model routing — resolve a role/model reference to a concrete endpoint.

Rebuilt in STEP 4 (this module did not exist on disk; ``core.vision_agent``
failed at import with ``ModuleNotFoundError: No module named 'core.model_router'``
and was tagged UNTESTABLE on the agent scorecard).

Pinned specs
------------
* ``core/vision_agent.py`` (module-scope calls, so they must work without a
  running server)::

      from core.model_router import get_ollama_url, model_for_role
      VISION_MODEL = model_for_role("vision")
      PLAN_MODEL   = model_for_role("planning")
      QUALITY_MODEL= model_for_role("quality")
      ...
      await self._http.post(f"{get_ollama_url(model)}/api/generate", ...)

  therefore ``model_for_role`` must accept ``planning``/``quality`` (which are
  *not* keys in ``core.llm_router.MODEL_ALIASES``) and ``get_ollama_url`` must
  accept the model reference as its first argument.

* ``tests/integration/test_channels_e2e.py`` patches
  ``core.model_router.route_request`` / ``get_ollama_url`` / ``model_for_role``,
  so those three names must exist and ``route_request`` must return the
  3-tuple ``(model_ref, provider, prompt)``.

Routing rules
-------------
``route_request`` picks the *cheapest provider that satisfies the request*:

1. an explicit ``model=`` wins,
2. otherwise the role's configured model,
3. a local Ollama model is preferred whenever Ollama is reachable and the
   request is not forced onto a cloud provider,
4. otherwise the first enabled cloud provider from ``MODEL_FALLBACKS`` order,
5. if nothing is configured, fall back to the chat model and mark the
   provider ``local`` — the caller degrades instead of crashing.

Reachability is probed with a short timeout and cached briefly so a router
called per-token does not stall on a dead daemon.
"""
from __future__ import annotations

import logging
import os
import time
import urllib.request
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)

__all__ = ["route_request", "get_ollama_url", "model_for_role",
           "resolve_model", "ollama_available"]

# Role aliases this module accepts on top of core.llm_router's table.
_EXTRA_ALIASES = {
    "planning": "reasoning",
    "plan": "reasoning",
    "quality": "reasoning",
    "agent": "chat",
    "summary": "chat",
    "embedding": "embedding",
}

# Cloud fallback order when no local model can serve the request.
_CLOUD_ORDER = ("openai", "anthropic", "gemini", "groq", "openrouter")

_PROBE_TTL = 15.0
_probe_cache: dict[str, tuple[bool, float]] = {}


def _llm():
    """Lazy import so this module stays importable without the full stack."""
    from core import llm_router
    return llm_router


def get_ollama_url(model: Optional[str] = None) -> str:
    """Base URL of the Ollama daemon for *model* (defaults to the global one).

    ``model`` may be ``"ollama/<name>"`` or a bare ``"<name>"``; it is accepted
    because vision code calls ``get_ollama_url(VISION_MODEL)``. A per-model
    override of the form ``"ollama@http://host:port/<name>"`` (multi-instance
    setups) is honoured, otherwise the configured daemon URL is returned.
    """
    ref = (model or "").strip()
    if "@" in ref:
        head, _, _tail = ref.partition("@")
        if head.startswith("ollama") and _tail.startswith(("http://", "https://")):
            base = _tail.split("/api/")[0].rstrip("/")
            if "/".join(_tail.split("/")[3:]):  # model part after scheme://host
                return base
            return base
    try:
        return _llm().get_ollama_url().rstrip("/")
    except Exception:  # noqa: BLE001 — degrade to env/default, never raise
        return os.getenv("OLLAMA_BASE_URL",
                         os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")).rstrip("/")


def model_for_role(role: str) -> str:
    """Model reference configured for *role* (falls back to the chat model).

    Accepts both canonical roles (``chat``, ``vision``) and friendly aliases
    (``planning``, ``quality``, ``plan``), including ones not present in
    ``core.llm_router.MODEL_ALIASES``.
    """
    key = (role or "chat").strip().lower()
    key = _EXTRA_ALIASES.get(key, key)
    try:
        llm = _llm()
        # llm_router.model_for_role already resolves MODEL_ALIASES + fallbacks
        resolved = llm.model_for_role(key)
        if resolved:
            return resolved
    except Exception:  # noqa: BLE001
        logger.debug("llm_router unavailable for role %r", role, exc_info=True)
    env_map = {
        "chat": "CHAT_MODEL", "code": "CODE_MODEL", "vision": "VISION_MODEL",
        "reasoning": "REASONING_MODEL", "analysis": "ANALYSIS_MODEL",
        "embedding": "EMBEDDING_MODEL",
    }
    canonical = _EXTRA_ALIASES.get(key, key)
    return os.getenv(env_map.get(canonical, "CHAT_MODEL"),
                     os.getenv("CHAT_MODEL", "ollama/qwen2.5-coder:3b"))


def resolve_model(model: Optional[str] = None, role: str = "chat") -> str:
    """Explicit *model* wins; otherwise the model configured for *role*."""
    ref = (model or "").strip()
    return ref if ref else model_for_role(role)


def ollama_available(timeout: float = 1.5) -> bool:
    """Cached reachability probe for the local Ollama daemon."""
    url = get_ollama_url()
    now = time.monotonic()
    hit = _probe_cache.get(url)
    if hit is not None and now - hit[1] < _PROBE_TTL:
        return hit[0]
    try:
        with urllib.request.urlopen(url + "/api/tags", timeout=timeout):
            ok = True
    except Exception:  # noqa: BLE001 — down daemon is a valid answer
        ok = False
    _probe_cache[url] = (ok, now)
    return ok


def _provider_for(model_ref: str) -> str:
    if "/" not in model_ref:
        return "local"
    head = model_ref.split("/", 1)[0]
    if head == "ollama":
        return "local"
    return head


def _is_local(model_ref: str) -> bool:
    return _provider_for(model_ref) == "local"


def route_request(
    prompt: str,
    role: str = "chat",
    model: Optional[str] = None,
    prefer_cloud: bool = False,
    **_kwargs: Any,
) -> Tuple[str, str, str]:
    """Choose ``(model_ref, provider, prompt)`` for one request.

    See the module docstring for the decision order. Never raises: an
    unsatisfiable request still returns a usable chat model so the caller can
    degrade rather than crash.
    """
    text = str(prompt if prompt is not None else "")

    candidate = resolve_model(model, role)

    if _is_local(candidate):
        if prefer_cloud:
            cloud = _first_cloud_model(role)
            if cloud:
                return cloud, _provider_for(cloud), text
            logger.debug("prefer_cloud set but no cloud model configured")
        if not ollama_available():
            cloud = _first_cloud_model(role)
            if cloud:
                return cloud, _provider_for(cloud), text
            # Nothing else available — still return a real model reference so
            # the caller reports a model-level failure, not a routing crash.
            logger.warning("no reachable provider; using %s as last resort", candidate)
        return candidate, _provider_for(candidate), text

    return candidate, _provider_for(candidate), text


def _first_cloud_model(role: str) -> Optional[str]:
    try:
        llm = _llm()
        roles = getattr(llm, "ROLE_MODELS", {}) or {}
        fallbacks = getattr(llm, "MODEL_FALLBACKS", {}) or {}
    except Exception:  # noqa: BLE001
        roles, fallbacks = {}, {}
    canonical = _EXTRA_ALIASES.get(role, role)
    for provider in _CLOUD_ORDER:
        env_name = f"{provider.upper()}_MODEL"
        ref = os.getenv(env_name)
        if ref:
            return ref
        configured = roles.get(canonical) or fallbacks.get(canonical)
        if configured and _provider_for(str(configured)) == provider:
            return str(configured)
        if canonical == provider or role == provider:
            configured = roles.get("chat")
            if configured and _provider_for(str(configured)) == provider:
                return str(configured)
    return None
