"""core.embeddings — shared embedding client.

Rebuilt from the committed contracts:

- tests/unit/test_docker_readiness.py::test_embedding_client_uses_ollama_embed_endpoint
    EmbeddingClient() (no args) -> client.url == "http://ollama:11434/api/embed"
    when OLLAMA_URL=http://ollama:11434 and EMBEDDING_URL unset.
- tests/unit/test_docker_readiness.py::test_embedding_client_accepts_ollama_response
    encode(["hello"]) POSTs to Ollama /api/embed and normalizes: for
    {"embeddings": [[3.0, 4.0]]} the result is [[0.6, 0.8]] exactly.
- memory/similarity.py + memory/vector_store.py consumers:
    get_embedding_client().encode(texts, normalize_embeddings=True) -> ndarray
    supporting .size and row dot products.
"""
from __future__ import annotations

import os
from typing import Any, Optional


def _default_embed_url() -> str:
    """Ollama /api/embed endpoint from env (EMBEDDING_URL > OLLAMA_URL)."""
    explicit = os.getenv("EMBEDDING_URL")
    if explicit:
        return explicit.rstrip("/")
    ollama = os.getenv("OLLAMA_URL") or os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434"
    return ollama.rstrip("/") + "/api/embed"


class EmbeddingClient:
    """Blocking HTTP embedding client for Ollama's /api/embed endpoint.

    `encode` mimics the sentence-transformers surface used across memory/:
    accepts a list of texts (or a single string), returns a 2-D float ndarray.
    """

    def __init__(self, url: str = "", model: str = "", **kwargs: Any) -> None:
        self.url = url or _default_embed_url()
        self.model = model or os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
        self.timeout = float(kwargs.get("timeout", 30.0))
        # Eagerly-constructed so tests/monkeypatchers can replace `.post` on it
        # directly (see test_embedding_client_accepts_ollama_response).
        import httpx

        self._client = httpx.Client(timeout=self.timeout)

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._client.post(self.url, json=payload)
        response.raise_for_status()
        return response.json()

    def encode(self, texts: Any, *, normalize_embeddings: bool = True) -> Any:
        """Embed texts; returns an (n, dim) ndarray. Rows are L2-normalized
        by default (contract: [[3.0, 4.0]] encodes to [[0.6, 0.8]])."""
        import numpy as np

        single = isinstance(texts, str)
        items = [texts] if single else list(texts)
        data = self._post({"model": self.model, "input": items})
        vecs = np.asarray(data["embeddings"], dtype=float)
        if normalize_embeddings:
            norms = np.linalg.norm(vecs, axis=1, keepdims=True)
            norms[norms == 0.0] = 1.0
            vecs = vecs / norms
        return vecs[0] if single else vecs

    def health(self) -> bool:
        """True when the embedding endpoint answers."""
        try:
            self.encode(["ping"])
            return True
        except Exception:  # noqa: BLE001
            return False


_client: Optional[EmbeddingClient] = None


def get_embedding_client() -> EmbeddingClient:
    """Shared singleton embedding client (memory/ consumers)."""
    global _client
    if _client is None:
        _client = EmbeddingClient()
    return _client


__all__ = ["EmbeddingClient", "get_embedding_client"]
