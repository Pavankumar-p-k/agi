from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Callable

from core.settings.store import SettingsStore

from core.event_bus import (
    CONFIG_CHANGED,
    CONFIG_RELOADED,
    CONFIG_VALIDATION_ERROR,
    Event,
    global_event_bus,
)

logger = logging.getLogger(__name__)

PROVIDERS_FILE = "providers.json"
CAPABILITIES = ("chat", "code", "analysis", "reasoning", "vision", "grader", "embedding", "orchestrator", "fallback", "cloud")

_HEADERS = {
    "chat": ("chat", "conversation", "dialogue"),
    "code": ("code", "coding", "programming"),
    "analysis": ("analysis", "analyze", "research"),
    "reasoning": ("reasoning", "reason", "think", "plan"),
    "vision": ("vision", "image", "visual", "screen"),
    "grader": ("grader", "grade", "evaluate", "quality"),
    "embedding": ("embedding", "embed", "vector"),
    "orchestrator": ("orchestrator", "orchestrate", "route"),
}

_CONFIG_TO_CAPABILITY: dict[str, str] = {
    "llm.chat_model": "chat",
    "llm.code_model": "code",
    "llm.analysis_model": "analysis",
    "llm.reasoning_model": "reasoning",
    "llm.vision_model": "vision",
    "llm.grader_model": "grader",
    "llm.embedding_model": "embedding",
    "llm.orchestrator_model": "orchestrator",
    "llm.fallback_model": "fallback",
    "llm.cloud_model": "cloud",
}

_DEFAULT_PROVIDERS = {
    "providers": {
        "ollama": {
            "enabled": True,
            "base_url": os.getenv("OLLAMA_URL", "http://127.0.0.1:11434"),
        },
        "openai": {
            "enabled": bool(os.getenv("OPENAI_API_KEY")),
        },
        "anthropic": {
            "enabled": bool(os.getenv("ANTHROPIC_API_KEY")),
        },
    },
    "routing": {
        capability: "auto" for capability in CAPABILITIES
    },
    "preferences": {
        "speed_over_quality": False,
        "offline_only": True,
    },
}


class ConfigurationService:
    def __init__(self, config_dir: Path | None = None):
        self.config_dir = config_dir or Path.home() / ".jarvis"
        self._settings_store: SettingsStore | None = None
        self._providers: dict[str, Any] = {}
        self._flat_config: dict[str, Any] = {}
        self._overrides: dict[str, Any] = {}
        self._env_cache: dict[str, str] = {}
        self._listeners: dict[str, list[Callable]] = {}
        self._loaded = False

    # ── Loading ────────────────────────────────────────────────

    def load(self, config_yaml_path: str = "./config.yaml", settings_path: str = "./data/settings.json"):
        self._flat_config = {}
        self._load_yaml(config_yaml_path)
        self._load_settings_json(settings_path)
        self._scan_env_vars()
        self._init_settings_store()
        self._load_providers()
        self._loaded = True

        self._fire_config_reloaded()

    def _fire_config_reloaded(self):
        try:
            global_event_bus.publish_sync(
                Event(type=CONFIG_RELOADED, source="config.service", payload={})
            )
        except Exception:
            logger.debug("[Config] Failed to emit config.reloaded event", exc_info=True)

    def _load_yaml(self, path: str):
        yaml_path = Path(path)
        if yaml_path.exists():
            try:
                import yaml
                with open(yaml_path, encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                self._flat_config.update(self._flatten(data))
                logger.debug("[Config] Loaded yaml: %s", yaml_path)
            except Exception as e:
                logger.warning("[Config] Failed to load yaml %s: %s", yaml_path, e)

    def _load_settings_json(self, path: str):
        settings_path = Path(path)
        if settings_path.exists():
            try:
                with open(settings_path, encoding="utf-8") as f:
                    data = json.load(f)
                self._flat_config.update(data)
                logger.debug("[Config] Loaded settings: %s", settings_path)
            except Exception as e:
                logger.warning("[Config] Failed to load settings %s: %s", settings_path, e)

    def _scan_env_vars(self):
        try:
            from core.config_registry import _REGISTRY
            for entry in _REGISTRY:
                if entry.env_var:
                    val = os.environ.get(entry.env_var)
                    if val is not None:
                        self._env_cache[entry.key] = val
        except ImportError:
            pass

    def _init_settings_store(self):
        self._settings_store = SettingsStore(config_dir=self.config_dir)
        self._settings_store.load()

    def _load_providers(self):
        providers_path = self.config_dir / PROVIDERS_FILE
        if providers_path.exists():
            try:
                self._providers = json.loads(providers_path.read_text(encoding="utf-8"))
                return
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to load %s: %s, using defaults", providers_path, e)
        self._providers = dict(_DEFAULT_PROVIDERS)
        self._save_providers()

    def _save_providers(self):
        providers_path = self.config_dir / PROVIDERS_FILE
        try:
            providers_path.write_text(json.dumps(self._providers, indent=2), encoding="utf-8")
        except OSError as e:
            logger.warning("Failed to save %s: %s", providers_path, e)

    @staticmethod
    def _flatten(data: dict, prefix: str = "") -> dict:
        result = {}
        for key, value in data.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                result.update(ConfigurationService._flatten(value, full_key))
            else:
                result[full_key] = value
        return result

    # ── Resolution chain ───────────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        if not self._loaded:
            self.load()

        if key.startswith("providers."):
            parts = key.split(".")
            val = self._providers
            for p in parts[1:]:
                if isinstance(val, dict):
                    val = val.get(p)
                else:
                    return default
            return val if val is not None else default

        # 1. In-memory overrides (set via set())
        if key in self._overrides:
            return self._overrides[key]

        # 2. Environment variable
        if key in self._env_cache:
            return self._env_cache[key]

        # 3. Flat config (from config.yaml + data/settings.json)
        if key in self._flat_config:
            return self._coerce(key, self._flat_config[key])

        # 4. SettingsStore (~/.jarvis/settings.json)
        try:
            if self._settings_store:
                val = self._settings_store.get(key)
                if val is not None:
                    return val
        except Exception:
            pass

        # 5. Auto-resolve model capabilities
        if key in _CONFIG_TO_CAPABILITY:
            return self.resolve(_CONFIG_TO_CAPABILITY[key])

        # 6. Default from registry
        try:
            from core.config_registry import _REGISTRY_MAP
            entry = _REGISTRY_MAP.get(key)
            if entry:
                return entry.default
        except ImportError:
            pass

        return default

    def _coerce(self, key: str, value: Any) -> Any:
        try:
            from core.config_registry import _REGISTRY_MAP
            entry = _REGISTRY_MAP.get(key)
            if entry and entry.type == "int":
                return int(value)
            if entry and entry.type == "float":
                return float(value)
            if entry and entry.type == "bool":
                if isinstance(value, bool):
                    return value
                if isinstance(value, str):
                    return value.lower() in ("1", "true", "yes", "on")
                return bool(value)
        except ImportError:
            pass
        return value

    def set(self, key: str, value: Any, persist: bool = True):
        self._overrides[key] = value
        if persist:
            settings_path = Path(os.environ.get("JARVIS_SETTINGS_FILE", "data/settings.json"))
            try:
                current = {}
                if settings_path.exists():
                    with open(settings_path, encoding="utf-8") as f:
                        current = json.load(f)
                current[key] = value
                settings_path.parent.mkdir(parents=True, exist_ok=True)
                with open(settings_path, "w", encoding="utf-8") as f:
                    json.dump(current, f, indent=2, default=str)
            except Exception as e:
                logger.warning("[Config] Failed to persist %s=%s: %s", key, value, e)
        self._fire_on_change(key, value)
        self._emit_config_changed(key, value)

    def _emit_config_changed(self, key: str, value: Any):
        try:
            global_event_bus.publish_sync(
                Event(type=CONFIG_CHANGED, source="config.service",
                      payload={"key": key, "value": value})
            )
        except Exception:
            logger.debug("[Config] Failed to emit config.changed event", exc_info=True)

    def reset(self, key: str):
        self._overrides.pop(key, None)

    def reset_all(self):
        self._overrides.clear()

    # ── Change listeners ───────────────────────────────────────

    def on_change(self, key: str, callback: Callable):
        self._listeners.setdefault(key, []).append(callback)

    def _fire_on_change(self, key: str, value: Any):
        for cb in self._listeners.get(key, []):
            try:
                cb(value)
            except Exception as e:
                logger.warning("[Config] on_change callback failed for %s: %s", key, e)

    # ── Introspection ──────────────────────────────────────────

    def as_dict(self, category: str | None = None) -> dict:
        try:
            from core.config_registry import _REGISTRY
            result = {}
            for entry in _REGISTRY:
                if category and entry.category != category:
                    continue
                result[entry.key] = self.get(entry.key)
            return result
        except ImportError:
            return dict(self._flat_config)

    def _mask_secret(self, value: Any) -> Any:
        if value and isinstance(value, str) and len(value) > 8:
            return value[:4] + "****" + value[-4:]
        return value

    def as_api_dict(self, category: str | None = None) -> list[dict]:
        try:
            from core.config_registry import _REGISTRY
            result = []
            for entry in _REGISTRY:
                if category and entry.category != category:
                    continue
                resolved = self.get(entry.key)
                display_value = self._mask_secret(resolved) if entry.secret else resolved
                is_overridden = entry.key in self._overrides
                result.append({
                    "key": entry.key,
                    "value": display_value,
                    "default": entry.default,
                    "type": entry.type,
                    "category": entry.category,
                    "description": entry.description,
                    "ui": entry.ui,
                    "options": entry.options,
                    "options_provider": entry.options_provider,
                    "restart_required": entry.restart_required,
                    "min_value": entry.min_value,
                    "max_value": entry.max_value,
                    "env_var": entry.env_var,
                    "is_overridden": is_overridden,
                })
            return result
        except ImportError:
            return []

    # ── Backward-compat dot access ─────────────────────────────

    class _Proxy:
        def __init__(self, config, prefix):
            self._config = config
            self._prefix = prefix

        def __getattr__(self, name):
            if name.startswith("_"):
                raise AttributeError(name)
            full_key = f"{self._prefix}.{name}" if self._prefix else name
            val = self._config.get(full_key)
            if val is None:
                raise AttributeError(f"Config has no key: {full_key}")
            return val

        def __setattr__(self, name, value):
            if name.startswith("_"):
                super().__setattr__(name, value)
            else:
                full_key = f"{self._prefix}.{name}" if self._prefix else name
                self._config.set(full_key, value)

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self._Proxy(self, name)

    # ── Capability-based model resolution ──────────────────────

    def resolve(self, capability: str) -> str:
        routing = self._providers.get("routing", {})
        preference = routing.get(capability, "auto")

        if preference == "auto":
            return self._auto_resolve(capability)
        if "/" in preference:
            return preference
        for prov_name, prov_cfg in self._providers.get("providers", {}).items():
            if prov_cfg.get("enabled") and prov_name == preference:
                return self._resolve_for_provider(prov_name, capability)
        return self._auto_resolve(capability)

    def _auto_resolve(self, capability: str) -> str:
        providers_cfg = self._providers.get("providers", {})
        offline = self._providers.get("preferences", {}).get("offline_only", True)
        ollama = providers_cfg.get("ollama", {})
        if ollama.get("enabled", True):
            local_model = self._local_model_for_capability(capability)
            if local_model:
                return f"ollama/{local_model}"
        if not offline:
            for cloud_prov in ("openai", "anthropic"):
                cfg = providers_cfg.get(cloud_prov, {})
                if cfg.get("enabled"):
                    return self._resolve_for_provider(cloud_prov, capability)
        return self._resolve_for_provider("ollama", capability)

    @staticmethod
    def _local_model_for_capability(capability: str) -> str:
        mapping = {
            "chat": "qwen2.5:7b",
            "code": "qwen2.5-coder:3b",
            "analysis": "qwen2.5:7b",
            "reasoning": "deepseek-r1:1.5b",
            "vision": "moondream:latest",
            "grader": "phi3:mini",
            "embedding": "nomic-embed-text:latest",
            "orchestrator": "qwen2.5:7b",
            "fallback": "tinyllama",
            "cloud": "qwen2.5:7b",
        }
        return mapping.get(capability, "qwen2.5:7b")

    @staticmethod
    def _resolve_for_provider(provider: str, capability: str) -> str:
        cloud_models = {
            "openai": {"chat": "gpt-4o", "code": "gpt-4o", "vision": "gpt-4o", "embedding": "text-embedding-3-small"},
            "anthropic": {"chat": "claude-sonnet-4-20250514", "code": "claude-sonnet-4-20250514", "vision": "claude-sonnet-4-20250514"},
        }
        if provider in cloud_models and capability in cloud_models[provider]:
            return f"{provider}/{cloud_models[provider][capability]}"
        local = ConfigurationService._local_model_for_capability(capability)
        return f"{provider}/{local}"

    def get_providers(self) -> dict[str, Any]:
        return dict(self._providers.get("providers", {}))

    def get_routing(self) -> dict[str, str]:
        return dict(self._providers.get("routing", {}))

    def set_provider_enabled(self, name: str, enabled: bool) -> None:
        providers = self._providers.setdefault("providers", {})
        provider = providers.setdefault(name, {})
        provider["enabled"] = enabled
        self._save_providers()

    def set_routing(self, capability: str, preference: str) -> None:
        routing = self._providers.setdefault("routing", {})
        routing[capability] = preference
        self._save_providers()
