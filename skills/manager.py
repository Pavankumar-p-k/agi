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

import importlib.util
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

SKILLS_DIR = Path(__file__).parent / "installed"


@dataclass
class SkillManifest:
    name: str
    version: str
    description: str
    author: str = ""
    entry_point: str = ""
    enabled: bool = True
    dependencies: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)


class Skill:
    manifest: SkillManifest

    def __init__(self, manifest: SkillManifest):
        self.manifest = manifest
        self._loaded = False
        self._tools: dict[str, Callable] = {}

    async def on_load(self) -> None:
        self._loaded = True
        logger.info("[Skill] %s v%s loaded", self.manifest.name, self.manifest.version)

    async def on_unload(self) -> None:
        self._loaded = False
        logger.info("[Skill] %s unloaded", self.manifest.name)

    def register_tool(self, name: str, handler: Callable,
                      description: str = "", input_schema: dict | None = None):
        self._tools[name] = {
            "handler": handler,
            "description": description,
            "input_schema": input_schema or {},
        }

    @property
    def tools(self) -> dict[str, dict]:
        return dict(self._tools)

    @property
    def is_loaded(self) -> bool:
        return self._loaded


class SkillManager:
    """Loadable skill packages that extend JARVIS — matching OpenClaw's skills system."""

    def __init__(self):
        self._skills: dict[str, Skill] = {}
        SKILLS_DIR.mkdir(parents=True, exist_ok=True)

    @property
    def skills(self) -> dict[str, Skill]:
        return dict(self._skills)

    def install(self, manifest: SkillManifest, source_path: str | Path) -> Skill | None:
        source = Path(source_path)
        if not source.exists():
            logger.warning("[Skills] Source not found: %s", source)
            return None
        dest = SKILLS_DIR / manifest.name
        dest.mkdir(parents=True, exist_ok=True)
        manifest_path = dest / "skill.json"
        manifest_path.write_text(json.dumps({
            "name": manifest.name,
            "version": manifest.version,
            "description": manifest.description,
            "author": manifest.author,
            "entry_point": manifest.entry_point,
            "dependencies": manifest.dependencies,
            "tools": manifest.tools,
        }, indent=2))
        logger.info("[Skills] Installed: %s v%s", manifest.name, manifest.version)
        return self._load_from_dir(dest)

    def _load_from_dir(self, skill_dir: Path) -> Skill | None:
        manifest_path = skill_dir / "skill.json"
        if not manifest_path.exists():
            logger.warning("[Skills] No manifest in %s", skill_dir)
            return None
        try:
            data = json.loads(manifest_path.read_text())
            manifest = SkillManifest(**data)
            if not manifest.enabled:
                return None
            if not manifest.entry_point:
                logger.warning("[Skills] No entry_point for %s", manifest.name)
                return None
            entry = skill_dir / manifest.entry_point
            if not entry.exists():
                logger.warning("[Skills] Entry %s not found for %s", entry, manifest.name)
                return None
            # Build correct package hierarchy so relative imports work
            rel_path = entry.relative_to(Path(__file__).parent)
            parts = list(rel_path.parent.parts)
            if parts and parts[0] != 'skills':
                parts.insert(0, 'skills')
            pkg_name = '.'.join(parts)
            mod_name = f"{pkg_name}.{entry.stem}"
            # Register parent packages so relative imports resolve
            if 'skills.utils' not in sys.modules:
                utils_spec = importlib.util.spec_from_file_location(
                    'skills.utils', Path(__file__).parent / 'utils.py')
                if utils_spec and utils_spec.loader:
                    utils_mod = importlib.util.module_from_spec(utils_spec)
                    utils_mod.__package__ = 'skills'
                    sys.modules['skills.utils'] = utils_mod
                    utils_spec.loader.exec_module(utils_mod)
            for i in range(1, len(parts)):
                parent_pkg = '.'.join(parts[:i])
                if parent_pkg not in sys.modules:
                    parent_mod = importlib.util.module_from_spec(
                        importlib.machinery.ModuleSpec(parent_pkg, None, is_package=True)
                    )
                    parent_mod.__path__ = []
                    parent_mod.__package__ = parent_pkg
                    sys.modules[parent_pkg] = parent_mod
            spec = importlib.util.spec_from_file_location(mod_name, entry)
            if not spec or not spec.loader:
                return None
            mod = importlib.util.module_from_spec(spec)
            mod.__package__ = pkg_name
            sys.modules[mod_name] = mod
            spec.loader.exec_module(mod)
            skill_class = getattr(mod, "Skill", Skill)
            skill = skill_class(manifest)
            self._skills[manifest.name] = skill
            logger.info("[Skills] Loaded: %s from %s", manifest.name, pkg_name)
            return skill
        except Exception as e:
            logger.exception("[Skills] Load failed for %s: %s", skill_dir, e)
            return None

    def load_all(self) -> None:
        """Search and load all skills in the skills directory recursively."""
        base_path = Path(__file__).parent
        for manifest_path in base_path.rglob("skill.json"):
            if "__pycache__" in str(manifest_path):
                continue
            self._load_from_dir(manifest_path.parent)

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def set_enabled(self, name: str, enabled: bool) -> bool:
        skill = self._skills.get(name)
        if not skill:
            return False
        old = skill.manifest.enabled
        skill.manifest.enabled = enabled
        manifest_path = SKILLS_DIR / name / "skill.json"
        if manifest_path.exists():
            try:
                data = json.loads(manifest_path.read_text())
                data["enabled"] = enabled
                manifest_path.write_text(json.dumps(data, indent=2))
            except Exception:
                skill.manifest.enabled = old
                return False
        return True

    def list(self) -> list[dict]:
        result = []
        for name, s in self._skills.items():
            try:
                loaded = getattr(s, "is_loaded", False)
                if callable(loaded):
                    loaded = loaded()
                tools = getattr(s, "tools", {})
                if callable(tools):
                    tools = tools()
                result.append({
                    "name": s.manifest.name,
                    "version": s.manifest.version,
                    "description": s.manifest.description,
                    "loaded": loaded,
                    "tools": list(tools.keys()),
                })
            except Exception as e:
                logger.warning("[Skills] list() skipped %s: %s", name, e)
                result.append({
                    "name": name,
                    "version": "?",
                    "description": "?",
                    "loaded": False,
                    "tools": [],
                })
        return result

    def get_all_tools(self) -> dict[str, tuple[str, Callable]]:
        tools = {}
        for skill in self._skills.values():
            for tname, tdata in skill.tools.items():
                tools[f"{skill.manifest.name}.{tname}"] = (tdata["description"], tdata["handler"])
        return tools


skill_manager = SkillManager()
