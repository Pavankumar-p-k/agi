"""KnobStore — persistent JSON-backed storage for behavior knob values.

Each knob has a current_value that can differ from its default_value.
The store persists to knobs.json for crash recovery and auditing.
"""

from __future__ import annotations

import json
import logging
from threading import RLock
from pathlib import Path
from typing import Any

from core.improvement.models import DEFAULT_KNOBS_JSON, BehaviorKnob, KNOB_REGISTRY, KnobCategory

logger = logging.getLogger(__name__)


class KnobStore:
    """Persistent, thread-safe store for behavior knob values.

    Loaded from knobs.json on init. Subsystems read knobs via get().
    """

    def __init__(self, json_path: str | None = None):
        self._path = Path(json_path or DEFAULT_KNOBS_JSON)
        self._lock = RLock()
        self._knobs: dict[str, BehaviorKnob] = {}
        self._load()

    def _load(self) -> None:
        """Load persisted knob values, falling back to registry defaults."""
        self._knobs = {k: self._clone(v) for k, v in KNOB_REGISTRY.items()}
        if self._path.exists():
            try:
                with self._lock, open(self._path, "r") as f:
                    saved: dict[str, Any] = json.load(f)
                for name, value in saved.items():
                    if name in self._knobs:
                        self._knobs[name].current_value = value
            except Exception:
                logger.exception("KnobStore: failed to load %s", self._path)

    def _save(self) -> None:
        """Persist current knob values to JSON."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {name: knob.current_value for name, knob in self._knobs.items()}
        with self._lock, open(self._path, "w") as f:
            json.dump(data, f, indent=2)

    def get(self, name: str) -> Any:
        """Get the current value of a knob."""
        with self._lock:
            knob = self._knobs.get(name)
            if knob is None:
                return None
            return knob.current_value

    def set(self, name: str, value: Any) -> bool:
        """Set a knob value, respecting bounds. Returns True if set."""
        with self._lock:
            knob = self._knobs.get(name)
            if knob is None:
                logger.warning("KnobStore: unknown knob %s", name)
                return False
            value = self._clamp(knob, value)
            knob.current_value = value
            self._save()
            logger.info("KnobStore: %s = %s", name, value)
            return True

    def get_all(self) -> dict[str, BehaviorKnob]:
        with self._lock:
            return {k: self._clone(v) for k, v in self._knobs.items()}

    def get_by_category(self, category: KnobCategory) -> dict[str, BehaviorKnob]:
        with self._lock:
            return {k: self._clone(v) for k, v in self._knobs.items() if v.category == category}

    def reset(self, name: str) -> bool:
        """Reset a knob to its default value."""
        with self._lock:
            knob = self._knobs.get(name)
            if knob is None:
                return False
            knob.current_value = knob.default_value
            self._save()
            return True

    def reset_all(self) -> None:
        with self._lock:
            for knob in self._knobs.values():
                knob.current_value = knob.default_value
            self._save()

    def get_snapshot(self) -> dict[str, Any]:
        """Return a snapshot of all current values for rollback."""
        with self._lock:
            return {n: k.current_value for n, k in self._knobs.items()}

    def apply_snapshot(self, snapshot: dict[str, Any]) -> None:
        """Restore a snapshot (for rollback)."""
        with self._lock:
            for name, value in snapshot.items():
                if name in self._knobs:
                    self._knobs[name].current_value = value
            self._save()

    @staticmethod
    def _clone(knob: BehaviorKnob) -> BehaviorKnob:
        return BehaviorKnob(
            name=knob.name,
            category=knob.category,
            current_value=knob.current_value,
            default_value=knob.default_value,
            min_value=knob.min_value,
            max_value=knob.max_value,
            allowed_values=knob.allowed_values,
            description=knob.description,
            tags=list(knob.tags),
        )

    @staticmethod
    def _clamp(knob: BehaviorKnob, value: Any) -> Any:
        if knob.allowed_values is not None:
            if value not in knob.allowed_values:
                return knob.current_value
            return value
        if isinstance(value, (int, float)) and knob.min_value is not None:
            value = max(knob.min_value, value)
        if isinstance(value, (int, float)) and knob.max_value is not None:
            value = min(knob.max_value, value)
        return value
