"""Capability Experience and Epistemic Learning Engine.

Enables JARVIS to learn how to use capabilities it encounters ("learning like a child").
Instead of relearning how to perform tasks from scratch, it records empirical
recipes of successful multi-capability executions, requirements, and verification patterns.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class CapabilityExperienceEntry:
    pattern_key: str
    goal_intent: str
    capabilities_used: list[str]
    parameters_template: dict[str, Any] = field(default_factory=dict)
    verification_method: str = "standard"
    success_count: int = 1
    failure_count: int = 0
    last_success_timestamp: float = field(default_factory=time.time)
    notes: list[str] = field(default_factory=list)

    @property
    def reliability_score(self) -> float:
        total = self.success_count + self.failure_count
        if total == 0:
            return 1.0
        return round(self.success_count / total, 3)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern_key": self.pattern_key,
            "goal_intent": self.goal_intent,
            "capabilities_used": self.capabilities_used,
            "parameters_template": self.parameters_template,
            "verification_method": self.verification_method,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "reliability_score": self.reliability_score,
            "last_success_timestamp": self.last_success_timestamp,
            "notes": self.notes,
        }


class CapabilityExperienceStore:
    """Stores and retrieves learned operational recipes."""

    def __init__(self, persistence_file: Optional[Path | str] = None) -> None:
        self._entries: dict[str, CapabilityExperienceEntry] = {}
        self.persistence_file = Path(persistence_file) if persistence_file else None
        if self.persistence_file and self.persistence_file.exists():
            self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self.persistence_file.read_text(encoding="utf-8"))
            for k, v in raw.items():
                self._entries[k] = CapabilityExperienceEntry(**v)
        except Exception as ex:
            logger.warning("Failed to load experience store: %s", ex)

    def _save(self) -> None:
        if self.persistence_file:
            try:
                self.persistence_file.parent.mkdir(parents=True, exist_ok=True)
                data = {k: v.to_dict() for k, v in self._entries.items()}
                self.persistence_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
            except Exception as ex:
                logger.warning("Failed to save experience store: %s", ex)

    def record_experience(
        self,
        pattern_key: str,
        goal_intent: str,
        capabilities_used: list[str],
        parameters_template: Optional[dict[str, Any]] = None,
        verification_method: str = "standard",
        success: bool = True,
        note: Optional[str] = None,
    ) -> CapabilityExperienceEntry:
        """Record or reinforce a learned capability sequence."""
        key = pattern_key.lower().strip()
        if key in self._entries:
            entry = self._entries[key]
            if success:
                entry.success_count += 1
                entry.last_success_timestamp = time.time()
                if capabilities_used:
                    entry.capabilities_used = capabilities_used
            else:
                entry.failure_count += 1
            if note:
                entry.notes.append(note)
        else:
            entry = CapabilityExperienceEntry(
                pattern_key=key,
                goal_intent=goal_intent,
                capabilities_used=list(capabilities_used),
                parameters_template=dict(parameters_template or {}),
                verification_method=verification_method,
                success_count=1 if success else 0,
                failure_count=0 if success else 1,
                last_success_timestamp=time.time(),
                notes=[note] if note else [],
            )
            self._entries[key] = entry

        self._save()
        logger.info("Recorded experience for '%s': reliability=%s", key, entry.reliability_score)
        return entry

    def find_experience(self, goal: str) -> Optional[CapabilityExperienceEntry]:
        """Find a matching learned recipe for a goal intent."""
        goal_tokens = set(goal.lower().replace("-", " ").replace(":", " ").split())
        best_entry: Optional[CapabilityExperienceEntry] = None
        best_score = 0.0

        for entry in self._entries.values():
            if entry.reliability_score < 0.5:
                continue  # Skip historically unreliable recipes
            pattern_tokens = set(entry.pattern_key.lower().replace(":", " ").split())
            intent_tokens = set(entry.goal_intent.lower().split())
            all_tokens = pattern_tokens | intent_tokens

            overlap = len(goal_tokens & all_tokens)
            if overlap > 0:
                score = (overlap / len(goal_tokens)) * entry.reliability_score
                if score > best_score:
                    best_score = score
                    best_entry = entry

        if best_score >= 0.4:
            return best_entry
        return None

    def all_experiences(self) -> list[CapabilityExperienceEntry]:
        return list(self._entries.values())
