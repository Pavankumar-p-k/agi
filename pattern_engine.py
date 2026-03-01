# learning/pattern_engine.py
#
# PATTERN RECOGNITION ENGINE
# ──────────────────────────────────────────────────────────────
# Learns behavioral patterns from user data.
# After enough observations, recognizes patterns like:
#
#  "Every weekday at ~9am → user asks for reminders"
#  "When mood=anxious → user usually asks for task list"
#  "Friday evenings → user usually plays music"
#  "After 10pm → user asks for short replies (tired)"
#  "When intent=code 3+ times → user in deep work mode"
#
# Uses simple frequency analysis + time-series pattern matching.
# No ML library needed — pure Python, runs on any machine.

import json
import time
import math
from collections import defaultdict, Counter
from datetime import datetime
from typing import List, Dict, Any


class PatternEngine:

    def __init__(self, memory):
        self.memory = memory
        # Pattern storage: pattern_key → {count, last_seen, outcomes}
        self._patterns: Dict[str, dict] = {}
        # Time-slot frequency: (hour, day) → [intents]
        self._time_slots: Dict[tuple, list] = defaultdict(list)
        # Sequence patterns: "intent_A → intent_B" frequency
        self._sequences: Counter = Counter()
        self._last_intent = ""

    # ─────────────────────────────────────────────────────
    #  OBSERVE
    # ─────────────────────────────────────────────────────

    async def observe(self, event: dict):
        """Record one user event and update pattern counters."""
        hour    = event.get("hour", datetime.now().hour)
        day     = event.get("day",  datetime.now().weekday())
        intent  = event.get("intent", "")
        emotion = event.get("emotion", "neutral")
        content = event.get("content", "")

        # 1. Time-slot pattern
        slot_key = (hour, day)
        self._time_slots[slot_key].append(intent)

        # 2. Sequence pattern
        if self._last_intent and intent:
            seq = f"{self._last_intent} → {intent}"
            self._sequences[seq] += 1
        self._last_intent = intent

        # 3. Emotion + intent combo
        if emotion != "neutral" and intent:
            combo = f"emotion:{emotion}+intent:{intent}"
            if combo not in self._patterns:
                self._patterns[combo] = {"count": 0, "first_seen": time.time(), "last_seen": 0}
            self._patterns[combo]["count"] += 1
            self._patterns[combo]["last_seen"] = time.time()

        # 4. Hour-based intent pattern
        hour_pattern = f"hour:{hour}+intent:{intent}"
        if hour_pattern not in self._patterns:
            self._patterns[hour_pattern] = {"count": 0, "first_seen": time.time(), "last_seen": 0}
        self._patterns[hour_pattern]["count"] += 1
        self._patterns[hour_pattern]["last_seen"] = time.time()

        # Persist periodically
        if sum(self._patterns[k]["count"] for k in self._patterns) % 20 == 0:
            await self._persist()

    async def learn_from_state(self, state):
        """Called each AGI loop — learn from current world state."""
        await self.observe({
            "hour":    state.hour,
            "day":     state.day_of_week,
            "intent":  "system_observe",
            "emotion": state.pavan_mood,
        })

    # ─────────────────────────────────────────────────────
    #  QUERY PATTERNS
    # ─────────────────────────────────────────────────────

    def get_likely_intent_at(self, hour: int, day: int, top_n: int = 3) -> list:
        """What does Pavan usually do at this time?"""
        slot_key = (hour, day)
        intents  = self._time_slots.get(slot_key, [])
        if not intents:
            # Try hour only (broader)
            intents = []
            for (h, d), v in self._time_slots.items():
                if h == hour:
                    intents.extend(v)
        if not intents:
            return []
        counter  = Counter(intents)
        total    = sum(counter.values())
        result   = []
        for intent, count in counter.most_common(top_n):
            result.append({
                "intent":      intent,
                "frequency":   count,
                "probability": round(count / total, 2),
            })
        return result

    def get_likely_next_intent(self, current_intent: str) -> list:
        """After this intent, what usually comes next?"""
        prefix = f"{current_intent} → "
        results = []
        for seq, count in self._sequences.most_common(50):
            if seq.startswith(prefix):
                next_intent = seq.split(" → ")[1]
                results.append({"next": next_intent, "count": count})
        return results[:3]

    def get_emotion_patterns(self, emotion: str) -> list:
        """When mood is X, what does Pavan usually want?"""
        prefix = f"emotion:{emotion}+intent:"
        results = []
        for key, data in sorted(self._patterns.items(), key=lambda x: -x[1]["count"]):
            if key.startswith(prefix):
                intent = key.split("+intent:")[1]
                results.append({"intent": intent, "count": data["count"]})
        return results[:5]

    def get_all_patterns(self) -> dict:
        """Return full pattern summary."""
        top_sequences = self._sequences.most_common(10)
        top_hourly = {}
        for (h, d), intents in self._time_slots.items():
            if intents:
                c = Counter(intents)
                top_hourly[f"h{h:02d}_d{d}"] = c.most_common(2)
        return {
            "total_patterns":    len(self._patterns),
            "top_sequences":     top_sequences,
            "top_hourly":        top_hourly,
        }

    async def _persist(self):
        """Save patterns to memory DB."""
        await self.memory.save_patterns(self._patterns, self._sequences)


# ──────────────────────────────────────────────────────────────
