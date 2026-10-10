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

"""core.plugins.manifest — declarative plugin manifest with file persistence."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any


@dataclass
class PluginManifest:
    """Manifest describing a plugin package (id, entry point, hooks, settings)."""

    id: str
    name: str
    version: str
    description: str = ""
    author: str = ""
    entry: str = ""
    hooks: list[str] = field(default_factory=list)
    settings_schema: dict[str, Any] = field(default_factory=dict)
    requires: list[str] = field(default_factory=list)
    enabled: bool = True

    # ── serialization ────────────────────────────────────────────────────────
    def to_dict(self) -> dict[str, Any]:
        return {
            f.name: getattr(self, f.name)
            for f in fields(self)
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PluginManifest":
        valid = {f.name for f in fields(cls)}
        kwargs = {k: v for k, v in data.items() if k in valid}
        missing = [name for name in ("id", "name", "entry") if not kwargs.get(name)]
        if missing:
            raise TypeError(f"PluginManifest missing required fields: {missing}")
        return cls(**kwargs)

    # ── persistence ─────────────────────────────────────────────────────────
    def save(self, directory: str | Path) -> Path:
        path = Path(directory) / "plugin.json"
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return path

    @classmethod
    def from_file(cls, path: str | Path) -> "PluginManifest":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)


__all__ = ["PluginManifest"]
