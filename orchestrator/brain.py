# orchestrator/brain.py  — UPDATED FOR RTX 4050 6GB
# Replace your existing jarvis_brain/orchestrator/brain.py
#
# KEY CHANGES:
#  Multi-model routing with automatic switching by task:
#    - llama3.1:8b → primary chat
#    - qwen2.5:7b → analysis/decisions
#    - qwen2.5-coder:3b → coding
#    - deepseek-r1:1.5b → reasoning/planning
#    - qwen3:4b → automation
#    - moondream → vision
#    - tinyllama / phi3 → fast classifiers & quality checks

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional

from gpu.pool import ModelPool
from jarvis_os.memory.memory_manager import MemoryManager
from core.model_router import model_for_role, route_role_for_text
from dataclasses import dataclass, field
from typing import Any


@dataclass
class BrainResult:
    reply: str
    model_used: str
    intent: str
    emotion: str
    confidence: float
    latency_ms: int
    cached: bool = False


@dataclass
class Message:
    text: str
    platform: str = "chat"
    user_id: str = "dev"
    image_b64: str = ""


@dataclass
class MemoryConfig:
    short_term_limit: int = 100
    data_dir: str = "data/memory"


class JarvisBrain:

    def __init__(self):
        print("[Brain] Initializing JARVIS Multi-Agent Brain (RTX 4050 optimized)...")
        self.pool           = ModelPool()
        self.memory         = MemoryManager(MemoryConfig())
        self.ctx_builder    = ContextBuilder(self.memory)
        self.fact_extractor = FactExtractor(self.pool, self.memory)
        self._reply_cache: dict = {}
        print("[Brain] All agents ready")

    async def startup(self):
        await self.pool.warmup()
        print("[Brain] Ready ✓")

    # ── Main entry point ──────────────────────────────────────

    async def think(self, msg: Message) -> BrainResult:
        t_start = time.time()
        print(f"\n[Brain] Input: '{msg.text[:60]}' platform={msg.platform}")

        # 1. Cache check
        cache_key = f"{msg.user_id}:{msg.text[:50]}"
        if cache_key in self._reply_cache:
            cached = self._reply_cache[cache_key]
            return BrainResult(
                reply=cached["reply"], model_used=cached["model"],
                intent="cached", emotion="neutral",
                confidence=1.0, latency_ms=0, cached=True,
            )

        # 2. Detect intent (fast — tinyllama)
        intent = await self._classify(msg.text)
        print(f"[Brain] Intent: {intent}")

        # 3. Detect emotion (fast — tinyllama)
        emotion = await self._detect_emotion(msg.text)
        print(f"[Brain] Emotion: {emotion}")

        # 4. Pick best model for this intent
        model = self._route(intent, msg)
        print(f"[Brain] Routing to: {model}")

        # 5. Build context from memory
        context = await self.ctx_builder.build(msg.user_id, msg.text, intent, emotion)

        # 6. Build system prompt
        system = SYSTEMS.get(model, SYSTEMS[ROUTE["chat"]])
        if emotion in EMOTION_PREFIXES and model in {ROUTE["chat"], ROUTE["analysis"], ROUTE["creative"]}:
            system = EMOTION_PREFIXES[emotion] + system

        # 7. Build full prompt
        prompt = self._build_prompt(msg.text, context)

        # 8. Generate response
        if msg.image_b64 and model == "moondream":
            reply = await self.pool.generate(
                model, prompt, system, images=[msg.image_b64])
        else:
            reply = await self.pool.generate(model, prompt, system)

        # 9. Quality check
        confidence = await self._quality_check(msg.text, reply)

        # 10. Retry with primary if quality too low
        retried = False
        if confidence < 0.5 and model != ROUTE["chat"]:
            print(f"[Brain] Quality {confidence:.2f} too low — retrying with {ROUTE['chat']}")
            reply      = await self.pool.generate(
                ROUTE["chat"], prompt, SYSTEMS[ROUTE["chat"]])
            model      = ROUTE["chat"]
            confidence = 0.75
            retried    = True

        # 11. Save to memory (background)
        asyncio.create_task(
            self.memory.save(msg.user_id, msg.text, reply))
        asyncio.create_task(
            self.fact_extractor.extract_and_save(msg.user_id, msg.text))

        # 12. Cache result
        self._reply_cache[cache_key] = {"reply": reply, "model": model}
        if len(self._reply_cache) > 200:
            oldest = next(iter(self._reply_cache))
            del self._reply_cache[oldest]

        latency = int((time.time() - t_start) * 1000)
        print(f"[Brain] Done in {latency}ms using {model} "
              f"(confidence={confidence:.2f})")

        return BrainResult(
            reply=reply, model_used=model,
            intent=intent, emotion=emotion,
            confidence=confidence, latency_ms=latency,
            retried=retried,
        )

    # ── Routing logic ─────────────────────────────────────────

    def _route(self, intent: str, msg: Message) -> str:
        # Vision task
        if msg.image_b64:
            return ROUTE["vision"]

        # Route by intent
        intent_map = {
            "code":        ROUTE["code"],
            "debug":       ROUTE["code"],
            "script":      ROUTE["code"],
            "automate":    ROUTE["automation"],
            "schedule":    ROUTE["reasoning"],
            "plan":        ROUTE["reasoning"],
            "steps":       ROUTE["reasoning"],
            "adb":         ROUTE["automation"],
            "whatsapp":    ROUTE["automation"],
            "reminder":    ROUTE["reasoning"],
            "analyze":     ROUTE["analysis"],
            "analysis":    ROUTE["analysis"],
            "creative":    ROUTE["creative"],
            "write":       ROUTE["creative"],
        }

        intent_lower = (intent or "").lower()
        for key, model in intent_map.items():
            if key in intent_lower:
                return model

        # Fallback to heuristic router
        role = route_role_for_text(msg.text)
        return ROUTE.get(role, ROUTE["chat"])   # default to primary brain

    # ── Sub-agents (fast, all use tinyllama) ──────────────────

    async def _classify(self, text: str) -> str:
        prompt = (f"Classify this message into ONE word — intent only.\n"
                  f"Options: chat, code, debug, automate, schedule, plan, "
                  f"reminder, vision, adb, whatsapp, analyze, question\n"
                  f"Message: {text[:200]}\nIntent:")
        result = await self.pool.generate(
            ROUTE["classifier"], prompt, temperature=0.1, max_tokens=5)
        return result.strip().lower().split()[0] if result.strip() else "chat"

    async def _detect_emotion(self, text: str) -> str:
        prompt = (f"Detect emotion in ONE word.\n"
                  f"Options: neutral, happy, sad, angry, excited, anxious, frustrated\n"
                  f"Text: {text[:200]}\nEmotion:")
        result = await self.pool.generate(
            ROUTE["emotion"], prompt, temperature=0.1, max_tokens=5)
        return result.strip().lower().split()[0] if result.strip() else "neutral"

    async def _quality_check(self, question: str, answer: str) -> float:
        prompt = (f"Rate this answer quality 0-10. Reply with number only.\n"
                  f"Q: {question[:100]}\nA: {answer[:200]}\nScore:")
        result = await self.pool.generate(
            ROUTE["quality"], prompt, temperature=0.1, max_tokens=3)
        try:
            score = float(result.strip().split()[0])
            return min(1.0, score / 10.0)
        except Exception:
            return 0.7

    def _build_prompt(self, text: str, context: str) -> str:
        if context:
            return f"[Context]\n{context}\n\n[User]\n{text}"
        return text


# ──────────────────────────────────────────────────────────────
#  SINGLETON BRAIN INSTANCE
# ──────────────────────────────────────────────────────────────

_brain_instance = None

def get_brain() -> JarvisBrain:
    """Get or create the singleton JARVIS brain instance."""
    global _brain_instance
    if _brain_instance is None:
        _brain_instance = JarvisBrain()
    return _brain_instance
