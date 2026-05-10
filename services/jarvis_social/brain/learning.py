"""
brain/learning.py — Shadow Learning Engine
==========================================
Observes manual chats and suggests trait adjustments.
Does NOT auto-modify without explicit enable flag.
Max shift: 0.05 per session.
"""
from __future__ import annotations
import logging, time, re
from db.schema import connect, clamp, DB_PATH
from friends.registry import FriendRegistry

logger = logging.getLogger(__name__)

MAX_SHIFT_PER_SESSION = 0.05
LEARNING_RATE         = 0.05   # new = old*0.95 + observed*0.05


class ShadowLearner:
    """
    Extracts tone features from manually-typed messages and
    produces trait update SUGGESTIONS (does not apply automatically).
    """

    def __init__(self, db_path: str = DB_PATH):
        self._db  = db_path
        self._reg = FriendRegistry(db_path)
        self._session_shifts: dict[str, dict[str, float]] = {}

    def observe_manual_message(self, friend_id: str,
                                 message: str) -> dict[str, float]:
        """
        Called when user manually types a message.
        Returns suggested trait adjustments (not applied yet).
        """
        observed = self._extract_tone(message)
        current  = self._reg.get_traits(friend_id)
        if not current:
            return {}

        suggestions = {}
        session = self._session_shifts.setdefault(friend_id, {})

        for trait, obs_val in observed.items():
            if trait not in current:
                continue
            old_val = float(current[trait])
            new_val = clamp(old_val * (1 - LEARNING_RATE) + obs_val * LEARNING_RATE)
            shift   = abs(new_val - old_val)

            # Cap total shift this session
            session_total = session.get(trait, 0.0) + shift
            if session_total > MAX_SHIFT_PER_SESSION:
                allowed = max(0.0, MAX_SHIFT_PER_SESSION - session.get(trait, 0.0))
                new_val = clamp(old_val + (new_val - old_val) * allowed / shift if shift > 0 else old_val)
                shift   = abs(new_val - old_val)

            session[trait] = session.get(trait, 0.0) + shift
            suggestions[trait] = round(new_val, 4)

        logger.debug("[ShadowLearner] Observed %s for %s", observed, friend_id)
        return suggestions

    def apply_suggestions(self, friend_id: str,
                           suggestions: dict[str, float]) -> None:
        """Apply trait suggestions to DB. Call only if explicitly enabled."""
        for trait, val in suggestions.items():
            try:
                self._reg.update_trait(friend_id, trait, val)
            except ValueError as e:
                logger.warning("[ShadowLearner] Blocked: %s", e)

    def reset_session(self, friend_id: str) -> None:
        self._session_shifts.pop(friend_id, None)

    def _extract_tone(self, message: str) -> dict[str, float]:
        """Extract tone features from message text."""
        text = message.strip()
        length = len(text)

        # Emoji density
        emoji_count = sum(1 for c in text if ord(c) > 127)
        emoji_val   = min(1.0, emoji_count / max(length, 1) * 15)

        # Humor signals
        humor_signals = ["haha","lol","lmao","😂","🤣","funny","joke","jk","kidding"]
        humor_val = min(1.0, sum(1 for s in humor_signals if s in text.lower()) * 0.25)

        # Energy: exclamation density + caps
        excl   = text.count("!") / max(length/10, 1)
        caps   = sum(1 for c in text if c.isupper()) / max(length, 1)
        energy = clamp(excl * 0.5 + caps * 2.0)

        # Formality: formal words lower formality
        informal = ["ya","yep","nah","dunno","gonna","wanna","btw","rn","tbh","imo"]
        informal_count = sum(1 for w in informal if w in text.lower().split())
        formality = clamp(0.5 - informal_count * 0.1)

        # Directness: short sentences = more direct
        words = len(text.split())
        directness = clamp(1.0 - min(words / 50.0, 1.0) * 0.5 + 0.5)

        # Caring: caring words
        caring_words = ["how are you","miss","hope","take care","❤","love","care"]
        caring = min(1.0, sum(1 for w in caring_words if w in text.lower()) * 0.3)
        caring = clamp(0.4 + caring)

        return {
            "humor":     round(humor_val, 3),
            "emoji":     round(emoji_val, 3),
            "energy":    round(energy, 3),
            "formality": round(formality, 3),
            "directness":round(directness, 3),
            "caring":    round(caring, 3),
        }
