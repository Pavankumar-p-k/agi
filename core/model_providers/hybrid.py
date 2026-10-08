"""core.model_providers.hybrid - local/cloud mode platform.

Contract (jarvis-export/cli/cli_commands.py `jarvis models priority`):

    from core.model_providers.hybrid import get_platform
    platform.mode.value  # "local" | "cloud" | "hybrid" (upper-cased in the UI)
"""
from __future__ import annotations

import os
from enum import Enum
from typing import Optional


class HybridMode(str, Enum):
    LOCAL = "local"
    CLOUD = "cloud"
    HYBRID = "hybrid"


class ModelInfo:
    """Small descriptor for a routed model reference."""

    def __init__(self, provider_id: str, model_id: str, local: bool) -> None:
        self.provider_id = provider_id
        self.model_id = model_id
        self.local = local

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ModelInfo {self.provider_id}/{self.model_id} local={self.local}>"


def _env_mode() -> HybridMode:
    raw = (os.getenv("MODEL_MODE") or os.getenv("HYBRID_MODE") or "local").strip().lower()
    try:
        return HybridMode(raw)
    except ValueError:
        return HybridMode.LOCAL


class ModelInfo:
    """Row rendered by `jarvis models` (provider/model/status/latency/cost)."""

    def __init__(self, provider: str, model: str, status: str = "unknown",
                 latency_ms: float = 0.0, cost_estimate: str = "free") -> None:
        self.provider = provider
        self.model = model
        self.status = status
        self.latency_ms = latency_ms
        self.cost_estimate = cost_estimate


class TestResult:
    """Row rendered by `jarvis models test <provider>`."""

    def __init__(self, provider: str, model: str, status: str = "unknown",
                 latency_ms: float = 0.0, cost_estimate: str = "free",
                 error: str = "") -> None:
        self.provider = provider
        self.model = model
        self.status = status
        self.latency_ms = latency_ms
        self.cost_estimate = cost_estimate
        self.error = error


class HybridModelPlatform:
    """Mode holder: which priority order the routing layer uses."""

    def __init__(self, mode: Optional[HybridMode] = None) -> None:
        self.mode = mode or _env_mode()

    def set_mode(self, mode: HybridMode | str) -> None:
        self.mode = HybridMode(mode) if not isinstance(mode, HybridMode) else mode

    def set_mode_from_string(self, raw: str) -> str:
        """`jarvis models switch local|cloud|hybrid` - returns the status line."""
        try:
            self.set_mode(raw.strip().lower())
        except ValueError:
            return f"unknown mode {raw!r} (use local | cloud | hybrid)"
        return f"model mode set to {self.mode.value.upper()}"

    def priority(self) -> list[str]:
        """Provider ids in priority order for the current mode."""
        if self.mode == HybridMode.LOCAL:
            return ["ollama"]
        if self.mode == HybridMode.CLOUD:
            return ["openai", "anthropic", "gemini", "groq", "openrouter"]
        return ["ollama", "openai", "anthropic", "gemini", "groq", "openrouter"]

    # ------------------------------------------------------------------ #
    # CLI surfaces (all real, all honest)                                #
    # ------------------------------------------------------------------ #
    def _candidate_providers(self) -> list:
        from core.model_providers.router import provider_for_role

        out = []
        for pid in self.priority():
            try:
                out.append(provider_for_role(f"{pid}/x" if pid == "ollama" else pid))
            except Exception:  # noqa: BLE001 - unknown provider id: skip
                continue
        return out

    async def list_models(self) -> list[ModelInfo]:
        """One row per configured provider with live health."""
        rows: list[ModelInfo] = []
        for provider in self._candidate_providers():
            try:
                status = provider.health()
                import asyncio as _aio
                if _aio.iscoroutine(status):
                    status = await status
                model = getattr(provider, "model", "")
                state = "healthy" if getattr(status, "healthy", False) else "down"
                cost = "free" if getattr(provider, "local", False) else "paid"
                rows.append(ModelInfo(
                    provider=provider.provider_id,
                    model=model or "(default)",
                    status=state,
                    latency_ms=float(getattr(status, "latency_ms", 0.0) or 0.0),
                    cost_estimate=cost,
                ))
            except Exception as exc:  # noqa: BLE001
                rows.append(ModelInfo(provider=getattr(provider, "provider_id", "?"),
                                      model="(default)", status="error",
                                      cost_estimate="?"))
                rows[-1].error = str(exc)
                rows[-1].status = "error"
        return rows

    async def test_model(self, provider: Optional[str] = None,
                         model: Optional[str] = None) -> TestResult:
        """`jarvis models test [provider[/model]]` - one real round trip."""
        import time as _time

        pid = (provider or "ollama").strip().lower()
        try:
            from core.model_providers.router import _build

            instance = _build(pid, model or "")
        except Exception as exc:  # noqa: BLE001
            return TestResult(provider=pid, model=model or "", status="error",
                              error=str(exc))
        started = _time.perf_counter()
        try:
            result = instance.complete("Reply with exactly one word: PONG",
                                       temperature=0, model=model or "")
            latency = round((_time.perf_counter() - started) * 1000.0, 1)
            ok = bool(getattr(result, "success", False))
            return TestResult(
                provider=pid,
                model=getattr(result, "model", model or ""),
                status="healthy" if ok else "error",
                latency_ms=latency if ok else 0.0,
                cost_estimate="free" if getattr(instance, "local", False) else "paid",
                error=str(getattr(result, "error", "") or ""),
            )
        except Exception as exc:  # noqa: BLE001
            return TestResult(provider=pid, model=model or "", status="error",
                              error=str(exc))

    async def benchmark(self, provider: Optional[str] = None) -> list[dict]:
        """`jarvis models benchmark [provider]` - latency probe per provider."""
        targets = [provider] if provider else self.priority()
        results: list[dict] = []
        for pid in targets:
            test = await self.test_model(pid)
            results.append({
                "provider": pid,
                "model": test.model,
                "tests": [{
                    "type": "ping",
                    "latency_ms": test.latency_ms,
                    "tokens": "?",
                    "error": test.error,
                }],
            })
        return results


_platform_instance: Optional[HybridModelPlatform] = None


def get_platform() -> HybridModelPlatform:
    """Singleton platform (CLI `jarvis models priority` surface)."""
    global _platform_instance
    if _platform_instance is None:
        _platform_instance = HybridModelPlatform()
    return _platform_instance


def reset_platform() -> None:
    """Drop the cached platform (test seam)."""
    global _platform_instance
    _platform_instance = None


__all__ = ["HybridMode", "HybridModelPlatform", "ModelInfo", "TestResult",
           "get_platform", "reset_platform"]
