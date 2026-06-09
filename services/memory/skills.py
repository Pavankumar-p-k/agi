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

import json
import logging
import os
from difflib import SequenceMatcher

from services.memory.skill_format import Skill, slugify

logger = logging.getLogger(__name__)


class SkillsManager:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self._skills_file = os.path.join(data_dir, "skills.json")
        self._cache = None

    def _load_all(self) -> list[dict]:
        if self._cache is not None:
            return self._cache
        if not os.path.exists(self._skills_file):
            self._cache = []
            return self._cache
        try:
            with open(self._skills_file, "r") as f:
                self._cache = json.load(f)
        except (json.JSONDecodeError, IOError):
            self._cache = []
        return self._cache

    def _save_all(self, skills: list[dict]):
        self._cache = skills
        os.makedirs(os.path.dirname(self._skills_file), exist_ok=True)
        with open(self._skills_file, "w") as f:
            json.dump(skills, f, indent=2)

    def load(self, owner: str = None) -> list[dict]:
        all_skills = self._load_all()
        if owner:
            return [s for s in all_skills if s.get("owner") == owner]
        return all_skills

    def read_skill_md(self, name: str, owner: str = None) -> str:
        skills = self.load(owner=owner)
        for s in skills:
            if s["name"] == name:
                lines = [f"# {s['name']}", "", s.get("description", "")]
                if s.get("when_to_use"):
                    lines.extend(["", "## When to use", s["when_to_use"]])
                proc = s.get("procedure") or s.get("steps") or []
                if proc:
                    lines.extend(["", "## Procedure"] + [f"{i+1}. {step}" for i, step in enumerate(proc)])
                return "\n".join(lines)
        return ""

    def read_skill_reference(self, name: str, ref: str, owner: str = None) -> str:
        return ""

    def add_skill(self, **kwargs) -> dict:
        skills = self._load_all()
        raw_name = kwargs.get("name", "")
        name = slugify(raw_name) if raw_name else slugify(kwargs.get("title", "untitled"))

        for existing in skills:
            if existing.get("name") == name and existing.get("owner") == kwargs.get("owner"):
                return {"name": name, "_deduped": True, "status": existing.get("status", "draft")}

        sk = Skill(**kwargs)
        entry = {
            "name": name,
            "description": sk.description,
            "version": sk.version,
            "category": sk.category,
            "tags": sk.tags,
            "platforms": sk.platforms,
            "requires_toolsets": sk.requires_toolsets,
            "fallback_for_toolsets": sk.fallback_for_toolsets,
            "status": sk.status,
            "confidence": sk.confidence,
            "source": sk.source,
            "teacher_model": sk.teacher_model,
            "owner": sk.owner,
            "when_to_use": sk.when_to_use,
            "procedure": sk.procedure,
            "pitfalls": sk.pitfalls,
            "verification": sk.verification,
            "body_extra": sk.body_extra,
        }
        skills.append(entry)
        self._save_all(skills)
        return {"name": name, "_deduped": False, "status": sk.status}

    def update_skill(self, name: str, data: dict, owner: str = None) -> bool:
        skills = self._load_all()
        for i, s in enumerate(skills):
            if s["name"] == name and (owner is None or s.get("owner") == owner):
                skills[i].update(data)
                self._save_all(skills)
                return True
        return False

    def delete_skill(self, name: str, owner: str = None) -> bool:
        skills = self._load_all()
        before = len(skills)
        skills[:] = [s for s in skills if not (s["name"] == name and (owner is None or s.get("owner") == owner))]
        if len(skills) < before:
            self._save_all(skills)
            return True
        return False

    def get_relevant_skills(self, query: str, skills: list[dict], max_items: int = 5) -> list[dict]:
        if not query:
            return skills[:max_items]
        q = query.lower()
        scored = []
        for s in skills:
            score = 0.0
            name = (s.get("name") or "").lower()
            desc = (s.get("description") or "").lower()
            when = (s.get("when_to_use") or "").lower()
            tags = " ".join(s.get("tags") or []).lower()
            combined = f"{name} {desc} {when} {tags}"
            score = SequenceMatcher(None, q, combined).ratio()
            if q in name:
                score += 0.3
            if any(word in combined for word in q.split()):
                score += 0.1
            scored.append((score, s))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [s for _, s in scored[:max_items] if _ > 0.1]
