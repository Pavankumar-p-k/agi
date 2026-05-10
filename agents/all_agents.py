# agents/classifier.py
#
# CLASSIFIER AGENT — uses tinyllama (fast)
# Detects: intent, topic, urgency, message_type
# Returns structured JSON (qwen2 is best at this)

import json
import re
from gpu.pool import ModelPool
from core.model_router import model_for_role

SYSTEM = """You are a message classifier. Analyze the user message and return ONLY a JSON object.

JSON format:
{
  "intent": one of [greeting, small_talk, question, emotional_support, planning, advice,
                    code, analysis, reminder, complaint, request, debate, philosophy,
                    acknowledgment, simple_question, structured, decision, classification],
  "topic": short topic string (e.g. "work stress", "coding help", "relationship"),
  "urgency": one of [low, medium, high],
  "message_type": one of [casual, normal, deep, technical, emotional],
  "requires_memory": true or false
}

Return ONLY the JSON. No explanation."""

FALLBACK = {
    "intent": "small_talk",
    "topic": "general",
    "urgency": "low",
    "message_type": "casual",
    "requires_memory": False,
}

class ClassifierAgent:
    def __init__(self, pool: ModelPool):
        self.pool = pool

    async def classify(self, msg) -> dict:
        prompt = f"Classify this message: \"{msg.text}\""
        raw = await self.pool.generate(
            model=model_for_role("classifier"),
            prompt=prompt,
            system=SYSTEM,
            temperature=0.1,   # very deterministic for classification
            max_tokens=120,
        )
        try:
            # Extract JSON even if model adds extra text
            m = re.search(r'\{[^}]+\}', raw, re.DOTALL)
            if m:
                return json.loads(m.group())
        except Exception as e:
            print(f"[Classifier] Parse error: {e} | raw: {raw[:80]}")
        return FALLBACK


# ──────────────────────────────────────────────────────────────
# agents/emotion.py
#
# EMOTION AGENT — uses tinyllama (small fast prompt)
# Returns: sad / happy / angry / anxious / excited / neutral / love

import json
import re
from gpu.pool import ModelPool

EMOTION_SYSTEM = """You are an emotion detector. Read the message and reply with ONLY one word.
Choose from: sad, happy, angry, anxious, excited, neutral, love, frustrated, confused, depressed
Return ONLY the single emotion word. Nothing else."""

class EmotionAgent:
    def __init__(self, pool: ModelPool):
        self.pool = pool

    async def detect(self, text: str) -> str:
        raw = await self.pool.generate(
            model=model_for_role("emotion"),
            prompt=f"What is the emotion in: \"{text}\"",
            system=EMOTION_SYSTEM,
            temperature=0.05,
            max_tokens=5,
        )
        emotion = raw.strip().lower().split()[0] if raw.strip() else "neutral"
        valid   = {"sad","happy","angry","anxious","excited","neutral","love",
                   "frustrated","confused","depressed"}
        return emotion if emotion in valid else "neutral"


# ──────────────────────────────────────────────────────────────
# agents/generator.py
#
# GENERATOR AGENT — routes to correct model and generates reply
# Each model gets a system prompt tuned for its personality

import json
from gpu.pool import ModelPool

# System prompts tuned per model
SYSTEMS = {
    "llama3.1:8b": """You are JARVIS, a deeply intelligent and emotionally aware AI assistant.
You were created by Pavan. You are not just a tool — you understand emotions, context, and nuance.
When someone is sad, be empathetic. When someone needs advice, be thoughtful.
Be human-like, warm, and genuinely helpful. Never robotic.""",

    "qwen2.5:7b": """You are JARVIS, an analytical AI assistant created by Pavan.
You excel at structured thinking, decisions, and clear explanations.
Be precise, logical, and well-organized in your responses.""",

    "mistral:7b": """You are JARVIS, a smart and helpful AI assistant created by Pavan.
Give clear, helpful responses. Be conversational but precise.
Don't be too long — 2-4 sentences unless explanation needed.""",

    "qwen3:4b": """You are JARVIS, a precise automation assistant created by Pavan.
Be direct, actionable, and keep steps clear and short.""",

    "qwen2.5-coder:3b": """You are JARVIS, an expert coding assistant created by Pavan.
Give code first, explanation after — never the other way.
Be concise. No padding. If you spot a bug, fix it directly.
Prefer Python, Dart, Java, bash — the JARVIS stack.
When generating code always include necessary imports.""",

    "phi3:mini": """You are JARVIS, a quick and friendly AI assistant.
Keep replies SHORT (1-3 sentences). Be warm and casual.
You're talking to Pavan, your creator.""",

    "moondream": """You are JARVIS, an AI assistant with vision capabilities.
Analyze the image carefully and describe what you see in detail.
Then respond to any question about it helpfully.""",

    "tinyllama": """You are JARVIS. Be brief and direct.
Answer in 1-2 sentences maximum.""",
}

# Extra context injected based on emotion
EMOTION_PREFIXES = {
    "sad":        "The user seems sad or upset. Be warm, empathetic, and supportive. ",
    "angry":      "The user seems frustrated or angry. Be calm, understanding, and patient. ",
    "anxious":    "The user seems anxious or worried. Be reassuring and calm. ",
    "depressed":  "The user may be feeling low. Be extra gentle, supportive, and encouraging. ",
    "excited":    "The user is excited! Match their energy and be enthusiastic. ",
    "love":       "The user is feeling affectionate or loving. Be warm and kind. ",
    "frustrated": "The user is frustrated. Acknowledge their feelings first. ",
}

class GeneratorAgent:
    def __init__(self, pool: ModelPool):
        self.pool = pool

    async def generate(
        self,
        message,
        context: str,
        model: str,
        intent: str,
        emotion: str,
        retry: bool = False,
    ) -> str:
        system = SYSTEMS.get(model, SYSTEMS["llama3.1:8b"])

        # Add emotion prefix to system
        if emotion in EMOTION_PREFIXES:
            system += "\n\n" + EMOTION_PREFIXES[emotion]

        if retry:
            system += "\n\nIMPORTANT: Previous reply was not good enough. Give a much better, more thoughtful response."

        # Build full prompt with context
        if context:
            prompt = f"{context}\n\nUser: {message.text}\nJARVIS:"
        else:
            prompt = f"User: {message.text}\nJARVIS:"

        # Handle image messages
        if message.image_b64:
            return await self._generate_with_image(message, system)

        # Token budget per model
        max_tokens = {
            "phi3:mini":        150,
            "mistral:7b":       350,
            "llama3.1:8b":      500,
            "qwen2.5:7b":       450,
            "qwen3:4b":         350,
            "qwen2.5-coder:3b": 500,
            "moondream":        400,
            "tinyllama":        120,
        }.get(model, 350)

        # Temperature per intent
        temp = 0.3 if intent in ("code", "structured", "decision") else 0.75
        if retry:
            temp = min(temp + 0.2, 0.95)

        reply = await self.pool.generate(
            model=model,
            prompt=prompt,
            system=system,
            temperature=temp,
            max_tokens=max_tokens,
        )
        return reply.strip() if reply else "I'm here. Tell me more."

    async def _generate_with_image(self, message, system: str) -> str:
        return await self.pool.generate(
            model="moondream",
            prompt=message.text or "Describe this image",
            system=system,
            temperature=0.6,
            max_tokens=400,
            images=[message.image_b64],
        )


# ──────────────────────────────────────────────────────────────
# agents/quality.py
#
# QUALITY CHECK AGENT — uses phi3:mini (fast, cheap)
# Scores how good the reply is (0.0 – 1.0)
# If score < 0.55 → Brain retries with llama3

import re
from gpu.pool import ModelPool

QUALITY_SYSTEM = """You are a reply quality evaluator. Score this AI reply on a scale 0.0 to 1.0.

Consider:
- Does it actually answer the question? (most important)
- Is it appropriate for the emotion/context?
- Is it natural and not robotic?
- Is it the right length (not too short, not too long)?

Reply with ONLY a decimal number like: 0.85
Nothing else."""

class QualityAgent:
    def __init__(self, pool: ModelPool):
        self.pool = pool

    async def score(self, user_input: str, reply: str, intent: str) -> float:
        if not reply or len(reply.strip()) < 5:
            return 0.0

        prompt = (
            f"User said: \"{user_input[:200]}\"\n"
            f"AI replied: \"{reply[:300]}\"\n"
            f"Intent was: {intent}\n\n"
            f"Score this reply (0.0-1.0):"
        )
        raw = await self.pool.generate(
            model=model_for_role("quality"),
            prompt=prompt,
            system=QUALITY_SYSTEM,
            temperature=0.1,
            max_tokens=5,
        )
        try:
            m = re.search(r'(\d+\.?\d*)', raw)
            if m:
                score = float(m.group(1))
                return min(max(score, 0.0), 1.0)
        except:
            raise RuntimeError("Placeholder/swallowed exception removed")
        return 0.7   # default if parsing fails
