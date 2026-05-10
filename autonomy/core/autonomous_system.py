"""
core/autonomous_system.py
═══════════════════════════════════════════════════════════════════
AUTONOMOUS SYSTEM WIRING

Single class that boots all 4 layers and the cognitive core.
This is imported in the patched jarvis_main.py.

STARTUP ORDER:
  Existing → WorldState, SemanticStore, Brain, AGI, FusionEngine
  New →      BrainExtension, AssistantEngine, ExecutorEngine,
             SystemController, AutonomousRoutes injected into API

NO EXISTING FILE IS MODIFIED.
This module imports existing modules and extends them.
═══════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
import asyncio, logging, os, time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("jarvis.autonomous")

PROJECT_ROOT = os.getenv("JARVIS_ROOT", ".")


# ─────────────────────────────────────────────────────────────────
#  AUTONOMOUS REQUEST / RESULT
# ─────────────────────────────────────────────────────────────────

@dataclass
class AutonomousRequest:
    """Single entry point for all user requests to the autonomous system."""
    text:       str
    user_id:    str   = "pavan"
    mode:       str   = "auto"    # auto|chat|plan|execute|code|system
    file:       str   = ""        # target file for code operations
    platform:   str   = "chat"
    image_b64:  str   = ""

@dataclass
class AutonomousResult:
    reply:          str
    intent:         str
    confidence:     float
    layer_used:     str         # l1|l2|l3|l4|multi
    execution_done: bool = False
    code_context:   Any  = None
    system_output:  Any  = None
    plan:           Any  = None
    latency_ms:     int  = 0


# ─────────────────────────────────────────────────────────────────
#  AUTONOMOUS SYSTEM
# ─────────────────────────────────────────────────────────────────

class AutonomousSystem:
    """
    The complete 4-layer autonomous intelligence system.
    Extends existing JARVIS without rewriting anything.
    """

    def __init__(self):
        # All components set during initialize()
        self.brain_ext   = None   # L1
        self.assistant   = None   # L2
        self.executor    = None   # L3
        self.controller  = None   # L4
        self.world       = None   # existing WorldState
        self.brain       = None   # existing JarvisBrain
        self.fusion      = None   # existing FusionEngine
        self.personality = None   # existing PersonalityFilter
        self.simulation  = None   # existing SimulationEngine
        self.store       = None   # existing SemanticStore
        self._ready      = False
        logger.info("[AS] AutonomousSystem created")

    # ─────────────────────────────────────────────────────────────
    #  INITIALIZE — called from jarvis_main.py after existing boot
    # ─────────────────────────────────────────────────────────────

    async def initialize(self,
                         brain, world, fusion, personality,
                         simulation, store,
                         device_id: str = None, adb_ip: str = None):
        """
        Wire all 4 layers using already-booted existing modules.
        Called from jarvis_main.py AFTER existing startup sequence.
        """
        logger.info("[AS] Initializing 4-layer autonomous system...")
        self.brain       = brain
        self.world       = world
        self.fusion      = fusion
        self.personality = personality
        self.simulation  = simulation
        self.store       = store

        # ── L1: Brain Extension ───────────────────────────────────
        from l1_brain.brain_ext import BrainExtension
        self.brain_ext = BrainExtension(brain, fusion, world, personality)
        logger.info("[AS] L1 Brain Extension ✓")

        # ── L2: Assistant Engine ──────────────────────────────────
        from l2_assistant.assistant_engine import AssistantEngine
        self.assistant = AssistantEngine(PROJECT_ROOT)
        self.assistant.initialize()
        logger.info("[AS] L2 Assistant Engine ✓ | %s", self.assistant.stats())

        # ── L4: System Controller (before L3 — L3 needs safety) ──
        from l4_controller.system_controller import SystemController, ExecutionSandbox
        self.controller = SystemController(
            world_state=world,
            working_dir=PROJECT_ROOT,
            device_id=device_id,
            adb_ip=adb_ip,
        )
        if adb_ip:
            self.controller.adb.connect()
        logger.info("[AS] L4 System Controller ✓")

        # ── L3: Executor Engine ───────────────────────────────────
        from l3_executor.executor_engine import ExecutorEngine
        sandbox = ExecutionSandbox(working_dir=PROJECT_ROOT)
        self.executor = ExecutorEngine(
            sandbox      = sandbox,
            safety_guard = self.controller.safety,
            simulation   = simulation,
            brain_ext    = self.brain_ext,
            world_state  = world,
        )
        logger.info("[AS] L3 Executor Engine ✓")

        self._ready = True
        logger.info("[AS] ✓ All 4 layers ready")

    # ─────────────────────────────────────────────────────────────
    #  MAIN ENTRY POINT — process any request
    # ─────────────────────────────────────────────────────────────

    async def process(self, req: AutonomousRequest) -> AutonomousResult:
        """
        Route request through correct layer(s).

        ROUTING:
          mode=chat    → L1 only
          mode=code    → L1 + L2
          mode=plan    → L1 → decompose → no execution
          mode=execute → L1 → L3 → L4
          mode=system  → L4 directly
          mode=auto    → L1 decides routing
        """
        if not self._ready:
            return AutonomousResult(
                reply="System still initializing. Please wait.",
                intent="error", confidence=0, layer_used="none")

        t0 = time.time()

        # Build message for L1
        from jarvis_brain.orchestrator.brain import Message as BMsg
        msg = BMsg(
            text      = req.text,
            user_id   = req.user_id,
            platform  = req.platform,
            image_b64 = req.image_b64,
        )

        mode = req.mode

        # ── mode=system — skip brain, go direct to L4 ────────────
        if mode == "system":
            return await self._route_system(req, t0)

        # ── L1: Think ────────────────────────────────────────────
        brain_result = await self.brain_ext.think(msg)

        # ── mode=auto: let brain decide routing ──────────────────
        if mode == "auto":
            if brain_result.needs_system:
                mode = "system"
            elif brain_result.needs_execution:
                mode = "execute"
            elif brain_result.needs_code:
                mode = "code"
            else:
                mode = "chat"

        # ── mode=chat — return brain reply ───────────────────────
        if mode == "chat":
            return AutonomousResult(
                reply      = brain_result.reply,
                intent     = brain_result.intent,
                confidence = brain_result.confidence,
                layer_used = "l1",
                latency_ms = int((time.time()-t0)*1000),
            )

        # ── mode=code — L1 + L2 ──────────────────────────────────
        if mode == "code":
            ctx = None
            if req.file:
                ctx = self.assistant.build_context(req.file, brain_result.intent)
                # Enrich reply with code context
                enriched_reply = (
                    f"{brain_result.reply}\n\n"
                    f"**Code Context:**\n{ctx.to_prompt_context(3000)}"
                    if ctx.relevant_code else brain_result.reply
                )
            else:
                enriched_reply = brain_result.reply

            return AutonomousResult(
                reply        = enriched_reply,
                intent       = brain_result.intent,
                confidence   = brain_result.confidence,
                layer_used   = "l1+l2",
                code_context = ctx,
                latency_ms   = int((time.time()-t0)*1000),
            )

        # ── mode=plan — return plan without executing ─────────────
        if mode == "plan":
            plan = await self.brain_ext.plan(req.text, req.user_id)
            reply = plan["plan_text"]
            return AutonomousResult(
                reply      = reply,
                intent     = brain_result.intent,
                confidence = brain_result.confidence,
                layer_used = "l1",
                plan       = plan,
                latency_ms = int((time.time()-t0)*1000),
            )

        # ── mode=execute — L1 → L3 → L4 ──────────────────────────
        if mode == "execute":
            # Build or reuse execution plan from brain
            raw_steps = brain_result.execution_plan
            if not raw_steps:
                # Decompose on demand
                raw_steps = await self.brain_ext._orchestrator.decompose_to_steps(
                    req.text, brain_result.intent)

            plan  = self.executor.from_steps(req.text, raw_steps)
            result = await self.executor.run(plan)

            # Format result reply
            if result.success:
                reply = (f"{brain_result.reply}\n\n"
                         f"✓ Executed {result.steps_done} steps successfully.\n"
                         f"Output:\n{result.output[:800]}")
            else:
                reply = (f"{brain_result.reply}\n\n"
                         f"⚠ Execution partial: {result.steps_done} done, "
                         f"{result.steps_fail} failed.\n"
                         f"Last error:\n{result.error}")

            reply = self.personality.transform(reply, self.world.snapshot())
            return AutonomousResult(
                reply          = reply,
                intent         = brain_result.intent,
                confidence     = brain_result.confidence,
                layer_used     = "l1+l3+l4",
                execution_done = True,
                system_output  = result,
                plan           = plan,
                latency_ms     = int((time.time()-t0)*1000),
            )

        # Fallback
        return AutonomousResult(
            reply      = brain_result.reply,
            intent     = brain_result.intent,
            confidence = brain_result.confidence,
            layer_used = "l1",
            latency_ms = int((time.time()-t0)*1000),
        )

    async def _route_system(self, req: AutonomousRequest, t0: float) -> AutonomousResult:
        """Route directly to L4 SystemController."""
        result = await self.controller.execute(req.text)
        reply  = (f"✓ {result['output']}" if result["success"]
                  else f"✗ {result['error']}")
        return AutonomousResult(
            reply         = reply,
            intent        = "system_control",
            confidence    = 0.95,
            layer_used    = "l4",
            execution_done= True,
            system_output = result,
            latency_ms    = int((time.time()-t0)*1000),
        )

    def status(self) -> dict:
        return {
            "ready":      self._ready,
            "layers": {
                "l1_brain":      "ok" if self.brain_ext else "not_init",
                "l2_assistant":  str(self.assistant.stats()) if self.assistant else "not_init",
                "l3_executor":   "ok" if self.executor else "not_init",
                "l4_controller": "ok" if self.controller else "not_init",
            },
            "adb": self.controller.adb.connected if self.controller else False,
        }


# ─────────────────────────────────────────────────────────────────
#  SINGLETON
# ─────────────────────────────────────────────────────────────────

_system: Optional[AutonomousSystem] = None

def get_system() -> Optional[AutonomousSystem]:
    return _system

def create_system() -> AutonomousSystem:
    global _system
    _system = AutonomousSystem()
    return _system
