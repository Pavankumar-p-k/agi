from __future__ import annotations

import asyncio
import time
from typing import Optional

from brain.agents import ClassifierAgent, EmotionAgent, GeneratorAgent, QualityAgent
from brain.memory import ContextBuilder, FactExtractor, MemoryStore
from brain.pool import ModelPool
from brain.types import BrainResult, Message


class JarvisBrain:
    def __init__(self) -> None:
        self.pool = ModelPool()
        self.memory = MemoryStore()
        self.context_builder = ContextBuilder(self.memory)
        self.classifier = ClassifierAgent(self.pool)
        self.emotion_agent = EmotionAgent(self.pool)
        self.generator = GeneratorAgent(self.pool)
        self.quality_agent = QualityAgent(self.pool)
        self.fact_extractor = FactExtractor(self.pool, self.memory)
        self._reply_cache: dict[str, dict[str, object]] = {}

    async def startup(self) -> None:
        await self.pool.warmup()

    async def think(self, msg: Message) -> BrainResult:
        start = time.time()
        cache_key = f"{msg.user_id}:{msg.text.strip().lower()}"
        cached = self._reply_cache.get(cache_key)
        if cached:
            return BrainResult(
                reply=str(cached["reply"]),
                model_used=str(cached["model"]),
                intent=str(cached["intent"]),
                emotion=str(cached["emotion"]),
                confidence=float(cached["confidence"]),
                latency_ms=int((time.time() - start) * 1000),
                cached=True,
            )

        classification, emotion = await asyncio.gather(
            self.classifier.classify(msg),
            self.emotion_agent.detect(msg.text),
        )
        intent = str(classification.get("intent", "small_talk"))
        urgency = str(classification.get("urgency", "low"))
        message_type = str(classification.get("message_type", "casual"))

        context = await self.context_builder.build(msg.user_id, msg.text, intent, emotion)
        model = self._route(msg, intent, emotion, urgency, message_type)
        reply = await self.generator.generate(msg, context=context, model=model, intent=intent, emotion=emotion)

        score = await self.quality_agent.score(msg.text, reply, intent)
        retried = False
        if score < 0.55 and model != "llama3:8b":
            reply = await self.generator.generate(
                msg,
                context=context,
                model="llama3:8b",
                intent=intent,
                emotion=emotion,
                retry=True,
            )
            model = "llama3:8b"
            score = await self.quality_agent.score(msg.text, reply, intent)
            retried = True

        asyncio.create_task(self.fact_extractor.extract_and_save(msg.user_id, msg.text))
        await asyncio.gather(
            self.memory.save(
                msg.user_id,
                "user",
                msg.text,
                metadata={"intent": intent, "emotion": emotion, "platform": msg.platform},
                session=msg.session,
            ),
            self.memory.save(
                msg.user_id,
                "assistant",
                reply,
                metadata={"intent": intent, "emotion": emotion, "model": model, "quality": score},
                session=msg.session,
            ),
        )

        if score > 0.7:
            self._reply_cache[cache_key] = {
                "reply": reply,
                "model": model,
                "intent": intent,
                "emotion": emotion,
                "confidence": score,
            }
            if len(self._reply_cache) > 100:
                oldest = next(iter(self._reply_cache))
                del self._reply_cache[oldest]

        return BrainResult(
            reply=reply,
            model_used=model,
            intent=intent,
            emotion=emotion,
            confidence=score,
            latency_ms=int((time.time() - start) * 1000),
            retried=retried,
        )

    def _route(self, msg: Message, intent: str, emotion: str, urgency: str, message_type: str) -> str:
        if msg.image_b64:
            return "llava:latest"
        if emotion in {"sad", "angry", "anxious", "depressed", "frustrated"}:
            return "llama3:8b"
        if urgency == "high":
            return "llama3:8b"
        if intent in {"emotional_support", "advice", "philosophy", "debate", "planning", "analysis"}:
            return "llama3:8b"
        if intent in {"code", "structured", "decision", "classification"}:
            return "qwen2:7b"
        if intent in {"greeting", "small_talk", "acknowledgment"}:
            return "phi3:mini"
        if len(msg.text.split()) < 8:
            return "phi3:mini"
        return "mistral:7b"

    async def get_memory_stats(self, user_id: str) -> dict:
        stats = await self.memory.get_stats(user_id)
        trend = await self.memory.get_emotion_trend(user_id, hours=24)
        facts = await self.memory.get_user_facts(user_id)
        return {
            **stats,
            "emotion_trend_24h": trend,
            "known_facts_count": len(facts),
            "known_facts": facts[:10],
            "pool": self.pool.get_stats(),
            "vram": self.pool.vram_status(),
        }

    async def clear_memory(self, user_id: str) -> None:
        await self.memory.clear_user_memory(user_id)
        self._reply_cache.clear()

    async def shutdown(self) -> None:
        await self.pool.unload_all()


_brain: Optional[JarvisBrain] = None


def get_brain() -> JarvisBrain:
    global _brain
    if _brain is None:
        _brain = JarvisBrain()
    return _brain
