"""
l1_brain/brain_ext.py
═══════════════════════════════════════════════════════════════════
LEVEL 1 — BRAIN EXTENSION
Extends existing JarvisBrain without modifying jarvis_brain/*.

Adds:
  • FusionEngine-enriched prompts (world state + memory + vision)
  • PromptOrchestrator for multi-step reasoning chains
  • L2/L3 routing: if intent=code/task → hand off to lower layers
  • Response personality transform on every output
═══════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
import asyncio, logging, time
from dataclasses import dataclass, field
from typing import Any, Optional, TYPE_CHECKING

logger = logging.getLogger("jarvis.l1")

if TYPE_CHECKING:
    from jarvis_brain.orchestrator.brain import JarvisBrain, Message, BrainResult
    from jarvis_cognitive.core.fusion_engine import FusionEngine, FusionContext
    from jarvis_cognitive.core.world_state import WorldState
    from jarvis_cognitive.core.personality_layer import PersonalityFilter


# ─────────────────────────────────────────────────────────────────
#  AUTONOMOUS BRAIN RESULT  (superset of BrainResult)
# ─────────────────────────────────────────────────────────────────

@dataclass
class AutonomousBrainResult:
    """BrainResult extended with routing decisions for lower layers."""
    reply:           str
    model_used:      str
    intent:          str
    emotion:         str
    confidence:      float
    latency_ms:      int
    # Autonomous extensions
    needs_execution: bool  = False   # → route to L3 Executor
    needs_code:      bool  = False   # → route to L2 Assistant
    needs_system:    bool  = False   # → route to L4 Controller
    execution_plan:  list  = field(default_factory=list)  # steps for L3
    fusion_context:  Optional[Any] = None
    personality_applied: bool = False


# ─────────────────────────────────────────────────────────────────
#  INTENTS THAT NEED LOWER LAYERS
# ─────────────────────────────────────────────────────────────────

EXECUTOR_INTENTS = {
    "code", "refactor", "debug", "test", "build", "deploy",
    "script", "automation", "fix", "implement", "create_file",
}

CODE_INTENTS = {
    "code", "review", "explain_code", "refactor", "test",
    "debug", "architecture", "code_review", "improve_code",
}

SYSTEM_INTENTS = {
    "open_app", "terminal", "file_operation", "system_control",
    "send_message", "adb_control", "schedule", "reminder_set",
    "volume", "screenshot", "browser",
}


# ─────────────────────────────────────────────────────────────────
#  BRAIN EXTENSION
# ─────────────────────────────────────────────────────────────────

class BrainExtension:
    """
    Wraps existing JarvisBrain.think() with:
    1. FusionEngine context injection before LLM call
    2. PersonalityFilter on output
    3. Routing decision (which lower layer to activate)
    4. Multi-step reasoning for complex requests

    USAGE:
        brain_ext = BrainExtension(brain, fusion, world, personality)
        result = await brain_ext.think(msg)
        if result.needs_execution:
            await executor.run(result.execution_plan)
    """

    def __init__(self,
                 brain:       "JarvisBrain",
                 fusion:      "FusionEngine",
                 world:       "WorldState",
                 personality: "PersonalityFilter"):
        self.brain       = brain
        self.fusion      = fusion
        self.world       = world
        self.personality = personality
        self._orchestrator = PromptOrchestrator(brain)
        logger.info("[L1] BrainExtension initialized")

    async def think(self, msg: "Message") -> AutonomousBrainResult:
        t0 = time.time()

        # ── Step 1: Enrich message with fusion context ───────────
        snap    = self.world.snapshot()
        fc: "FusionContext" = await self.fusion.fuse(
            text_input=msg.text,
            world_snapshot=snap,
        )
        logger.debug("[L1] FusionContext sources: %s", fc.sources_used)

        # Inject fusion context into message (non-destructive copy)
        from jarvis_brain.orchestrator.brain import Message as BMsg
        enriched = BMsg(
            text      = f"{fc.to_llm_prompt()}\n\nUser: {msg.text}",
            user_id   = msg.user_id,
            image_b64 = msg.image_b64,
            platform  = msg.platform,
            session   = msg.session,
        )

        # ── Step 2: Run existing brain pipeline ──────────────────
        base_result = await self.brain.think(enriched)

        # ── Step 3: Apply personality filter ─────────────────────
        reply = self.personality.transform(base_result.reply, snap)

        # ── Step 4: Routing decision ─────────────────────────────
        needs_execution = base_result.intent in EXECUTOR_INTENTS
        needs_code      = base_result.intent in CODE_INTENTS
        needs_system    = base_result.intent in SYSTEM_INTENTS

        # ── Step 5: Build execution plan if needed ───────────────
        execution_plan = []
        if needs_execution:
            execution_plan = await self._orchestrator.decompose_to_steps(
                goal=msg.text,
                intent=base_result.intent,
            )

        latency = int((time.time() - t0) * 1000)
        logger.info("[L1] think() done in %dms | intent=%s | route: exec=%s code=%s sys=%s",
                    latency, base_result.intent,
                    needs_execution, needs_code, needs_system)

        return AutonomousBrainResult(
            reply           = reply,
            model_used      = base_result.model_used,
            intent          = base_result.intent,
            emotion         = base_result.emotion,
            confidence      = base_result.confidence,
            latency_ms      = latency,
            needs_execution = needs_execution,
            needs_code      = needs_code,
            needs_system    = needs_system,
            execution_plan  = execution_plan,
            fusion_context  = fc,
            personality_applied = True,
        )

    async def plan(self, goal: str, user_id: str = "pavan") -> dict:
        """
        High-level planning mode. Returns structured plan.
        Used by CLI: jarvis plan "goal"
        """
        from jarvis_brain.orchestrator.brain import Message as BMsg
        snap  = self.world.snapshot()
        fc    = await self.fusion.fuse(text_input=goal, world_snapshot=snap)

        plan_prompt = (
            f"{fc.to_llm_prompt()}\n\n"
            f"Goal: {goal}\n\n"
            f"Break this into a concrete numbered action plan. "
            f"For each step: what to do, which tool (code/terminal/browser/adb), "
            f"expected output. Be specific."
        )
        msg = BMsg(text=plan_prompt, user_id=user_id)
        result = await self.brain.think(msg)
        steps  = await self._orchestrator.decompose_to_steps(goal, "planning")

        return {
            "goal":       goal,
            "plan_text":  self.personality.transform(result.reply, snap),
            "steps":      steps,
            "confidence": result.confidence,
            "model":      result.model_used,
        }


# ─────────────────────────────────────────────────────────────────
#  PROMPT ORCHESTRATOR — multi-step reasoning chains
# ─────────────────────────────────────────────────────────────────

class PromptOrchestrator:
    """
    Chains multiple LLM calls to reason through complex tasks.
    Existing brain.think() handles single messages.
    This handles sequences: think → verify → refine → output.
    """

    def __init__(self, brain: "JarvisBrain"):
        self.brain = brain

    async def decompose_to_steps(self, goal: str, intent: str) -> list:
        """
        Ask the LLM to decompose a goal into executable steps.
        Returns list of step dicts.
        """
        from jarvis_brain.orchestrator.brain import Message as BMsg

        system_context = (
            "You are a task planner. Given a goal, output ONLY a JSON array of steps. "
            "Each step: {\"step\": int, \"action\": str, \"tool\": str, "
            "\"command\": str, \"expected\": str}. "
            "Tools: code|terminal|browser|adb|file|api. No markdown, pure JSON."
        )

        prompt = f"{system_context}\n\nGoal: {goal}"
        msg    = BMsg(text=prompt, user_id="system")

        try:
            result = await self.brain.think(msg)
            import json, re
            # Extract JSON array
            m = re.search(r'\[[\s\S]*\]', result.reply)
            if m:
                return json.loads(m.group())
        except Exception as e:
            logger.warning("[L1] decompose_to_steps failed: %s", e)

        # Fallback: minimal plan
        return [
            {"step": 1, "action": goal, "tool": "code",
             "command": "", "expected": "task completed"}
        ]

    async def chain(self, prompts: list[str], user_id: str = "system") -> list[str]:
        """
        Run a sequence of prompts where each output feeds the next.
        Used for: think → critique → improve → final.
        """
        from jarvis_brain.orchestrator.brain import Message as BMsg
        results = []
        context = ""
        for prompt in prompts:
            full_prompt = f"{context}\n\n{prompt}".strip() if context else prompt
            result      = await self.brain.think(BMsg(text=full_prompt, user_id=user_id))
            results.append(result.reply)
            context = f"Previous step output:\n{result.reply[:500]}"
        return results
