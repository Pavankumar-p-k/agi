from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)

_ARCH_MEMORY_FILE: str = "data/architectural_memory.json"


class ArchitecturalMemory:
    """Stores architectural patterns learned from failures.

    When a plan evolution identifies a missing layer (e.g., no Repository),
    the pattern is stored and injected into future planner prompts.
    """

    def __init__(self, path: str = ""):
        self.path = path or os.path.join(os.path.dirname(__file__), "../..", _ARCH_MEMORY_FILE)
        self._patterns: dict[str, dict] = {}
        self._load()

    def _load(self):
        try:
            if os.path.exists(self.path):
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._patterns = data.get("patterns", {})
        except Exception:
            self._patterns = {}

    def _save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"patterns": self._patterns}, f, indent=2)

    def learn(self, project_type: str, root_cause: str, affected_areas: list[str],
              plan_mutation: dict):
        key = project_type.lower().replace(" ", "_").replace("-", "_")
        if key not in self._patterns:
            self._patterns[key] = {
                "project_type": project_type,
                "lessons": [],
                "required_components": [],
                "hit_count": 0,
            }
        entry = self._patterns[key]
        existing = any(l.get("root_cause") == root_cause for l in entry["lessons"])
        if not existing:
            entry["lessons"].append({
                "root_cause": root_cause,
                "affected_areas": affected_areas,
                "plan_mutation": plan_mutation,
            })
        entry["hit_count"] += 1
        for area in affected_areas:
            if area not in entry["required_components"]:
                entry["required_components"].append(area)
        self._save()

    def get_prompt_suffix(self, objective: str) -> str:
        """Return a string to inject into the planner prompt."""
        lo = objective.lower()
        relevant = []
        for key, entry in self._patterns.items():
            if key.lower() in lo or any(word in lo for word in key.replace("-", " ").replace("_", " ").split()):
                relevant.append(entry)
        if not relevant:
            return ""
        parts = ["", "## Architectural Lessons From Past Projects"]
        for entry in relevant:
            if entry["required_components"]:
                parts.append(
                    f"Previous {entry['project_type']} projects required: "
                    f"{', '.join(entry['required_components'])}. "
                    f"Ensure all are included."
                )
            for lesson in entry["lessons"][-3:]:
                parts.append(f"  - {lesson['root_cause']}")
        return "\n".join(parts)
