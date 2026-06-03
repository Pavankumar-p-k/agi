# core/plugins/manifest.py
# PluginManifest — structured definition of a JARVIS plugin/skill
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
import json
import os


@dataclass
class PluginManifest:
    id: str
    name: str
    version: str                    # semver, e.g. "1.0.0"
    description: str
    author: str
    entry: str                      # python import path, e.g. "skills.library.entertainment.spotify.main"
    hooks: list[str]                = field(default_factory=list)
    settings_schema: dict[str, Any] = field(default_factory=dict)
    requires: list[str]             = field(default_factory=list)
    min_jarvis_version: str         = "1.0.0"
    enabled: bool                   = True

    # ------------------------------------------------------------------ #
    @classmethod
    def from_dict(cls, data: dict) -> "PluginManifest":
        for required in ("id", "name", "entry"):
            if required not in data:
                raise TypeError(f"Missing required plugin manifest field: '{required}'")
        return cls(
            id                  = data["id"],
            name                = data["name"],
            version             = data.get("version", "1.0.0"),
            description         = data.get("description", ""),
            author              = data.get("author", "unknown"),
            entry               = data["entry"],
            hooks               = data.get("hooks", []),
            settings_schema     = data.get("settings_schema", {}),
            requires            = data.get("requires", []),
            min_jarvis_version  = data.get("min_jarvis_version", "1.0.0"),
            enabled             = data.get("enabled", True),
        )

    @classmethod
    def from_file(cls, path: str) -> "PluginManifest":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Handle legacy skill.json / missing ID or entry
        if "id" not in data and "name" in data:
            data["id"] = data["name"]
        
        if "entry" not in data:
            # Calculate module path from file system path
            # e.g., C:\...\skills\library\ent\games\skill.json -> skills.library.ent.games.main
            rel = os.path.relpath(path, os.getcwd())
            parts = rel.replace("\\", "/").split("/")[:-1] # Remove filename
            entry_point = data.get("entry_point", "main.py").replace(".py", "")
            data["entry"] = ".".join(parts + [entry_point])

        return cls.from_dict(data)

    def to_dict(self) -> dict:
        return {
            "id":                   self.id,
            "name":                 self.name,
            "version":              self.version,
            "description":          self.description,
            "author":               self.author,
            "entry":                self.entry,
            "hooks":                self.hooks,
            "settings_schema":      self.settings_schema,
            "requires":             self.requires,
            "min_jarvis_version":   self.min_jarvis_version,
            "enabled":              self.enabled,
        }

    def save(self, directory: str) -> None:
        path = os.path.join(directory, "plugin.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
