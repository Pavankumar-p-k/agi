"""core/plugins/manifest.py
DEPRECATED — re-exports PluginManifest from base.py for backward compatibility.
New code should import from core.plugins.base import PluginManifest.

Deprecated: v3.2
Remove after: v4.0
"""
from __future__ import annotations

import json
import logging
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.plugins.base import PluginManifest as _BaseManifest

logger = logging.getLogger(__name__)
warnings.warn(
    "Import PluginManifest from core.plugins.base instead of core.plugins.manifest",
    DeprecationWarning, stacklevel=2,
)


@dataclass
class PluginManifest:
    id: str
    name: str
    version: str = "1.0.0"
    description: str = ""
    author: str = "unknown"
    entry: str = ""
    hooks: list[str] = field(default_factory=list)
    settings_schema: dict[str, Any] = field(default_factory=dict)
    requires: list[str] = field(default_factory=list)
    min_jarvis_version: str = "1.0.0"
    enabled: bool = True

    def to_base(self) -> _BaseManifest:
        return _BaseManifest(
            name=self.name,
            version=self.version,
            description=self.description,
            author=self.author,
            entry_point=self.entry,
            enabled=self.enabled,
            config_schema=self.settings_schema if self.settings_schema else None,
            dependencies=list(self.requires),
            hooks=list(self.hooks),
            id=self.id,
            requires=list(self.requires),
            min_jarvis_version=self.min_jarvis_version,
        )

    @classmethod
    def from_dict(cls, data: dict) -> PluginManifest:
        for required in ("id", "name"):
            if required not in data:
                raise TypeError(f"Missing required field: '{required}'")
        return cls(
            id=data["id"],
            name=data["name"],
            version=data.get("version", "1.0.0"),
            description=data.get("description", ""),
            author=data.get("author", "unknown"),
            entry=data.get("entry", ""),
            hooks=data.get("hooks", []),
            settings_schema=data.get("settings_schema", {}),
            requires=data.get("requires", []),
            min_jarvis_version=data.get("min_jarvis_version", "1.0.0"),
            enabled=data.get("enabled", True),
        )

    @classmethod
    def from_file(cls, path: str) -> PluginManifest:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if "id" not in data and "name" in data:
            data["id"] = data["name"]
        if not data.get("entry"):
            entry_point = data.get("entry_point", "").replace(".py", "")
            if entry_point:
                import os as _os
                rel = _os.path.relpath(path, _os.getcwd())
                parts = rel.replace("\\", "/").split("/")[:-1]
                data["entry"] = ".".join(parts + [entry_point])
            else:
                data["entry"] = data.get("id", "plugin")
        return cls.from_dict(data)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "entry": self.entry,
            "hooks": self.hooks,
            "settings_schema": self.settings_schema,
            "requires": self.requires,
            "min_jarvis_version": self.min_jarvis_version,
            "enabled": self.enabled,
        }

    def save(self, directory: str):
        path = Path(directory) / "plugin.json"
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")


def from_file(path: str | Path) -> PluginManifest:
    return PluginManifest.from_file(str(path))
