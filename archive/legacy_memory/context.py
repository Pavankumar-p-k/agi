# memory/context.py
#
# CONTEXT BUILDER — Smart Context Window Optimizer
# ─────────────────────────────────────────────────────────────
#
#  The problem: LLMs have limited context windows.
#  Naively sending full chat history = slow + expensive + degraded quality.
#
#  Our solution — 3-layer context injection:
#
#   Layer 1: ALWAYS INCLUDE
#     • Last 6 messages (recency = most important)
#
#   Layer 2: SMART RETRIEVE
#     • Past messages matching current intent (up to 3)
#     • Past messages matching current emotion (up to 2)
#     • Keyword overlap with current message (up to 3)
#
#   Layer 3: USER PROFILE
#     • Known facts about user
#     • Current emotion trend
#
#  Total context budget: ~1500 tokens
#  (leaves plenty of room for reply generation)

from memory.store import MemoryStore, MemoryEntry
from typing import List
import time


MAX_CONTEXT_CHARS = 3000   # ~750 tokens — fast and effective


class ContextBuilder:
    def __init__(self, memory: MemoryStore):
        self.memory = memory

    async def build(
        self,
        user_id: str,
        current_text: str,
        intent:  str,
        emotion: str,
    ) -> str:
        """
        Build optimized context string to prepend to the prompt.
        Returns a string like:
          [User Profile]
          - Pavan likes Python and Flutter
          - Pavan works on JARVIS project

          [Relevant Past]
          User: I'm working on my AI project
          JARVIS: That sounds amazing...

          [Recent]
          User: hey
          JARVIS: Hello Pavan! ...
        """
        sections = []

        # ── Layer 3: User Profile ──────────────────────────────
        facts  = await self.memory.get_user_facts(user_id)
        trends = await self.memory.get_emotion_trend(user_id, hours=6)

        if facts:
            facts_str = "\n".join(f"• {f}" for f in facts[:8])
            sections.append(f"[User Profile]\n{facts_str}")

        if trends:
            top_emotion = max(trends, key=trends.get)
            if top_emotion != "neutral":
                sections.append(f"[Mood Today] User has been feeling mostly {top_emotion}")

        # ── Layer 2: Smart Retrieval ───────────────────────────
        relevant = []

        # a) Same intent messages
        intent_msgs = await self.memory.search_by_intent(user_id, intent, limit=2)
        relevant.extend(intent_msgs)

        # b) Same emotion messages (if emotional)
        if emotion not in ("neutral",):
            emotion_msgs = await self.memory.search_by_emotion(user_id, emotion, limit=2)
            relevant.extend(emotion_msgs)

        # c) Keyword overlap
        keywords = self._extract_keywords(current_text)
        seen_ids = {m.id for m in relevant}
        for kw in keywords[:3]:
            kw_msgs = await self.memory.search_by_keyword(user_id, kw, limit=2)
            for m in kw_msgs:
                if m.id not in seen_ids:
                    relevant.append(m)
                    seen_ids.add(m.id)

        # Deduplicate + sort by timestamp
        relevant = sorted(
            {m.id: m for m in relevant}.values(),
            key=lambda m: m.timestamp
        )[-6:]   # max 6 relevant messages

        if relevant:
            rel_str = self._format_messages(relevant)
            sections.append(f"[Relevant Past]\n{rel_str}")

        # ── Layer 1: Recent Messages ───────────────────────────
        recent = await self.memory.get_recent(user_id, n=8)

        # Remove any already in relevant to avoid duplication
        recent = [m for m in recent if m.id not in seen_ids]

        if recent:
            recent_str = self._format_messages(recent)
            sections.append(f"[Recent Conversation]\n{recent_str}")

        # ── Assemble + Truncate ────────────────────────────────
        context = "\n\n".join(sections)

        if len(context) > MAX_CONTEXT_CHARS:
            context = context[-MAX_CONTEXT_CHARS:]
            # Find first newline to avoid cutting mid-sentence
            nl = context.find("\n")
            if nl > 0:
                context = context[nl:]

        return context

    def _format_messages(self, messages: List[MemoryEntry]) -> str:
        lines = []
        for m in messages:
            role = "User" if m.role == "user" else "JARVIS"
            # Truncate very long messages
            content = m.content[:200] + "..." if len(m.content) > 200 else m.content
            lines.append(f"{role}: {content}")
        return "\n".join(lines)

    def _extract_keywords(self, text: str) -> List[str]:
        """Simple keyword extraction — remove stop words, return important terms."""
        stop = {"i","the","a","an","is","are","was","were","be","been","to","of",
                "and","or","in","on","at","for","with","by","from","do","did",
                "have","has","had","will","would","could","should","can","that",
                "this","it","he","she","they","we","you","me","him","her","them",
                "what","how","why","when","where","which","who","whom"}
        words = text.lower().split()
        keywords = [w.strip(".,!?") for w in words
                    if len(w) > 3 and w.lower() not in stop]
        return keywords[:5]


# ─────────────────────────────────────────────────────────────
# memory/fact_extractor.py
#
# Runs after each conversation turn to extract user facts
# e.g. "I love coding in Python" → saves "Pavan loves coding in Python"
# Uses phi3 (fast, cheap) for extraction

FACT_SYSTEM = """You are a fact extractor. Read the user message and extract any personal facts.
Return ONLY a JSON array of fact strings. Max 3 facts.
If no clear personal facts, return empty array: []

Examples:
Input: "I work as a software engineer in Hyderabad"
Output: ["Pavan works as a software engineer", "Pavan lives in Hyderabad"]

Input: "hey how are you"
Output: []"""

import json
import re
from gpu.pool import ModelPool
from core.model_router import model_for_role

class FactExtractor:
    def __init__(self, pool: ModelPool, memory: MemoryStore):
        self.pool   = pool
        self.memory = memory

    async def extract_and_save(self, user_id: str, user_message: str):
        """Extract facts from message and save to memory."""
        # Only process substantial messages
        if len(user_message.split()) < 5:
            return

        raw = await self.pool.generate(
            model=model_for_role("quality"),
            prompt=f'Extract facts from: "{user_message}"',
            system=FACT_SYSTEM,
            temperature=0.1,
            max_tokens=100,
        )
        try:
            m = re.search(r'\[.*?\]', raw, re.DOTALL)
            if m:
                facts = json.loads(m.group())
                for fact in facts:
                    if isinstance(fact, str) and len(fact) > 5:
                        await self.memory.save_fact(user_id, fact)
        except Exception:
            pass
