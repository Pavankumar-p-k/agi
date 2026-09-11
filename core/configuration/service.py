"""Runtime configuration service."""
from __future__ import annotations

from typing import Any
import os
from pathlib import Path

from dotenv import load_dotenv


class ConfigurationService:
    """Minimal but functional configuration store used across the app."""

    def __init__(self, data: dict[str, Any] | None = None):
        self._data: dict[str, Any] = {}
        if data:
            self._data.update(data)

    @property
    def browser(self) -> Any:
        """Compatibility view for browser acceptance harnesses."""
        if "browser" not in self._data or not isinstance(self._data["browser"], dict):
            self._data["browser"] = {}
        return _ConfigSection(self._data["browser"])

    def _resolve_key(self, key: str) -> tuple[dict[str, Any], str] | None:
        parts = key.split(".")
        if not parts:
            return None
        current = self._data
        for part in parts[:-1]:
            if not isinstance(current, dict):
                return None
            if part not in current:
                return None
            current = current[part]
        return current, parts[-1]

    def get(self, key: str, default: Any = None) -> Any:
        if "." not in key:
            return self._data.get(key, default)
        result = self._resolve_key(key)
        if result is None:
            return default
        parent, leaf = result
        if isinstance(parent, dict):
            return parent.get(leaf, default)
        return default

    def set(self, key: str, value: Any) -> None:
        if "." not in key:
            self._data[key] = value
            return
        parts = key.split(".")
        current = self._data
        for part in parts[:-1]:
            existing = current.get(part)
            if not isinstance(existing, dict):
                existing = {}
                current[part] = existing
            current = existing
        current[parts[-1]] = value

    def load(self) -> None:
        root = Path(__file__).resolve().parents[2]
        env_name = os.getenv("JARVIS_ENV", "").lower()
        candidates = []
        explicit_env = os.getenv("JARVIS_ENV_FILE")
        if explicit_env:
            candidates.append(Path(explicit_env))
        elif env_name:
            candidates.append(root / f".env.{env_name}")
        for path in candidates:
            if path.exists():
                load_dotenv(path, override=False)

        aliases = {
            "JARVIS_ENV": "environment",
            "JARVIS_SECRET_KEY": "server.secret_key",
            "JARVIS_DEV_MODE": "server.dev_mode",
            "HOST": "server.host",
            "PORT": "server.port",
            "ALLOWED_ORIGINS": "server.allowed_origins",
            "CHAT_MODEL": "llm.chat_model",
            "OLLAMA_MODEL": "llm.ollama_model",
            "OLLAMA_URL": "llm.ollama_url",
            "JARVIS_DB__URL": "database.url",
            "DATABASE_URL": "database.url",
        }
        for env_key, config_key in aliases.items():
            value = os.getenv(env_key)
            if value is not None:
                if config_key.endswith(("dev_mode",)):
                    value = str(value).lower() in {"1", "true", "yes", "on"}
                elif config_key.endswith(".port"):
                    value = int(value)
                self.set(config_key, value)

    def as_dict(self) -> dict[str, Any]:
        return dict(self._data)

    @staticmethod
    def validate_security_settings(dev_mode: bool, secret: str | None) -> None:
        if dev_mode:
            return
        if secret is None or not str(secret).strip() or len(str(secret).strip()) < 32:
            raise ValueError("Production mode requires a secret key of at least 32 characters.")

    @staticmethod
    def _safe_api_value(key: str, value: Any) -> Any:
        lowered = key.lower()
        if any(token in lowered for token in ("secret", "token", "password", "api_key", "vault", "private_key")):
            return "[redacted]"
        if value is None:
            return None
        if isinstance(value, (str, bytes)) and not value:
            return value
        return value


configuration = ConfigurationService()
configuration.load()


class _ConfigSection:
    def __init__(self, data: dict[str, Any]):
        self.__dict__["_data"] = data

    def __getattr__(self, key: str) -> Any:
        return self._data.get(key)

    def __setattr__(self, key: str, value: Any) -> None:
        self._data[key] = value
