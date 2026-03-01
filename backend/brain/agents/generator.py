from __future__ import annotations

from brain.pool import ModelPool
from brain.types import Message

SYSTEMS = {
    "phi3:mini": "You are JARVIS. Reply briefly and clearly in 1-3 sentences.",
    "mistral:7b": "You are JARVIS. Be accurate and helpful. Keep it concise.",
    "llama3:8b": "You are JARVIS. Be empathetic, thoughtful, and practical.",
    "qwen2:7b": "You are JARVIS. Be structured and precise.",
    "llava:latest": "You are JARVIS with image understanding. Analyze carefully.",
}

EMOTION_HINTS = {
    "sad": "User sounds sad; use warm and supportive language.",
    "angry": "User sounds frustrated; stay calm and constructive.",
    "anxious": "User sounds anxious; reassure and simplify.",
    "depressed": "User sounds low; keep tone gentle and encouraging.",
    "excited": "User is excited; match energy and stay focused.",
    "frustrated": "User is frustrated; acknowledge and propose concrete steps.",
}


class GeneratorAgent:
    def __init__(self, pool: ModelPool) -> None:
        self.pool = pool

    async def generate(
        self,
        message: Message,
        context: str,
        model: str,
        intent: str,
        emotion: str,
        retry: bool = False,
    ) -> str:
        system = SYSTEMS.get(model, SYSTEMS["mistral:7b"])
        if emotion in EMOTION_HINTS:
            system = f"{system}\n{EMOTION_HINTS[emotion]}"
        if retry:
            system = f"{system}\nImprove quality versus previous attempt."

        prompt = f"{context}\n\nUser: {message.text}\nJARVIS:" if context else f"User: {message.text}\nJARVIS:"
        max_tokens = {"phi3:mini": 150, "mistral:7b": 350, "llama3:8b": 500, "qwen2:7b": 400}.get(model, 350)
        temp = 0.3 if intent in {"code", "structured", "decision", "classification"} else 0.75
        if retry:
            temp = min(temp + 0.15, 0.95)

        out = await self.pool.generate(
            model=model,
            prompt=prompt,
            system=system,
            temperature=temp,
            max_tokens=max_tokens,
        )
        return out.strip() if out else "I am here. Tell me a bit more."
