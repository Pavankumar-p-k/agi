from __future__ import annotations

import json
import re
from typing import Any

from brain.pool import ModelPool
from brain.types import Message

SYSTEM = """You are a message classifier. Return ONLY JSON with:
{
  "intent": one of [greeting, small_talk, question, emotional_support, planning, advice, code, analysis, reminder, complaint, request, debate, philosophy, acknowledgment, simple_question, structured, decision, classification],
  "topic": short string,
  "urgency": one of [low, medium, high],
  "message_type": one of [casual, normal, deep, technical, emotional],
  "requires_memory": true or false
}"""

FALLBACK: dict[str, Any] = {
    "intent": "small_talk",
    "topic": "general",
    "urgency": "low",
    "message_type": "casual",
    "requires_memory": False,
}


class ClassifierAgent:
    def __init__(self, pool: ModelPool) -> None:
        self.pool = pool

    async def classify(self, msg: Message) -> dict[str, Any]:
        raw = await self.pool.generate(
            model="qwen2:7b",
            prompt=f'Classify this: "{msg.text}"',
            system=SYSTEM,
            temperature=0.1,
            max_tokens=120,
        )
        if not raw:
            return FALLBACK
        try:
            match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
            if not match:
                return FALLBACK
            data = json.loads(match.group(0))
            merged = dict(FALLBACK)
            merged.update({k: v for k, v in data.items() if k in merged})
            return merged
        except Exception:
            return FALLBACK
