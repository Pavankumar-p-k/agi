from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class PluginConfigStore:
    def __init__(self, config_dir: str | Path | None = None):
        if config_dir is None:
            config_dir = Path(os.getcwd()) / "data" / "plugin_configs"
        self._config_dir = Path(config_dir)
        self._config_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, dict] = {}

    def _path(self, plugin_name: str) -> Path:
        safe = plugin_name.replace(".", "_").replace("/", "_")
        return self._config_dir / f"{safe}.json"

    def load(self, plugin_name: str) -> dict:
        if plugin_name in self._cache:
            return dict(self._cache[plugin_name])
        path = self._path(plugin_name)
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self._cache[plugin_name] = data
                return dict(data)
            except Exception as e:
                logger.warning("[PluginConfig] Failed to load config for %s: %s", plugin_name, e)
        self._cache[plugin_name] = {}
        return {}

    def save(self, plugin_name: str, config: dict) -> None:
        self._cache[plugin_name] = dict(config)
        path = self._path(plugin_name)
        try:
            path.write_text(json.dumps(config, indent=2, default=str), encoding="utf-8")
        except Exception as e:
            logger.warning("[PluginConfig] Failed to save config for %s: %s", plugin_name, e)

    def get(self, plugin_name: str, key: str, default: Any = None) -> Any:
        cfg = self.load(plugin_name)
        return cfg.get(key, default)

    def set(self, plugin_name: str, key: str, value: Any) -> None:
        cfg = self.load(plugin_name)
        cfg[key] = value
        self.save(plugin_name, cfg)

    def delete(self, plugin_name: str, key: str) -> None:
        cfg = self.load(plugin_name)
        cfg.pop(key, None)
        self.save(plugin_name, cfg)

    def clear_cache(self) -> None:
        self._cache.clear()
