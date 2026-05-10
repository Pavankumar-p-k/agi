"""
l1_brain/brain_layer.py
═══════════════════════════════════════════════════════════════════
LEVEL 1 — BRAIN LAYER  (ChatGPT / Claude equivalent)

WRAPS (does not replace):
  jarvis_brain/orchestrator/brain.py  → JarvisBrain 8-agent pipeline
  jarvis_brain/gpu/pool.py            → ModelPool RTX 4050
  jarvis_fixed/core/fusion_engine.py  → FusionEngine
  jarvis_fixed/memory/semantic_store.py
  jarvis_fixed/core/personality_layer.py

ADDS:
  • LayerRoute enum — routes to L1/L2/L3/L4
  • ReasoningPlanner — LLM multi-step task decomposition
  • Goal extractor — parses goals from natural language
  • Context enrichment via FusionEngine before every LLM call
"""
from __future__ import annotations
import asyncio, json, logging, re, time
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("jarvis.l1_brain")


# ── Layer routing ─────────────────────────────────────────────────

class LayerRoute(str, Enum):
    BRAIN      = "brain"       # pure NL reply stays in L1
    ASSISTANT  = "assistant"   # code understanding → L2
    EXECUTOR   = "executor"    # task execution → L3
    CONTROLLER = "controller"  # system action → L4


ROUTING_TABLE: dict[str, LayerRoute] = {
    "greeting": LayerRoute.BRAIN, "small_talk": LayerRoute.BRAIN,
    "question": LayerRoute.BRAIN, "emotional_support": LayerRoute.BRAIN,
    "philosophy": LayerRoute.BRAIN, "advice": LayerRoute.BRAIN,
    "acknowledgment": LayerRoute.BRAIN,
    "code": LayerRoute.ASSISTANT, "code_explain": LayerRoute.ASSISTANT,
    "debug": LayerRoute.ASSISTANT, "architecture": LayerRoute.ASSISTANT,
    "task": LayerRoute.EXECUTOR, "planning": LayerRoute.EXECUTOR,
    "automation": LayerRoute.EXECUTOR, "code_execute": LayerRoute.EXECUTOR,
    "structured": LayerRoute.EXECUTOR, "decision": LayerRoute.EXECUTOR,
    "open_app": LayerRoute.CONTROLLER, "system_control": LayerRoute.CONTROLLER,
    "android": LayerRoute.CONTROLLER, "file_operation": LayerRoute.CONTROLLER,
    "send_message": LayerRoute.CONTROLLER, "reminder": LayerRoute.CONTROLLER,
}

CONTROLLER_KW = ["open ","launch ","close ","send ","call ",
                  "screenshot","volume","battery","whatsapp","instagram"]
EXECUTOR_KW   = ["execute","run script","create file","build ","generate ",
                  "write script","test ","deploy ","compute "]
ASSISTANT_KW  = ["explain this code","review this","fix bug","refactor",
                  "what does this do","optimize this"]


@dataclass
class L1Result:
    reply:         str
    intent:        str
    emotion:       str
    confidence:    float
    latency_ms:    int
    route:         LayerRoute = LayerRoute.BRAIN
    plan:          list       = field(default_factory=list)
    goals:         list       = field(default_factory=list)
    requires_exec: bool       = False
    context_used:  dict       = field(default_factory=dict)
    model_used:    str        = "qwen3:4b"


class BrainLayer:
    """
    L1 façade — every user message enters here.
    Routes to L2/L3/L4 based on intent classification.
    """

    def __init__(self, brain, fusion_engine, semantic_store,
                 world_state, personality):
        self._brain       = brain           # JarvisBrain
        self._fusion      = fusion_engine   # FusionEngine
        self._store       = semantic_store  # SemanticStore
        self._world       = world_state     # WorldState
        self._personality = personality     # PersonalityFilter
        self._planner     = ReasoningPlanner(brain)
        logger.info("[L1] BrainLayer initialized — wraps JarvisBrain")

    async def process(self, text: str, platform: str = "chat",
                      image_b64: str = "", session: str = "") -> L1Result:
        t0 = time.time()

        # 1. Retrieve memories + fuse context
        memory_hits = []
        ctx_info    = {}
        try:
            memory_hits = self._store.recall(text, top_k=3)
            fused = self._fusion.fuse(
                text_input    = text,
                memory_hits   = memory_hits,
                world_snapshot= self._world.snapshot(),
            )
            ctx_info = {"sources": fused.sources_used,
                        "confidence": fused.confidence}
        except Exception as err:
            import logging
            logging.getLogger(__name__).error("Exception swallowed: %s", err)
            raise RuntimeError(f"Exception swallowed: {err}")

        # 2. Run existing JarvisBrain 8-agent pipeline
        intent = "small_talk"; emotion = "neutral"
        reply  = ""; model = "fallback"; conf = 0.3
        try:
            try:
                from orchestrator.brain import Message
            except ModuleNotFoundError:
                from orchestrator.brain import Message
            msg    = Message(text=text, platform=platform,
                             image_b64=image_b64, session=session)
            r      = await self._brain.think(msg)
            intent = r.intent;  emotion  = r.emotion
            reply  = r.reply;   model    = r.model_used
            conf   = r.confidence
        except Exception as e:
            logger.warning("[L1] JarvisBrain error: %s", e)

        # 3. Route decision
        route = self._route(intent, text)

        # 4. Plan if L3/L4 path
        plan = []; goals = []
        if route in (LayerRoute.EXECUTOR, LayerRoute.CONTROLLER):
            plan  = await self._planner.decompose(text, intent)
            goals = _extract_goals(text)

        return L1Result(
            reply=reply, intent=intent, emotion=emotion,
            confidence=conf,
            latency_ms=int((time.time() - t0) * 1000),
            route=route, plan=plan, goals=goals,
            requires_exec=route in (LayerRoute.EXECUTOR,
                                     LayerRoute.CONTROLLER),
            context_used=ctx_info, model_used=model,
        )

    def _route(self, intent: str, text: str) -> LayerRoute:
        if intent in ROUTING_TABLE:
            return ROUTING_TABLE[intent]
        tl = text.lower()
        if any(k in tl for k in CONTROLLER_KW): return LayerRoute.CONTROLLER
        if any(k in tl for k in EXECUTOR_KW):   return LayerRoute.EXECUTOR
        if any(k in tl for k in ASSISTANT_KW):  return LayerRoute.ASSISTANT
        return LayerRoute.BRAIN


def _extract_goals(text: str) -> list[dict]:
    verbs = ["create","build","write","fix","analyze","send",
             "open","run","test","deploy","explain","generate"]
    words = text.lower().split()
    goals = []
    for i, w in enumerate(words):
        if w in verbs and i + 1 < len(words):
            goals.append({"action": w,
                           "object": " ".join(words[i+1:i+5]),
                           "priority": 5})
    return goals or [{"action": "process",
                       "object": text[:60], "priority": 5}]


class ReasoningPlanner:
    SYSTEM = (
        "You are JARVIS task planner. Break the goal into 3-7 concrete, "
        "ordered steps. Return ONLY a JSON array of step strings. "
        "No explanation. No markdown."
    )

    def __init__(self, brain):
        self._brain = brain

    async def decompose(self, task: str, intent: str) -> list[str]:
        try:
            raw = await self._brain.pool.generate(
                model="qwen3:4b",
                prompt=f"Goal: {task}",
                system=self.SYSTEM,
                temperature=0.1,
                max_tokens=250,
            )
            m = re.search(r"\[.*\]", raw, re.DOTALL)
            if m:
                return json.loads(m.group())
        except Exception as e:
            logger.warning("[L1] Planner: %s", e)
        return [f"1. Analyze: {task[:60]}", "2. Execute", "3. Verify"]
