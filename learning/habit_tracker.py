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

"""Habit tracking for JARVIS.

Learns *repeated, verified activities* — the simple frequency layer under the
pattern engine.  A goal or action observed repeatedly becomes a habit the
planner can anticipate (e.g. "check GitHub notifications" every morning).

Design constraints (per the integration plan):
- No new storage system: a bounded in-memory ring per key.  Durable,
  goal-level reuse lives in the memory facade's experience store; durable
  patterns live in the PatternEngine's persistence sink.
- Never raises: habit learning must not be able to break a caller.
"""
from __future__ import annotations

import logging
import time
from collections import deque
from typing import Any, Deque, Dict, Optional

logger = logging.getLogger(__name__)

# Observations kept per habit key (bounded memory, no unbounded growth)
_RING_SIZE = 50
# A habit counts as "established" at this many observations
_ESTABLISHED_AT = 3


def _normalize_key(text: str) -> str:
    return " ".join(str(text).lower().split())[:80]


class HabitTracker:
    """Tracks repeated goals/actions with success rates and recency."""

    def __init__(self, memory: Any = None, *, max_records: int = _RING_SIZE) -> None:
        # ``memory`` is accepted for backward compatibility with the old
        # placeholder signature; the tracker itself stays storage-free.
        self.memory = memory
        self.max_records = max_records
        self._events: Dict[str, Deque[dict]] = {}
        self._stats: Dict[str, Any] = {
            "updates": 0,
            "goals_observed": 0,
            "actions_observed": 0,
        }

    # ------------------------------------------------------------------ #
    # Recording (called by learning listeners)                           #
    # ------------------------------------------------------------------ #

    def record_outcome(self, goal: str, *, success: bool = True,
                       verified: bool = False, user_id: str = "default") -> None:
        """Record one completed goal execution."""
        key = _normalize_key(goal)
        if not key:
            return
        self._record(key, {"ts": time.time(), "success": bool(success),
                           "verified": bool(verified), "user_id": user_id})
        self._stats["goals_observed"] += 1

    def record_event(self, name: str, *, success: bool = True,
                     kind: str = "action") -> None:
        """Record one lower-level action observation."""
        key = _normalize_key(f"{kind}:{name}" if name else kind)
        if not key:
            return
        self._record(key, {"ts": time.time(), "success": bool(success)})
        self._stats["actions_observed"] += 1

    # ------------------------------------------------------------------ #
    # Queries                                                            #
    # ------------------------------------------------------------------ #

    def habit_strength(self, key: str) -> Optional[dict]:
        """Observation count, success rate, recency, and established flag."""
        events = self._events.get(_normalize_key(key))
        if not events:
            return None
        now = time.time()
        successes = sum(1 for e in events if e.get("success"))
        last_24h = sum(1 for e in events if now - e["ts"] <= 86400)
        last_7d = sum(1 for e in events if now - e["ts"] <= 7 * 86400)
        return {
            "key": _normalize_key(key),
            "count": len(events),
            "success_rate": round(successes / len(events), 2),
            "last_24h": last_24h,
            "last_7d": last_7d,
            "last_seen": events[-1]["ts"],
            "established": len(events) >= _ESTABLISHED_AT,
        }

    def top_habits(self, limit: int = 10) -> list[dict]:
        """Strongest habits, strongest first."""
        habits = []
        for key in self._events:
            strength = self.habit_strength(key)
            if strength:
                habits.append(strength)
        habits.sort(key=lambda h: (h["count"], h["last_seen"]), reverse=True)
        return habits[:limit]

    # ------------------------------------------------------------------ #
    # Legacy API (preserved)                                             #
    # ------------------------------------------------------------------ #

    async def update(self, state: Any) -> None:
        """Legacy hook: called each AGI loop with the current state object.

        Previously a no-op placeholder; now derives an observation key from
        common state attributes when available.  Never raises.
        """
        self._stats["updates"] += 1
        try:
            key = getattr(state, "current_goal", None) or getattr(state, "intent", None)
            if isinstance(key, str) and key.strip():
                self.record_outcome(key, success=True, verified=False)
        except Exception as exc:
            logger.debug("[habit_tracker] update failed: %s", exc)
        return None

    def get_stats(self) -> Dict[str, Any]:
        """Return tracker statistics (legacy key ``updates`` preserved)."""
        return {
            **self._stats,
            "tracked_habits": len(self._events),
        }

    # ------------------------------------------------------------------ #
    # Internals                                                          #
    # ------------------------------------------------------------------ #

    def _record(self, key: str, event: dict) -> None:
        try:
            ring = self._events.setdefault(key, deque(maxlen=self.max_records))
            ring.append(event)
        except Exception as exc:
            logger.debug("[habit_tracker] record failed: %s", exc)
