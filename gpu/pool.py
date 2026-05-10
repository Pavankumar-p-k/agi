# gpu/pool.py
# Multi-model pool with per-model endpoints (supports Option 2).

import asyncio
import httpx
import time
from collections import OrderedDict

from core.model_router import (
    get_ollama_url,
    get_fallbacks,
    is_multi_instance,
    model_for_role,
    resolve_model,
)

VRAM_LIMIT_GB = 5.8    # 200MB headroom on 6GB card

# ── Model VRAM costs (GB) ─────────────────────────────────────
MODEL_VRAM = {
    "llama3.1:8b":        4.9,   # primary chat (8B)
    "qwen2.5:7b":         4.7,   # analysis (7B)
    "mistral:7b":         4.4,   # creative (7B)
    "qwen3:4b":           2.5,   # automation
    "qwen2.5-coder:3b":   1.9,   # coding tasks
    "deepseek-r1:1.5b":   1.1,   # reasoning + planning
    "moondream":          1.7,   # vision
    "phi3:mini":          2.2,   # quality/short tasks
    "tinyllama":          0.7,   # fast fallback
}

# tinyllama stays loaded always (only 1.2GB, trivial cost)
PINNED_MODELS = {"tinyllama"}

# ── Context windows ───────────────────────────────────────────
MODEL_CTX = {
    "llama3.1:8b":        4096,
    "qwen2.5:7b":         4096,
    "mistral:7b":         4096,
    "qwen3:4b":           4096,
    "qwen2.5-coder:3b":   4096,
    "deepseek-r1:1.5b":   4096,
    "moondream":          2048,
    "phi3:mini":          4096,
    "tinyllama":          2048,
}


class ModelPool:
    def __init__(self):
        self._loaded: OrderedDict = OrderedDict()   # LRU eviction
        self._vram_used: float    = 0.0
        self._lock                = asyncio.Lock()
        self._client              = httpx.AsyncClient(timeout=180.0)
        self._call_counts: dict   = {}
        self._latency_stats: dict = {}
        self._multi_instance      = is_multi_instance()

    # ── Warm up on startup ────────────────────────────────────

    async def warmup(self):
        print("[Pool] Warming up models...")
        # Pin tinyllama first — always in VRAM
        await self._ensure_loaded("tinyllama")
        # Pre-load primary brain
        await self._ensure_loaded(model_for_role("chat"))
        print("[Pool] Warmup done ✓  (tinyllama + primary chat loaded)")
        print(f"[Pool] VRAM used: {self._vram_used:.1f}GB / {VRAM_LIMIT_GB}GB")

    # ── Main interface ────────────────────────────────────────

    async def generate(
        self,
        model:       str,
        prompt:      str,
        system:      str   = "",
        temperature: float = 0.7,
        max_tokens:  int   = 512,
        images:      list  = None,   # for moondream vision
    ) -> str:
        model = resolve_model(model)
        await self._ensure_loaded(model)

        t_start = time.time()
        payload = {
            "model":   model,
            "prompt":  prompt,
            "system":  system,
            "stream":  False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx":     MODEL_CTX.get(model, 4096),
                "num_gpu":     99,    # force all layers to GPU
            },
        }

        # Add images for moondream vision
        if images:
            payload["images"] = images

        try:
            r = await self._client.post(
                f"{get_ollama_url(model)}/api/generate",
                json=payload,
                timeout=120.0,
            )
            data    = r.json()
            elapsed = int((time.time() - t_start) * 1000)
            self._track(model, elapsed)
            return data.get("response", "").strip()

        except Exception as e:
            print(f"[Pool] ERROR generating with {model}: {e}")
            for fb in get_fallbacks(model):
                if fb == model:
                    continue
                print(f"[Pool] Falling back to {fb}...")
                return await self.generate(
                    fb, prompt, system, temperature, max_tokens, images=images
                )
            return "I'm having trouble connecting to my brain right now."

    async def chat(
        self,
        model:    str,
        messages: list,
        temperature: float = 0.7,
        max_tokens: int    = 512,
    ) -> str:
        """Chat interface — used by jarvis_conversation.py"""
        model = resolve_model(model)
        await self._ensure_loaded(model)

        payload = {
            "model":    model,
            "messages": messages,
            "stream":   False,
            "options":  {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx":     MODEL_CTX.get(model, 4096),
                "num_gpu":     99,
            },
        }

        try:
            r    = await self._client.post(f"{get_ollama_url(model)}/api/chat",
                                            json=payload, timeout=120.0)
            data = r.json()
            return data.get("message", {}).get("content", "").strip()
        except Exception as e:
            print(f"[Pool] Chat ERROR with {model}: {e}")
            for fb in get_fallbacks(model):
                if fb == model:
                    continue
                return await self.chat(fb, messages, temperature, max_tokens)
            return "Connection error."

    # ── VRAM management ───────────────────────────────────────

    async def _ensure_loaded(self, model: str):
        async with self._lock:
            if model in self._loaded:
                self._loaded.move_to_end(model)   # refresh LRU
                return

            if self._multi_instance:
                # In multi-instance mode, just warm the target model's server.
                try:
                    await self._client.post(
                        f"{get_ollama_url(model)}/api/generate",
                        json={"model": model, "prompt": " ", "stream": False,
                              "options": {"num_predict": 1}},
                        timeout=60.0)
                    self._loaded[model] = time.time()
                    print(f"[Pool] Warmed {model} (multi-instance)")
                except Exception as e:
                    print(f"[Pool] Failed to warm {model}: {e}")
                return

            needed = MODEL_VRAM.get(model, 2.0)

            # Evict LRU models (skip pinned) until we have room
            while self._vram_used + needed > VRAM_LIMIT_GB:
                evicted = self._evict_lru()
                if not evicted:
                    break

            # Load model by sending a tiny prompt
            try:
                await self._client.post(
                    f"{get_ollama_url(model)}/api/generate",
                    json={"model": model, "prompt": " ", "stream": False,
                          "options": {"num_predict": 1}},
                    timeout=60.0)
                self._loaded[model] = time.time()
                self._vram_used    += needed
                print(f"[Pool] Loaded {model} "
                      f"({needed}GB, total={self._vram_used:.1f}GB)")
            except Exception as e:
                print(f"[Pool] Failed to load {model}: {e}")

    def _evict_lru(self) -> bool:
        for model in list(self._loaded.keys()):
            if model not in PINNED_MODELS:
                vram = MODEL_VRAM.get(model, 2.0)
                del self._loaded[model]
                self._vram_used = max(0, self._vram_used - vram)
                print(f"[Pool] Evicted {model} (freed {vram}GB)")
                return True
        return False

    def _track(self, model: str, latency_ms: int):
        self._call_counts[model] = self._call_counts.get(model, 0) + 1
        stats = self._latency_stats.setdefault(model, [])
        stats.append(latency_ms)
        if len(stats) > 100:
            stats.pop(0)

    # ── Stats ─────────────────────────────────────────────────

    def stats(self) -> dict:
        return {
            "loaded_models": list(self._loaded.keys()),
            "vram_used_gb":  round(self._vram_used, 2),
            "vram_limit_gb": VRAM_LIMIT_GB,
            "call_counts":   self._call_counts,
            "avg_latency_ms": {
                m: int(sum(v) / len(v))
                for m, v in self._latency_stats.items() if v
            },
        }

    async def health_check(self) -> bool:
        try:
            r = await self._client.get(
                f"{get_ollama_url(model_for_role('chat'))}/api/tags",
                timeout=3.0)
            return r.status_code == 200
        except Exception:
            return False
