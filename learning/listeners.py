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

"""Event-driven learning wiring.

Connects the EventBus (core/event_bus.py) to the learning components — the
plan's "Experience → Learning / Patterns" layer:

    specialists publish  goal.completed / action.verified / user.message
        ↓ EventBus (no direct coupling)
    LearningHub
        ├─→ memory facade .record_experience()   (reusable procedures)
        ├─→ HabitTracker                         (repeated verified activities)
        └─→ PatternEngine                        (time/sequence patterns)

Standard event contract (publishers should use these names):

    goal.completed    {goal, success, verified, actions, error, evidence,
                       specialist, user_id}
    action.verified   {action, success, specialist}
    user.message      {content, intent, emotion, user_id}

Subscribing never raises into the producer: the EventBus isolates handler
errors, so a broken learning component cannot break a specialist.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from core.event_bus import EventBus, global_event_bus

logger = logging.getLogger(__name__)

# Canonical event names
EVENT_GOAL_COMPLETED = "goal.completed"
EVENT_ACTION_VERIFIED = "action.verified"
EVENT_USER_MESSAGE = "user.message"


class _PatternPersistenceAdapter:
    """Gives PatternEngine a ``save_patterns`` sink without new memory systems.

    PatternEngine only ever calls ``memory.save_patterns(patterns, sequences)``
    (async).  We persist a bounded JSON snapshot under ``data/`` so learned
    counters survive restarts; loading is best-effort.
    """

    def __init__(self, path: str | Path | None = None):
        if path is None:
            data_dir = Path(__file__).resolve().parent.parent / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            path = data_dir / "learning_patterns.json"
        self._path = Path(path)

    async def save_patterns(self, patterns: dict, sequences: Any) -> None:
        try:
            payload = {
                "patterns": patterns,
                "sequences": dict(sequences) if hasattr(sequences, "items") else {},
                "saved_at": __import__("time").time(),
            }
            self._path.write_text(json.dumps(payload, default=str), encoding="utf-8")
        except Exception as exc:
            logger.debug("[learning] pattern persistence failed: %s", exc)

    def load(self) -> dict | None:
        try:
            if self._path.exists():
                return json.loads(self._path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.debug("[learning] pattern load failed: %s", exc)
        return None


class LearningHub:
    """Subscribes learning components to the EventBus.

    Owns no memory of its own beyond in-memory counters: experience goes to
    the memory facade (episodic store), patterns to the PatternEngine with a
    JSON persistence sink, habits to the HabitTracker's bounded ring.
    """

    def __init__(
        self,
        bus: EventBus | None = None,
        *,
        memory: Any = None,
        pattern_engine: Any = None,
        habit_tracker: Any = None,
    ):
        self.bus = bus or global_event_bus
        if memory is None:
            try:
                from memory.memory_facade import memory as memory
            except Exception:
                memory = None
        self.memory = memory

        if pattern_engine is None:
            from learning.pattern_engine import PatternEngine
            adapter = _PatternPersistenceAdapter()
            pattern_engine = PatternEngine(adapter)
            saved = adapter.load()
            if saved:
                try:
                    pattern_engine._patterns = saved.get("patterns", {})
                    from collections import Counter
                    pattern_engine._sequences = Counter(saved.get("sequences", {}))
                except Exception:
                    pass
        self.pattern_engine = pattern_engine

        if habit_tracker is None:
            from learning.habit_tracker import HabitTracker
            habit_tracker = HabitTracker(memory)
        self.habit_tracker = habit_tracker

        self._attached = False

    # ------------------------------------------------------------------ #
    # Subscription                                                       #
    # ------------------------------------------------------------------ #

    def attach(self) -> "LearningHub":
        if self._attached:
            return self
        self.bus.subscribe(EVENT_GOAL_COMPLETED, self.handle_goal_completed)
        self.bus.subscribe(EVENT_ACTION_VERIFIED, self.handle_action_verified)
        self.bus.subscribe(EVENT_USER_MESSAGE, self.handle_user_message)
        self._attached = True
        return self

    # ------------------------------------------------------------------ #
    # Handlers                                                           #
    # ------------------------------------------------------------------ #

    def handle_goal_completed(self, event: dict | Any) -> None:
        """Record a finished goal as experience + habit observation.

        Sync on purpose: sqlite writes are blocking; the EventBus supports
        plain callables.  Failures are contained here and logged.
        """
        data = self._payload(event)
        goal = str(data.get("goal", "")).strip()
        if not goal:
            return
        try:
            if self.memory is not None and hasattr(self.memory, "record_experience"):
                self.memory.record_experience(
                    goal,
                    list(data.get("actions") or []),
                    verified=bool(data.get("verified", data.get("success", False))),
                    error=data.get("error") or None,
                    evidence=data.get("evidence") or None,
                    specialist=str(data.get("specialist", "")),
                    user_id=str(data.get("user_id", "default")),
                )
        except Exception as exc:
            logger.warning("[learning] experience recording failed: %s", exc)
        try:
            self.habit_tracker.record_outcome(
                goal,
                success=bool(data.get("success", False)),
                verified=bool(data.get("verified", data.get("success", False))),
                user_id=str(data.get("user_id", "default")),
            )
        except Exception as exc:
            logger.warning("[learning] habit update failed: %s", exc)

    def handle_action_verified(self, event: dict | Any) -> None:
        data = self._payload(event)
        try:
            self.habit_tracker.record_event(
                str(data.get("action", "")),
                success=bool(data.get("success", False)),
                kind="action",
            )
        except Exception as exc:
            logger.debug("[learning] action observation failed: %s", exc)

    async def handle_user_message(self, event: dict | Any) -> None:
        """Feed the pattern engine from user messages (async handler — the
        EventBus awaits coroutines on both publish paths)."""
        data = self._payload(event)
        try:
            await self.pattern_engine.observe({
                "intent": data.get("intent", ""),
                "emotion": data.get("emotion", "neutral"),
                "content": data.get("content", ""),
            })
        except Exception as exc:
            logger.warning("[learning] pattern observation failed: %s", exc)

    # ------------------------------------------------------------------ #
    # Introspection                                                      #
    # ------------------------------------------------------------------ #

    def summary(self) -> dict:
        return {
            "attached": self._attached,
            "habits": self.habit_tracker.get_stats(),
            "patterns": self.pattern_engine.get_all_patterns()
            if hasattr(self.pattern_engine, "get_all_patterns") else {},
        }

    # ------------------------------------------------------------------ #
    # Helpers                                                            #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _payload(event: dict | Any) -> dict:
        if isinstance(event, dict):
            return event
        return getattr(event, "data", None) or {}


_hub: LearningHub | None = None


def get_learning_hub(bus: EventBus | None = None) -> LearningHub:
    """Process-wide hub (created and attached on first call)."""
    global _hub
    if _hub is None:
        _hub = LearningHub(bus=bus).attach()
    return _hub


def attach_default_listeners(bus: EventBus | None = None) -> LearningHub:
    """Explicit attach entry point for application startup."""
    return get_learning_hub(bus)
