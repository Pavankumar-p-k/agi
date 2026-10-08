"""core.model_providers.ollama — local Ollama provider.

Rebuilt from the committed contracts:

- tests/unit/test_docker_readiness.py::test_ollama_provider_prefers_container_url
    OLLAMA_URL wins over OLLAMA_BASE_URL; trailing "/" stripped.
- tests/unit/test_phase5_reliability.py::test_ollama_embeddings_preserve_requested_model_and_batches
    await provider.embeddings(model, texts) POSTs {"model": model,
    "input": texts} to /api/embed via httpx.AsyncClient and returns
    resp.json()["embeddings"].
- tests/architecture/test_phase5_hybrid_router.py
    health() ping /api/tags with GET Lindsey 200 → available + healthy +
    latency_ms that measures the round trip (unavailable → available=False,
    healthy False or error).
"""
from __future__ import annotations

import os
import time
from typing import Any, Optional

from core.model_providers.base import (
    ModelProvider,
    ModelResult,
    ProviderState,
    ProviderStatus,
)


def resolve_base_url() -> str:
    """Ollama base URL precedence: OLLAMA_URL > OLLAMA_BASE_URL > localhost.

    A trailing "/" is stripped (container URL contract).
    """
    url = (
        os.getenv("OLLAMA_URL")
        or os.getenv("OLLAMA_BASE_URL")
        or "http://localhost:11434"
    )
    return url.rstrip("/")


def _is_ollama_native_url(url: str) -> bool:
    """True when `url` already points at an Ollama daemon."""
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        if scheme not in ("http", "https"):
            return False
        if not parsed.hostname:
            return False
        port = parsed.port
        return port == 11434 or (port is None and url.rstrip("/").endswith(":11434"))
    except Exception:
        return False


class OllamaProvider(ModelProvider):
    """Local-first provider. Free, private, no API key."""

    provider_id = "ollama"
    local = True

    def __init__(self, base_url: str = "", model: str = "", **kwargs: Any) -> None:
        super().__init__(base_url=base_url or resolve_base_url(), model=model, **kwargs)
        # Contract alias: tests and legacy callers read `_base_url`.
        self._base_url = self.base_url
        self.timeout_seconds = float(kwargs.get("timeout_seconds", 60.0))

    # ------------------------------------------------------------------ #
    # Health                                                             #
    # ------------------------------------------------------------------ #
    def health(self) -> ProviderStatus:
        """Ping GET /api/tags; measure the round trip. No caching — each
        probe reflects the daemon state at call time (the doctor table is
        rendered once per run, so the cost is one HTTP round trip)."""
        base = self._base_url
        started = time.perf_counter()
        status = ProviderStatus(provider=self.provider_id)
        try:
            import httpx

            with httpx.Client(timeout=2.0) as client:
                tags = client.get(f"{base}/api/tags")
                status.latency_ms = round((time.perf_counter() - started) * 1000.0, 1)
                tags.raise_for_status()
                payload = tags.json()
                models = [
                    str(m.get("name", ""))
                    for m in payload.get("models", [])
                    if m.get("name")
                ]
                if models:
                    status.models = models
                status.available = True
                status.healthy = True
                status.state = ProviderState.HEALTHY
        except Exception as exc:  # noqa: BLE001 - health probes must not raise
            status.latency_ms = round((time.perf_counter() - started) * 1000.0, 1)
            status.available = False
            status.healthy = False
            status.error = str(exc)
            status.state = ProviderState.DOWN
        return status

    def list_models(self) -> list[str]:
        """Installed model names (best effort; [] when the daemon is down)."""
        try:
            import httpx

            with httpx.Client(timeout=2.0) as client:
                return [
                    str(m.get("name", ""))
                    for m in client.get(f"{self._base_url}/api/tags").json().get("models", [])
                    if m.get("name")
                ]
        except Exception:  # noqa: BLE001
            return []

    # ------------------------------------------------------------------ #
    # Generation                                                         #
    # ------------------------------------------------------------------ #
    def _post_generate(self, payload: dict[str, Any])-> Any:
        import httpx

        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(f"{self._base_url}/api/generate", json=payload)
            response.raise_for_status()
            return response.json()

    def complete(
        self,
        prompt: str,
        *,
        system: str = "",
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        model: str = "",
        **kwargs: Any,
    ) -> ModelResult:
        """Blocking single-turn completion via /api/generate."""
        started = time.perf_counter()
        model_ref = model or self.model or "qwen2.5-coder:3b"
        payload: dict[str, Any] = {
            "model": model_ref,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if system:
            payload["system"] = system
        if max_tokens is not None:
            payload["options"]["num_predict"] = int(max_tokens)
        try:
            data = self._post_generate(payload)
            latency = round((time.perf_counter() - started) * 1000.0, 1)
            return ModelResult(
                success=True,
                text=str(data.get("response", "")),
                model=model_ref,
                latency_ms=latency,
                tokens_used=int(data.get("eval_count", 0) or 0),
            )
        except Exception as exc:  # noqa: BLE001 - callers handle errors
            return ModelResult(
                success=False,
                error=str(exc),
                model=model_ref,
                latency_ms=round((time.perf_counter() - started) * 1000.0, 1),
            )

    # ------------------------------------------------------------------ #
    # Embeddings                                                         #
    # ------------------------------------------------------------------ #
    async def embeddings(self, model: str, inputs: list[str]) -> list[list[float]]:
        """POST {"model": model, "input": texts} to /api/embed; return the
        full embeddings matrix (batches preserved verbatim)."""
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self._base_url}/api/embed",
                json={"model": model, "input": inputs},
            )
            response.raise_for_status()
            data = response.json()
        return data["embeddings"]


__all__ = ["OllamaProvider", "resolve_base_url", "_is_ollama_native_url"]
