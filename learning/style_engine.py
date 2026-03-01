from __future__ import annotations

import re
from collections import Counter
from typing import Any


_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002700-\U000027BF\U00002600-\U000026FF]+",
    flags=re.UNICODE,
)


class MessageStyleEngine:
    """
    Lightweight style imitation from user's own chat samples.
    """

    def __init__(self, memory):
        self.memory = memory
        self._messages: list[str] = []
        self._loaded = False

    async def _ensure_loaded(self, user_id: str = "pavan") -> None:
        if self._loaded:
            return
        self._messages = await self.memory.get_user_messages(user_id=user_id, limit=300)
        self._loaded = True

    async def observe(self, event: dict[str, Any]) -> None:
        if event.get("type") != "user_input":
            return
        text = str(event.get("content", "")).strip()
        if not text:
            return
        self._messages.insert(0, text)
        if len(self._messages) > 300:
            self._messages = self._messages[:300]
        self._loaded = True

    def _profile(self) -> dict[str, Any]:
        msgs = self._messages[:300]
        if not msgs:
            return {
                "samples": 0,
                "avg_words": 10,
                "lowercase_ratio": 0.5,
                "question_ratio": 0.2,
                "exclaim_ratio": 0.05,
                "top_emoji": "",
                "top_end_token": "",
            }

        total = len(msgs)
        word_counts = [max(1, len(m.split())) for m in msgs]
        avg_words = sum(word_counts) / total

        lowercase_hits = 0
        question_hits = 0
        exclaim_hits = 0
        endings = Counter()
        emojis = Counter()

        for m in msgs:
            stripped = m.strip()
            if stripped and stripped == stripped.lower():
                lowercase_hits += 1
            if "?" in stripped:
                question_hits += 1
            if "!" in stripped:
                exclaim_hits += 1

            tail = stripped.split()[-1].lower() if stripped.split() else ""
            if tail:
                endings[tail] += 1

            for e in _EMOJI_RE.findall(stripped):
                emojis[e] += 1

        return {
            "samples": total,
            "avg_words": round(avg_words, 2),
            "lowercase_ratio": round(lowercase_hits / total, 3),
            "question_ratio": round(question_hits / total, 3),
            "exclaim_ratio": round(exclaim_hits / total, 3),
            "top_emoji": emojis.most_common(1)[0][0] if emojis else "",
            "top_end_token": endings.most_common(1)[0][0] if endings else "",
        }

    def _base_reply(self, incoming_text: str, intent: str) -> str:
        t = incoming_text.strip()
        i = (intent or "").strip().lower()
        if i == "reminder":
            return "ok i will set this and remind you at the right time"
        if i == "code":
            return "noted. i will handle this in steps and send update"
        if i == "planning":
            return "done. i can break this into a simple plan right now"
        if i == "greeting":
            return "yes sir i am here. tell me what to do"
        if "call" in t.lower():
            return "call alert received. do you want me to lift or send busy note"
        return "noted. i understood. i will take care of it"

    def _apply_style(self, text: str, profile: dict[str, Any]) -> str:
        out = text.strip()
        if not out:
            return out

        if profile["lowercase_ratio"] >= 0.65:
            out = out.lower()

        # Length adaptation.
        avg_words = float(profile["avg_words"])
        words = out.split()
        if avg_words <= 8 and len(words) > 10:
            out = " ".join(words[:9])
        elif avg_words >= 16 and len(words) < 10:
            out = out + " and i can also give you the full breakdown if you want."

        # Punctuation adaptation.
        if profile["question_ratio"] >= 0.35 and "?" not in out:
            out = out.rstrip(".!") + "?"
        elif profile["exclaim_ratio"] >= 0.2 and "!" not in out and "?" not in out:
            out = out.rstrip(".") + "!"

        # Add common ending style token if useful.
        end_tok = str(profile.get("top_end_token") or "")
        if end_tok in {"sir", "bro", "ok", "okay"} and end_tok not in out.lower().split():
            out = f"{out} {end_tok}"

        emoji = str(profile.get("top_emoji") or "")
        if emoji and emoji not in out:
            out = f"{out} {emoji}"

        return out.strip()

    async def generate_reply(self, incoming_text: str, intent: str = "small_talk", user_id: str = "pavan") -> dict[str, Any]:
        await self._ensure_loaded(user_id=user_id)
        p = self._profile()
        base = self._base_reply(incoming_text, intent)
        styled = self._apply_style(base, p)
        return {
            "reply": styled,
            "style_profile": p,
        }

    async def get_profile(self, user_id: str = "pavan") -> dict[str, Any]:
        await self._ensure_loaded(user_id=user_id)
        return self._profile()
