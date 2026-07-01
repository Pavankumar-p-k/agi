"""core/routes/diagnostics.py — Diagnostics Dashboard REST API."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

try:
    from fastapi import APIRouter
    _FASTAPI = True
except ImportError:
    _FASTAPI = False

if _FASTAPI:
    router = APIRouter(tags=["diagnostics"])

    @router.get("/api/diagnostics")
    async def get_full_diagnostics():
        results: dict[str, Any] = {}
        errors: dict[str, str] = {}

        # Model health
        try:
            from core.model_providers.base import health_check_all as models_health
            results["models"] = {}
            raw = await asyncio.wait_for(models_health(), timeout=5.0)
            for name, status in raw.items():
                results["models"][name] = {
                    "available": status.available,
                    "healthy": status.healthy,
                    "latency_ms": round(getattr(status, "latency_ms", 0), 1),
                    "error": getattr(status, "error", None),
                    "model": getattr(status, "model", None),
                }
        except asyncio.TimeoutError:
            errors["models"] = "timeout"
        except Exception as e:
            errors["models"] = str(e)

        # Integration health
        try:
            from core.integration_manager import health_check_all as int_health
            raw = await asyncio.wait_for(int_health(), timeout=5.0)
            results["integrations"] = {
                name: {
                    "connected": s.get("connected", False),
                    "healthy": s.get("healthy", False),
                    "error": s.get("error", None),
                    "latency_ms": round(s.get("latency_ms", 0), 1),
                }
                for name, s in raw.items()
            }
        except asyncio.TimeoutError:
            errors["integrations"] = "timeout"
        except Exception as e:
            errors["integrations"] = str(e)

        # Voice health
        try:
            from assistant.voice_pipeline import health_check as voice_health
            voice_status = await asyncio.wait_for(voice_health(), timeout=3.0)
            results["voice"] = {
                "enabled": voice_status.get("enabled", False),
                "stt_available": voice_status.get("stt_available", False),
                "tts_available": voice_status.get("tts_available", False),
                "wake_word_available": voice_status.get("wake_word_available", False),
                "error": voice_status.get("error", None),
            }
        except asyncio.TimeoutError:
            errors["voice"] = "timeout"
        except Exception as e:
            errors["voice"] = str(e)

        # Feature audit
        try:
            from core.feature_registry import get_feature_report
            results["features"] = get_feature_report()
        except Exception as e:
            errors["features"] = str(e)

        # Environment
        try:
            from core.environment_monitor import environment_monitor
            env = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, environment_monitor.check),
                timeout=5.0,
            )
            results["environment"] = {
                "disk_free_gb": round(env.disk_free_gb, 1),
                "memory_free_mb": round(env.memory_free_mb, 0),
                "ollama_available": env.ollama_available,
                "ollama_latency_ms": round(env.ollama_latency_ms, 1),
                "network_reachable": env.network_reachable,
            }
        except asyncio.TimeoutError:
            errors["environment"] = "timeout"
        except Exception as e:
            errors["environment"] = str(e)

        # System info
        import os, platform, time
        results["system"] = {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "hostname": platform.node(),
            "pid": os.getpid(),
            "uptime_seconds": int(time.time() - _get_start_time()),
        }

        return {
            "timestamp": __import__("datetime").datetime.now().isoformat(),
            "data": results,
            "errors": errors,
            "healthy": len(errors) == 0,
        }

    @router.get("/api/diagnostics/models")
    async def get_model_diagnostics():
        from core.model_providers.base import health_check_all
        try:
            results = await asyncio.wait_for(health_check_all(), timeout=5.0)
        except asyncio.TimeoutError:
            results = {}
        return {
            "providers": [
                {
                    "name": name,
                    "available": s.available,
                    "healthy": s.healthy,
                    "latency_ms": round(getattr(s, "latency_ms", 0), 1),
                    "error": getattr(s, "error", None),
                    "model": getattr(s, "model", None),
                }
                for name, s in results.items()
            ]
        }

    @router.get("/api/diagnostics/integrations")
    async def get_integration_diagnostics():
        from core.integration_manager import health_check_all
        try:
            results = await asyncio.wait_for(health_check_all(), timeout=5.0)
        except asyncio.TimeoutError:
            results = {}
        return {
            "integrations": [
                {"name": name, **s}
                for name, s in results.items()
            ]
        }

    @router.get("/api/diagnostics/voice")
    async def get_voice_diagnostics():
        try:
            from assistant.voice_pipeline import health_check
            return await health_check()
        except Exception as e:
            return {"enabled": False, "error": str(e)}

    @router.get("/api/diagnostics/environment")
    async def get_environment_diagnostics():
        from core.environment_monitor import environment_monitor
        env = environment_monitor.check()
        return {
            "disk_free_gb": round(env.disk_free_gb, 1),
            "memory_free_mb": round(env.memory_free_mb, 0),
            "ollama_available": env.ollama_available,
            "ollama_latency_ms": round(env.ollama_latency_ms, 1),
            "network_reachable": env.network_reachable,
        }

    @router.get("/api/diagnostics/features")
    async def get_feature_diagnostics():
        from core.feature_registry import get_feature_report
        return get_feature_report()

    def _get_start_time() -> float:
        try:
            from core.main import _start_time
            return _start_time
        except ImportError:
            import os
            import time
            return time.time() - (os.getpid() * 0.001)

else:
    class router:
        pass
