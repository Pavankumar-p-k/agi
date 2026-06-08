from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any


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

    @classmethod
    def from_dict(cls, data: dict) -> "PluginManifest":
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
    def from_file(cls, path: str) -> "PluginManifest":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "id" not in data and "name" in data:
            data["id"] = data["name"]
        if not data.get("entry"):
            rel = os.path.relpath(path, os.getcwd())
            parts = rel.replace("\\", "/").split("/")[:-1]
            entry_point = data.get("entry_point", "main").replace(".py", "")
            data["entry"] = ".".join(parts + [entry_point])
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
        path = os.path.join(directory, "plugin.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
