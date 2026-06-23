# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
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
                rel = os.path.relpath(path, os.getcwd())
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
        path = os.path.join(directory, "plugin.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
