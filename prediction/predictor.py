# prediction/predictor.py
#
# PREDICTION ENGINE
# ──────────────────────────────────────────────────────────────
# Uses learned patterns + habits to predict what Pavan needs
# BEFORE he asks for it.
#
# Output: list of predictions with confidence scores.
# High-confidence predictions → sent to Goal Planner for action.
#
# Examples of what it predicts:
#  08:00 weekday  → "Pavan usually wants morning briefing" (0.82)
#  18:00 Friday   → "Pavan usually plays music" (0.75)
#  mood=stressed  → "Pavan usually wants task overview" (0.71)
#  after coding   → "Pavan usually wants a break reminder" (0.68)
#  10 unread msgs → "Pavan may want to check messages" (0.65)

import time
from datetime import datetime
from typing import List, Dict


class PredictionEngine:

    def __init__(self, patterns, habits):
        self.patterns = patterns
        self.habits   = habits
        self._last_predictions: list = []
        self._prediction_cooldowns: dict = {}  # action → last_predicted_ts
        self.COOLDOWN_SEC = 1800   # don't repeat same prediction within 30 min

    async def predict(self, state) -> List[dict]:
        """
        Generate predictions for the current world state.
        Returns list of {action, reason, confidence, tool, params}
        """
        predictions = []
        now = time.time()

        # ── Time-based predictions ──────────────────────────
        likely = self.patterns.get_likely_intent_at(state.hour, state.day_of_week)
        for item in likely:
            if item["probability"] >= 0.35:
                action = self._intent_to_action(item["intent"])
                if action:
                    predictions.append({
                        "action":     action["action"],
                        "tool":       action["tool"],
                        "params":     action["params"],
                        "reason":     f"You usually {action['reason']} at this time",
                        "confidence": item["probability"] * 0.9,
                        "type":       "time_based",
                    })

        # ── Mood-based predictions ───────────────────────────
        if state.pavan_mood not in ("neutral", "happy"):
            mood_patterns = self.patterns.get_emotion_patterns(state.pavan_mood)
            for p in mood_patterns[:2]:
                action = self._intent_to_action(p["intent"])
                if action:
                    predictions.append({
                        "action":     action["action"],
                        "tool":       action["tool"],
                        "params":     action["params"],
                        "reason":     f"When feeling {state.pavan_mood}, you usually {action['reason']}",
                        "confidence": 0.60,
                        "type":       "mood_based",
                    })

        # ── Proactive reminders ──────────────────────────────
        if state.pending_reminders > 0:
            predictions.append({
                "action":     "announce_reminders",
                "tool":       "speak",
                "params":     {"text": f"You have {state.pending_reminders} upcoming reminders."},
                "reason":     "You have pending reminders",
                "confidence": 0.85,
                "type":       "alert",
            })

        # ── Unread messages ──────────────────────────────────
        if state.unread_messages >= 5 and state.hour in range(8, 22):
            predictions.append({
                "action":     "notify_messages",
                "tool":       "speak",
                "params":     {"text": f"You have {state.unread_messages} unread messages. Want me to read them?"},
                "reason":     "Unread messages accumulating",
                "confidence": 0.70,
                "type":       "alert",
            })

        # ── Morning briefing (8-9am weekdays) ───────────────
        if state.hour == 8 and not state.is_weekend:
            predictions.append({
                "action":     "morning_briefing",
                "tool":       "daily_briefing",
                "params":     {},
                "reason":     "Morning briefing time",
                "confidence": 0.80,
                "type":       "scheduled",
            })

        # ── Evening wind-down (9-10pm) ───────────────────────
        if state.hour in (21, 22):
            predictions.append({
                "action":     "evening_summary",
                "tool":       "daily_summary",
                "params":     {},
                "reason":     "End of day — daily summary time",
                "confidence": 0.72,
                "type":       "scheduled",
            })

        # Filter by cooldown + sort by confidence
        filtered = []
        for p in predictions:
            key = p["action"]
            last = self._prediction_cooldowns.get(key, 0)
            if now - last > self.COOLDOWN_SEC:
                filtered.append(p)
                self._prediction_cooldowns[key] = now

        self._last_predictions = sorted(filtered, key=lambda x: -x["confidence"])
        return self._last_predictions[:3]   # max 3 predictions per loop

    def _intent_to_action(self, intent: str) -> dict:
        """Map intent name to a concrete action."""
        MAPPING = {
            "greeting":      {"action": "greet",        "tool": "speak",     "params": {}, "reason": "greet"},
            "reminder":      {"action": "check_reminders","tool":"list_reminders","params":{},"reason":"check reminders"},
            "music":         {"action": "play_music",   "tool": "media",     "params": {"mode":"random"}, "reason": "play music"},
            "planning":      {"action": "show_tasks",   "tool": "task_list", "params": {}, "reason": "review tasks"},
            "code":          {"action": "focus_mode",   "tool": "speak",     "params": {"text":"Entering focus mode. Notifications paused."}, "reason": "code"},
            "small_talk":    {"action": "casual_chat",  "tool": "brain",     "params": {}, "reason": "chat"},
            "notes":         {"action": "show_notes",   "tool": "notes",     "params": {}, "reason": "check notes"},
        }
        return MAPPING.get(intent)

    def get_last_predictions(self) -> list:
        return self._last_predictions


# ──────────────────────────────────────────────────────────────
