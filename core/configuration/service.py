"""Canonical configuration service (rebuilt in STEP 4).

Pinned specs
------------
* ``tests/unit/test_security_hardening.py``
    - ``ConfigurationService.validate_security_settings(dev, secret)`` must raise
      ``ValueError`` for a missing/short production secret, and allow a dev opt-in.
    - ``ConfigurationService._safe_api_value(path, value)`` must redact secrets and
      filesystem paths while passing ordinary scalars through untouched.
* ``memory/mem0_adapter.py`` -> ``configuration.get("ollama.base_url")``,
  ``configuration.get("llm.chat_model")``, ``configuration.get("llm.embedding_model")``.
* ``core/security_audit.py`` -> ``configuration.get("server.dev_mode", False)``.
* ``core/llm_failover.py`` -> ``configuration.get("failover.profiles", [])``,
  ``configuration.get("failover.cooldown_backoff_base", 60)``.
* ``tests/acceptance/test_browser_acceptance.py`` -> ``configuration.browser.headed = False``
  (attribute-style section assignment must stick and be readable back).

Design notes
------------
Values come from three layers, lowest precedence first:

1. built-in defaults (safe, production-shaped),
2. environment variables (``JARVIS_``-prefixed, plus the handful of legacy
   names already used across the codebase such as ``OLLAMA_BASE_URL``),
3. explicit ``set()`` / attribute assignment made at runtime.

Reading is dotted-path (``server.secret_key``); sections are also reachable as
attributes so ``configuration.browser.headed`` works in both directions.
No secrets are ever returned by ``_safe_api_value`` — that helper exists so
diagnostics and doctor output can print config without leaking it.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

logger = logging.getLogger(__name__)

JARVIS_DIR = Path.home() / ".jarvis"
USER_CONFIG_PATH = JARVIS_DIR / "config.json"

# Production-shaped defaults: no wildcards, no dev mode, no baked-in secret.
_DEFAULTS: Dict[str, Any] = {
    "server.dev_mode": False,
    "server.secret_key": "",
    "server.port": 8000,
    "server.allowed_origins": [],
    "browser.headed": False,
    "browser.headless": True,
    "ollama.base_url": "http://127.0.0.1:11434",
    "llm.chat_model": "ollama/qwen2.5-coder:3b",
    "llm.code_model": "ollama/qwen2.5-coder:3b",
    "llm.vision_model": "ollama/llava:7b",
    "llm.embedding_model": "nomic-embed-text",
    "failover.profiles": [],
    "failover.cooldown_backoff_base": 60,
    "voice.mode": "push-to-talk",
    "voice.tts_provider": "edge-tts",
    "voice.stt_provider": "faster-whisper",
    "voice.wake_word_enabled": False,
}

# env var -> config key (legacy names already referenced across the codebase)
_ENV_KEYS: Dict[str, str] = {
    "OLLAMA_BASE_URL": "ollama.base_url",
    "OLLAMA_HOST": "ollama.base_url",
    "CHAT_MODEL": "llm.chat_model",
    "CODE_MODEL": "llm.code_model",
    "VISION_MODEL": "llm.vision_model",
    "EMBEDDING_MODEL": "llm.embedding_model",
    "JARVIS_SECRET_KEY": "server.secret_key",
    "JARVIS_DEV_MODE": "server.dev_mode",
    "JARVIS_PORT": "server.port",
}

_SECRET_TOKENS = ("secret", "token", "password", "passwd", "api_key",
                  "apikey", "credential", "private_key")
_PATH_TOKENS = ("path", "dir", "vault", "home", "cwd")
_SECRET_MARK = "[redacted]"

_MIN_PRODUCTION_SECRET = 32


def _env_bool(raw: str) -> bool:
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class _Section:
    """Attribute window onto a flat dotted config store."""

    __slots__ = ("_store", "_prefix")

    def __init__(self, store: "ConfigurationService", prefix: str) -> None:
        object.__setattr__(self, "_store", store)
        object.__setattr__(self, "_prefix", prefix)

    def _key(self, name: str) -> str:
        return f"{object.__getattribute__(self, '_prefix')}.{name}"

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return object.__getattribute__(self, "_store").get(self._key(name))

    def __setattr__(self, name: str, value: Any) -> None:
        object.__getattribute__(self, "_store").set(self._key(name), value)

    def __getitem__(self, name: str) -> Any:
        return self.get(self._key(name))

    def __setitem__(self, name: str, value: Any) -> None:
        self.set(self._key(name), value)

    # allow store access on the section object
    def get(self, key: str, default: Any = None) -> Any:
        return object.__getattribute__(self, "_store").get(key, default)

    def set(self, key: str, value: Any) -> Any:
        return object.__getattribute__(self, "_store").set(key, value)


class ConfigurationService:
    """Single source of runtime configuration (see module docstring)."""

    def __init__(self, env: Optional[Dict[str, str]] = None,
                 defaults: Optional[Dict[str, Any]] = None,
                 user_config_path: Optional[Path] = None) -> None:
        self._env = dict(os.environ if env is None else env)
        self._defaults = dict(_DEFAULTS if defaults is None else defaults)
        self._path = Path(user_config_path) if user_config_path else USER_CONFIG_PATH
        self._values: Dict[str, Any] = {}
        self._sections: Dict[str, _Section] = {}
        self._load()

    # ------------------------------------------------------------ loading
    def _load(self) -> None:
        # layer 1: defaults
        self._values.update(self._defaults)
        # layer 2: environment
        for env_name, key in _ENV_KEYS.items():
            if env_name in self._env:
                self._values[key] = self._coerce(key, self._env[env_name])
        for env_name, raw in self._env.items():
            if env_name.startswith("JARVIS_"):
                key = env_name[len("JARVIS_"):].lower().replace("__", ".")
                if key not in self._values:
                    self._values[key] = self._coerce(key, raw)
        # layer 3: user config file (if present and readable)
        try:
            if self._path.exists():
                import json
                data = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    for k, v in data.items():
                        self._values[str(k).replace("__", ".")] = v
        except (OSError, ValueError) as exc:
            logger.warning("could not read %s: %s", self._path, exc)

    @staticmethod
    def _coerce(key: str, raw: Any) -> Any:
        if not isinstance(raw, str):
            return raw
        low = raw.strip().lower()
        if low in {"true", "false"}:
            return low == "true"
        if key.endswith((".port", ".timeout", ".cooldown_backoff_base")):
            try:
                return int(raw)
            except ValueError:
                return raw
        if key.endswith(".allowed_origins") or key.endswith(".cors_origins"):
            return [p.strip() for p in raw.split(",") if p.strip()] if raw else []
        return raw

    # -------------------------------------------------------------- access
    def get(self, key: str, default: Any = None) -> Any:
        if key in self._values:
            return self._values[key]
        # dotted fallback into the user config dict, e.g. "server.secret_key"
        return default

    def set(self, key: str, value: Any) -> Any:
        self._values[key] = value
        return value

    def __getitem__(self, key: str) -> Any:
        if key not in self._values:
            raise KeyError(key)
        return self._values[key]

    def __contains__(self, key: str) -> bool:
        return key in self._values

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        if "." + name + "." in "." + ".".join(self._values) or any(
                k.startswith(name + ".") for k in self._values):
            return self.section(name)
        raise AttributeError(f"configuration has no section {name!r}")

    def section(self, name: str) -> _Section:
        sec = self._sections.get(name)
        if sec is None:
            sec = _Section(self, name)
            self._sections[name] = sec
        return sec

    def keys(self) -> Iterable[str]:
        return sorted(self._values)

    def snapshot(self) -> Dict[str, Any]:
        return dict(self._values)

    # ---------------------------------------------------- security helpers
    @staticmethod
    def validate_security_settings(dev_mode: bool, secret: Optional[str]) -> None:
        """Raise ValueError unless the secret is fit for the deployment mode.

        Production (``dev_mode=False``) requires a secret of at least 32
        characters. Development opts in to a missing secret.
        """
        if dev_mode:
            return  # dev opt-in: a missing secret is tolerated by design
        if not secret or len(str(secret)) < _MIN_PRODUCTION_SECRET:
            raise ValueError(
                "production requires a secret of at least "
                f"{_MIN_PRODUCTION_SECRET} characters (got "
                f"{0 if not secret else len(str(secret))})"
            )

    @staticmethod
    def _safe_api_value(path: str, value: Any) -> Any:
        """Redact secrets and filesystem paths; pass ordinary values through."""
        if not isinstance(value, str):
            return value
        p = str(path).lower()
        if any(tok in p for tok in _SECRET_TOKENS):
            return _SECRET_MARK
        if any(tok in p for tok in _PATH_TOKENS):
            return _SECRET_MARK
        # a bare value that looks like a filesystem path is also redacted
        if len(value) >= 3 and (
            ("\\" in value and ":" in value)
            or value.startswith(("/", "~/"))
            or (len(value) > 2 and value[1] == ":")
        ):
            return _SECRET_MARK
        return value


# Module-level singleton used across the codebase: ``from core.configuration import configuration``
configuration = ConfigurationService()

__all__ = ["ConfigurationService", "configuration"]
