from __future__ import annotations

import json
import re

from brain.memory.store import MemoryEntry, MemoryStore
from brain.pool import ModelPool

MAX_CONTEXT_CHARS = 3000
FACT_SYSTEM = """Extract personal facts from this message.
Return ONLY a JSON array of strings. Max 3. If none, return [].
Examples:
"I work as a software engineer in Hyderabad" -> ["User works as a software engineer", "User lives in Hyderabad"]
"Hello" -> []
"""


class ContextBuilder:
    def __init__(self, memory: MemoryStore) -> None:
        self.memory = memory

    async def build(self, user_id: str, current_text: str, intent: str, emotion: str) -> str:
        sections: list[str] = []
        seen_ids: set[int] = set()

        facts = await self.memory.get_user_facts(user_id)
        if facts:
            bullet = "\n".join(f"- {f}" for f in facts[:8])
            sections.append(f"[User Profile]\n{bullet}")

        trend = await self.memory.get_emotion_trend(user_id, hours=6)
        if trend:
            dominant = max(trend, key=trend.get)
            if dominant != "neutral":
                sections.append(f"[Mood Today]\nMostly {dominant}")

        relevant: list[MemoryEntry] = []
        intent_msgs = await self.memory.search_by_intent(user_id, intent, limit=2)
        relevant.extend(intent_msgs)
        seen_ids.update(m.id for m in intent_msgs)

        if emotion != "neutral":
            for msg in await self.memory.search_by_emotion(user_id, emotion, limit=2):
                if msg.id not in seen_ids:
                    relevant.append(msg)
                    seen_ids.add(msg.id)

        for kw in self._extract_keywords(current_text)[:3]:
            for msg in await self.memory.search_by_keyword(user_id, kw, limit=2):
                if msg.id not in seen_ids:
                    relevant.append(msg)
                    seen_ids.add(msg.id)

        if relevant:
            relevant_sorted = sorted(relevant, key=lambda x: x.timestamp)[-6:]
            sections.append("[Relevant Past]\n" + self._format(relevant_sorted))

        recent = await self.memory.get_recent(user_id, n=8)
        recent = [m for m in recent if m.id not in seen_ids]
        if recent:
            sections.append("[Recent Conversation]\n" + self._format(recent))

        context = "\n\n".join(sections)
        if len(context) > MAX_CONTEXT_CHARS:
            context = context[-MAX_CONTEXT_CHARS:]
            first_nl = context.find("\n")
            if first_nl > 0:
                context = context[first_nl + 1 :]
        return context

    def _format(self, messages: list[MemoryEntry]) -> str:
        rows: list[str] = []
        for msg in messages:
            role = "User" if msg.role == "user" else "JARVIS"
            body = msg.content if len(msg.content) <= 220 else (msg.content[:220] + "...")
            rows.append(f"{role}: {body}")
        return "\n".join(rows)

    def _extract_keywords(self, text: str) -> list[str]:
        stop = {
            "i",
            "the",
            "a",
            "an",
            "is",
            "are",
            "to",
            "of",
            "and",
            "or",
            "in",
            "on",
            "at",
            "for",
            "with",
            "this",
            "that",
            "what",
            "when",
            "where",
            "why",
            "how",
            "you",
            "me",
            "we",
            "they",
        }
        keywords = [w.strip(".,!?()[]{}:;\"'").lower() for w in text.split()]
        return [w for w in keywords if len(w) > 3 and w and w not in stop]


class FactExtractor:
    def __init__(self, pool: ModelPool, memory: MemoryStore) -> None:
        self.pool = pool
        self.memory = memory

    async def extract_and_save(self, user_id: str, user_message: str) -> None:
        if len(user_message.split()) < 5:
            return
        raw = await self.pool.generate(
            model="phi3:mini",
            prompt=f'Extract facts from: "{user_message}"',
            system=FACT_SYSTEM,
            temperature=0.1,
            max_tokens=120,
        )
        if not raw:
            return
        try:
            match = re.search(r"\[.*\]", raw, flags=re.DOTALL)
            if not match:
                return
            facts = json.loads(match.group(0))
            if not isinstance(facts, list):
                return
            for fact in facts:
                if isinstance(fact, str) and len(fact.strip()) > 5:
                    await self.memory.save_fact(user_id, fact.strip())
        except Exception:
            return
