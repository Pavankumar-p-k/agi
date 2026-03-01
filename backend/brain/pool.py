from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from typing import Any

import httpx

from core.config import OLLAMA_URL

VRAM_LIMIT_GB = 5.8
MODEL_VRAM = {
    "phi3:mini": 2.2,
    "mistral:7b": 4.4,
    "qwen2:7b": 4.4,
    "llama3:8b": 4.7,
    "llava:latest": 4.7,
}
PINNED_MODELS = {"phi3:mini"}
FALLBACK_MODEL = "phi3:mini"


class ModelPool:
    def __init__(self) -> None:
        self._loaded: OrderedDict[str, float] = OrderedDict()
        self._vram_used = 0.0
        self._lock = asyncio.Lock()
        self._client = httpx.AsyncClient(timeout=120.0)
        self._call_counts: dict[str, int] = {}
        self._latency_stats: dict[str, list[float]] = {}

    async def warmup(self) -> None:
        if not await self.is_available():
            print("[BrainPool] Ollama unavailable. Skipping warmup.")
            return
        await self._ensure_loaded("phi3:mini")
        await self._ensure_loaded("mistral:7b")

    async def is_available(self) -> bool:
        try:
            res = await self._client.get(f"{OLLAMA_URL}/api/tags", timeout=2.0)
            return res.status_code == 200
        except Exception:
            return False

    async def generate(
        self,
        model: str,
        prompt: str,
        system: str = "",
        temperature: float = 0.7,
        max_tokens: int = 512,
    ) -> str:
        if not await self.is_available():
            return ""

        async with self._lock:
            await self._ensure_loaded(model)

        start = time.time()
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": 4096,
                "num_gpu": 99,
                "num_thread": 8,
                "top_p": 0.9,
                "repeat_penalty": 1.1,
            },
        }
        if system:
            payload["system"] = system

        try:
            res = await self._client.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=90.0)
            res.raise_for_status()
            data = res.json()
            text = str(data.get("response", "")).strip()
            self._record_stat(model, time.time() - start)
            if model in self._loaded:
                self._loaded.move_to_end(model)
            return text
        except Exception:
            if model != FALLBACK_MODEL:
                return await self.generate(FALLBACK_MODEL, prompt, system=system, temperature=temperature, max_tokens=max_tokens)
            return ""

    async def _ensure_loaded(self, model: str) -> None:
        if model in self._loaded:
            return

        needed = MODEL_VRAM.get(model, 4.0)
        while self._vram_used + needed > VRAM_LIMIT_GB:
            if not self._evict_lru():
                break

        try:
            await self._client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": model,
                    "prompt": "",
                    "stream": False,
                    "options": {"num_predict": 1, "num_gpu": 99},
                },
                timeout=30.0,
            )
            self._loaded[model] = time.time()
            self._vram_used += needed
        except Exception:
            # Keep running even when load fails.
            pass

    def _evict_lru(self) -> bool:
        for model in list(self._loaded.keys()):
            if model in PINNED_MODELS:
                continue
            self._loaded.pop(model, None)
            self._vram_used = max(0.0, self._vram_used - MODEL_VRAM.get(model, 4.0))
            return True
        return False

    def _record_stat(self, model: str, elapsed: float) -> None:
        self._call_counts[model] = self._call_counts.get(model, 0) + 1
        self._latency_stats.setdefault(model, []).append(round(elapsed, 3))
        if len(self._latency_stats[model]) > 50:
            self._latency_stats[model].pop(0)

    def get_stats(self) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for model, latencies in self._latency_stats.items():
            avg = (sum(latencies) / len(latencies)) if latencies else 0.0
            out[model] = {
                "calls": self._call_counts.get(model, 0),
                "avg_latency_s": round(avg, 3),
                "loaded": model in self._loaded,
                "vram_gb": MODEL_VRAM.get(model, 0.0),
            }
        return out

    def vram_status(self) -> dict[str, Any]:
        return {
            "used_gb": round(self._vram_used, 2),
            "limit_gb": VRAM_LIMIT_GB,
            "free_gb": round(VRAM_LIMIT_GB - self._vram_used, 2),
            "loaded": list(self._loaded.keys()),
            "pinned": list(PINNED_MODELS),
        }

    async def unload_all(self) -> None:
        self._loaded.clear()
        self._vram_used = 0.0
        await self._client.aclose()
