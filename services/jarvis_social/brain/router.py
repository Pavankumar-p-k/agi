"""
brain/router.py — Hybrid Brain Router
======================================
Routes messages to server brain (heavy NLP) or local brain (fast).
Auto-falls back to local within 2 seconds if server unavailable.
"""
from __future__ import annotations
import asyncio, logging, time, re, random
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

SERVER_TIMEOUT  = 2.0    # seconds before fallback
SERVER_URL      = "http://localhost:11434"  # Ollama default
SERVER_MODEL    = "llama3.2"
LOCAL_MODEL     = "tinyllama"   # fast lightweight fallback


@dataclass
class BrainResponse:
    text:      str
    source:    str     # "server" | "local" | "fallback"
    latency_ms: float
    model:     str = ""


# ── Server brain (Ollama) ─────────────────────────────────────────

async def _call_server(messages: list[dict], timeout: float = SERVER_TIMEOUT) -> Optional[str]:
    try:
        import httpx
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{SERVER_URL}/api/chat",
                json={"model": SERVER_MODEL, "messages": messages, "stream": False},
            )
            data = resp.json()
            return data.get("message", {}).get("content", "")
    except Exception as e:
        logger.debug("[Brain] Server unavailable: %s", e)
        return None


async def _server_available() -> bool:
    try:
        import httpx
        async with httpx.AsyncClient(timeout=1.5) as client:
            r = await client.get(f"{SERVER_URL}/api/tags")
            return r.status_code == 200
    except Exception:
        return False


# ── Local brain (lightweight) ─────────────────────────────────────

class LocalBrain:
    """
    Fast local response generator.
    Uses tinyllama via Ollama if available, otherwise template-based.
    """

    TEMPLATES = {
        "greeting":    ["hey! how's it going?", "hey! what's up?", "hey, been a while!"],
        "question":    ["interesting question — let me think about that", "good point, honestly"],
        "statement":   ["yeah that makes sense", "totally get that", "true, makes sense"],
        "long":        ["haha yeah", "that's actually interesting", "fair enough"],
        "short":       ["haha", "lol", "😄", "true", "facts"],
        "default":     ["got it", "yeah", "for sure", "noted"],
    }

    def classify(self, text: str) -> str:
        t = text.lower().strip()
        if t.endswith("?"):
            return "question"
        if any(w in t for w in ["hi","hey","hello","yo","sup"]):
            return "greeting"
        if len(t) < 15:
            return "short"
        if len(t) > 100:
            return "long"
        return "statement"

    async def generate(self, messages: list[dict], traits: dict) -> str:
        # Try tinyllama first
        try:
            import httpx
            async with httpx.AsyncClient(timeout=1.5) as client:
                r = await client.post(f"{SERVER_URL}/api/chat", json={
                    "model": LOCAL_MODEL,
                    "messages": messages,
                    "stream": False,
                    "options": {"temperature": 0.7 + traits.get("energy",0.5)*0.2}
                })
                text = r.json().get("message",{}).get("content","")
                if text:
                    return text
        except Exception as err:
            import logging
            logging.getLogger(__name__).error("Exception swallowed: %s", err)
            raise RuntimeError(f"Exception swallowed: {err}")

        # Template fallback
        last = messages[-1]["content"] if messages else ""
        msg_type = self.classify(last)
        options = self.TEMPLATES.get(msg_type, self.TEMPLATES["default"])
        base = random.choice(options)
        return self._apply_traits(base, traits)

    def _apply_traits(self, text: str, traits: dict) -> str:
        emoji_level = traits.get("emoji", 0.3)
        if emoji_level > 0.6 and random.random() < emoji_level:
            EMOJIS = ["😊","😄","🙌","✨","😂","👍","🔥","💯"]
            text = text + " " + random.choice(EMOJIS)
        return text


_local_brain = LocalBrain()


# ── Prompt builder ────────────────────────────────────────────────

def build_prompt(friend_profile, history: list[dict],
                 user_message: str, memory_tokens: list[dict]) -> list[dict]:
    """Build message list for LLM from friend profile + history."""

    traits = friend_profile.traits
    special = friend_profile.special_mode

    # Tone description from traits
    tone_desc = []
    if traits.get("humor",0) > 0.6:    tone_desc.append("use light humor when natural")
    if traits.get("caring",0) > 0.6:   tone_desc.append("be warm and caring")
    if traits.get("formality",0) < 0.4: tone_desc.append("keep it casual and relaxed")
    if traits.get("emoji",0) > 0.5:    tone_desc.append("use emojis lightly")
    if traits.get("energy",0) > 0.6:   tone_desc.append("be energetic and enthusiastic")
    if traits.get("directness",0) > 0.6: tone_desc.append("be direct and concise")
    if special:                         tone_desc.append("this is a close friend — be warm")

    # Memory context
    mem_ctx = ""
    if memory_tokens:
        items = [f"- {m['token_type']}: {m['token_value']}" for m in memory_tokens[:5]]
        mem_ctx = "\n[Things you know about them]\n" + "\n".join(items)

    system = f"""You are JARVIS, Pavan's AI assistant helping manage a conversation with {friend_profile.display_name}.

Respond AS Pavan in a natural, authentic way. Keep responses SHORT (1-3 sentences usually).
Tone: {', '.join(tone_desc) if tone_desc else 'natural and friendly'}.
NEVER mention being an AI. NEVER be overly formal. NEVER escalate conflicts.{mem_ctx}

Auto-reply disclosure: This reply is sent by JARVIS on Pavan's behalf. Pavan is currently away."""

    messages = [{"role": "system", "content": system}]
    messages.extend(history[-8:])  # last 8 turns
    messages.append({"role": "user", "content": user_message})
    return messages


# ── Main router ───────────────────────────────────────────────────

class BrainRouter:

    def __init__(self):
        self._server_ok  = True    # optimistic start
        self._last_check = 0.0

    async def route(self, friend_profile, history: list[dict],
                    user_message: str, memory_tokens: list[dict] = None) -> BrainResponse:
        """Route to best available brain. Always returns a response."""
        start = time.time()
        messages = build_prompt(friend_profile, history, user_message, memory_tokens or [])

        # Try server first if likely available
        if self._server_ok or (time.time() - self._last_check > 60):
            result = await self._try_server(messages)
            if result:
                self._server_ok = True
                return BrainResponse(result, "server", (time.time()-start)*1000, SERVER_MODEL)

        # Local fallback
        self._server_ok = False
        self._last_check = time.time()
        result = await _local_brain.generate(messages, friend_profile.traits)
        return BrainResponse(result, "local", (time.time()-start)*1000, LOCAL_MODEL)

    async def _try_server(self, messages: list[dict]) -> Optional[str]:
        try:
            result = await asyncio.wait_for(
                _call_server(messages, SERVER_TIMEOUT),
                timeout=SERVER_TIMEOUT + 0.5
            )
            return result
        except (asyncio.TimeoutError, Exception) as e:
            logger.debug("[Router] Server failed: %s", e)
            return None

    async def generate_initiation(self, friend_profile,
                                   memory_tokens: list[dict] = None,
                                   initiation_type: str = "check_in") -> BrainResponse:
        """Generate an initiation message (check-in, etc.)."""
        name = friend_profile.display_name
        templates = {
            "check_in":   f"hey {name}, how've you been?",
            "continuation": f"hey, been thinking about our last conversation",
            "casual":     f"yo, what's up?",
        }
        fallback = templates.get(initiation_type, templates["check_in"])

        messages = build_prompt(
            friend_profile, [],
            f"[Generate a short, natural {initiation_type} message to start a conversation]",
            memory_tokens or []
        )
        start = time.time()
        result = await self._try_server(messages)
        if result:
            return BrainResponse(result, "server", (time.time()-start)*1000)
        return BrainResponse(fallback, "fallback", (time.time()-start)*1000)
