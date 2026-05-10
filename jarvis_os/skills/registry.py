from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from ..contracts import SkillRecord


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _slug(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return cleaned[:48] or "workflow"


class SkillRegistry:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.skills_file = self.data_dir / "skills.json"
        self._skills: dict[str, SkillRecord] = {}
        self._load()

    def _load(self) -> None:
        if not self.skills_file.exists():
            return
        raw = self.skills_file.read_text(encoding="utf-8").strip()
        if not raw:
            return
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = []
        for item in payload:
            record = SkillRecord(**item)
            self._skills[record.name] = record

    def _persist(self) -> None:
        rows = [record.to_dict() for record in sorted(self._skills.values(), key=lambda item: item.name)]
        self.skills_file.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    def list(self) -> list[SkillRecord]:
        return sorted(self._skills.values(), key=lambda item: (-item.use_count, item.name))

    def get(self, name: str) -> SkillRecord | None:
        return self._skills.get(name)

    def match(self, prompt: str, intent_name: str) -> SkillRecord | None:
        normalized_prompt = _normalize(prompt)
        best: tuple[int, SkillRecord] | None = None
        for skill in self._skills.values():
            if skill.intent != intent_name:
                continue
            score = 0
            if _normalize(skill.source_prompt) == normalized_prompt:
                score += 10
            for phrase in skill.trigger_phrases:
                phrase_normalized = _normalize(phrase)
                if phrase_normalized == normalized_prompt:
                    score += 8
                elif phrase_normalized and phrase_normalized in normalized_prompt:
                    score += 4
            if score and (best is None or score > best[0]):
                best = (score, skill)
        if best:
            return best[1]
        return None

    def promote(self, prompt: str, intent_name: str, plan: dict[str, Any], execution: dict[str, Any]) -> SkillRecord | None:
        results = execution.get("results", [])
        if not results or not execution.get("success"):
            return None
        steps = plan.get("steps", [])
        if not steps:
            return None
        name = f"{intent_name}_{_slug(prompt)}"
        existing = self._skills.get(name)
        if existing is None:
            record = SkillRecord(
                name=name,
                intent=intent_name,
                description=f"Learned workflow for: {prompt}",
                source_prompt=prompt,
                trigger_phrases=[prompt],
                steps=steps,
                use_count=0,
                success_count=1,
                promoted_at=time.time(),
            )
        else:
            record = existing
            if prompt not in record.trigger_phrases:
                record.trigger_phrases.append(prompt)
            record.steps = steps
            record.success_count += 1
        self._skills[name] = record
        self._persist()
        return record

    def record_use(self, name: str) -> SkillRecord | None:
        record = self._skills.get(name)
        if record is None:
            return None
        record.use_count += 1
        self._persist()
        return record
