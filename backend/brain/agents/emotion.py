from __future__ import annotations

from brain.pool import ModelPool

SYSTEM = """Reply with one word only from:
sad, happy, angry, anxious, excited, neutral, love, frustrated, confused, depressed"""
VALID = {"sad", "happy", "angry", "anxious", "excited", "neutral", "love", "frustrated", "confused", "depressed"}


class EmotionAgent:
    def __init__(self, pool: ModelPool) -> None:
        self.pool = pool

    async def detect(self, text: str) -> str:
        raw = await self.pool.generate(
            model="qwen2:7b",
            prompt=f'Emotion in: "{text}"',
            system=SYSTEM,
            temperature=0.05,
            max_tokens=5,
        )
        if not raw:
            return "neutral"
        token = raw.strip().lower().split()[0]
        return token if token in VALID else "neutral"
