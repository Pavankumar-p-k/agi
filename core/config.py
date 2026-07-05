"""DEPRECATED — use `core.configuration.configuration.get(key)` instead.

This module is a backward-compatibility shim. Module-level constants are
resolved from the canonical ConfigurationService on first access.

Deprecated: v3.2
Remove after: v4.0
"""
from __future__ import annotations

import os
import warnings
from pathlib import Path
from typing import Any

_warned = False


def _warn() -> None:
    global _warned
    if not _warned:
        warnings.warn(
            "core.config is deprecated. "
            "Use 'from core.configuration import configuration' and call configuration.get(key) instead.",
            DeprecationWarning, stacklevel=3,
        )
        _warned = True


BASE_DIR = Path(__file__).resolve().parents[1]

# ── Mapping from legacy constant name → ConfigurationService key ────────────
_CONFIG_KEYS: dict[str, str] = {
    "HOST": "server.host",
    "PORT": "server.port",
    "ALLOWED_ORIGINS": "server.allowed_origins",
    "SECRET_KEY": "server.secret_key",
    "DEV_MODE": "server.dev_mode",
    "FIREBASE_CREDENTIALS": "server.firebase_credentials",
    "DATABASE_URL": "db.url",
    "OLLAMA_URL": "ollama.base_url",
    "OLLAMA_MODEL": "ollama.default_model",
    "OLLAMA_PORTS": "ollama.ports",
    "VOSK_MODEL_PATH": "hardware.vosk_model_path",
    "CODEX_CLI_PATH": "build.codex_cli_path",
    "HYBRID_MAX_RETRIES": "llm.hybrid_max_retries",
    "HYBRID_TIMEOUT_SECONDS": "llm.hybrid_timeout_seconds",
    "SUPABASE_URL": "supabase_url",
    "SUPABASE_SERVICE_KEY": "supabase_service_key",
    "FACES_DIR": "hardware.faces_dir",
    "FACE_RECOGNITION_MODEL": "hardware.face_recognition_model",
    "FACE_DETECTION_BACKEND": "hardware.face_detection_backend",
    "FACE_DISTANCE_THRESHOLD": "hardware.face_distance_threshold",
    "MUSIC_DIR": "hardware.music_dir",
    "MAX_RETRIES": "build.max_retries",
    "DAEMON_MODE": "build.daemon_mode",
    "VAULT_PATH": "build.vault_path",
    "MAX_PARALLEL_BUILDS": "build.max_parallel_builds",
    "PROJECTS_DIR": "build.projects_dir",
}

# ── Constants resolved directly from env vars (no ConfigurationService key) ──
_ENV_ONLY: dict[str, str] = {
    "CLAUDE_API_KEY": "CLAUDE_API_KEY",
    "COPILOT_API_KEY": "COPILOT_API_KEY",
    "GITHUB_TOKEN": "GITHUB_TOKEN",
    "INSTAGRAM_USERNAME": "INSTAGRAM_USERNAME",
    "INSTAGRAM_PASSWORD": "INSTAGRAM_PASSWORD",
    "SUPABASE_SERVICE_KEY": "SUPABASE_SERVICE_KEY",
}

# ── Constants with combined env var + legacy fallback ────────────────────────
_ENV_WITH_FALLBACK: dict[str, tuple[str, str]] = {
    "SUPABASE_URL": ("SUPABASE_URL", "supabase_url"),
}


def __getattr__(name: str) -> Any:
    _warn()
    if name == "BASE_DIR":
        return BASE_DIR
    if name == "jarvis_config":
        from core.config_schema import jarvis_config
        return jarvis_config
    if name in _CONFIG_KEYS:
        config_key = _CONFIG_KEYS[name]
        # Try ConfigurationService (canonical source)
        try:
            from core.configuration import configuration
            val = configuration.get(config_key)
            if val is not None:
                return val
        except Exception:
            pass
        # Fall back to legacy jarvis_config for keys not in the config registry
        try:
            from core.config_schema import jarvis_config as _jc
            seg = config_key.split(".", 1)
            if len(seg) == 2:
                sub = getattr(_jc, seg[0], None)
                if sub is not None:
                    return getattr(sub, seg[1], None)
        except Exception:
            pass
    if name in _ENV_ONLY:
        return os.getenv(_ENV_ONLY[name])
    if name in _ENV_WITH_FALLBACK:
        env_var, fallback_key = _ENV_WITH_FALLBACK[name]
        val = os.getenv(env_var)
        if val is not None:
            return val
        try:
            from core.config_schema import jarvis_config as _jc
            return getattr(_jc, fallback_key, None)
        except Exception:
            pass
        return None
    raise AttributeError(f"module 'core.config' has no attribute {name!r}")


def __dir__() -> list[str]:
    return [*_CONFIG_KEYS.keys(), *_ENV_ONLY.keys(), *_ENV_WITH_FALLBACK.keys(), "BASE_DIR", "jarvis_config"]
