"""
l4_controller/vision_integration.py
═══════════════════════════════════════════════════════════════════
Wires the existing VisionAgent (jarvis_vision_complete) into
the L4 ControllerLayer as a new action type: "vision_task"

Extends ControllerLayer WITHOUT modifying controller_layer.py.

Usage in controller_layer.py execute():
    if action == "vision_task":
        return await self._vision.run(params["instruction"])

Usage from orchestrator:
    result = await controller.execute(
        "vision_task",
        instruction="open chrome and search for Python tutorials"
    )

The VisionAgent:
  1. Takes screenshot → LLava describes screen state
  2. Llama3 plans steps
  3. pyautogui executes each step
  4. Screenshots after each step → LLava verifies
  5. Self-corrects if step failed
  6. Returns TaskResult with full step log
"""
from __future__ import annotations
import logging, time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("jarvis.l4.vision")


@dataclass
class VisionTaskResult:
    success:      bool
    instruction:  str
    steps_done:   int
    steps_total:  int
    result:       str    # final description of what was accomplished
    error:        str = ""
    duration_ms:  int = 0


class VisionIntegration:
    """
    Wraps jarvis_vision_complete/core/vision_agent.py.
    Called by ControllerLayer when action == "vision_task".
    """

    def __init__(self):
        self._agent = None
        self._available = False
        self._load_agent()

    def _load_agent(self):
        try:
            from jarvis_vision_complete.core.vision_agent import VisionAgent
            self._agent     = VisionAgent()
            self._available = True
            logger.info("[VisionIntegration] VisionAgent loaded ✓")
        except ImportError:
            logger.info("[VisionIntegration] VisionAgent not available — "
                        "install pyautogui + mss + Pillow + LLava model")
        except Exception as e:
            logger.warning("[VisionIntegration] VisionAgent load error: %s", e)

    async def run(self, instruction: str) -> VisionTaskResult:
        t0 = time.time()

        if not self._available or self._agent is None:
            return VisionTaskResult(
                success=False,
                instruction=instruction,
                steps_done=0,
                steps_total=0,
                result="",
                error="VisionAgent not available — missing pyautogui/mss/LLava",
                duration_ms=0,
            )

        try:
            import asyncio
            # VisionAgent.run() is async
            task = await self._agent.run(instruction, platform="pc")
            return VisionTaskResult(
                success     = task.status == "done",
                instruction = instruction,
                steps_done  = sum(1 for s in task.steps if s.status == "done"),
                steps_total = len(task.steps),
                result      = task.result or "Task completed",
                error       = task.error,
                duration_ms = int((time.time() - t0) * 1000),
            )
        except Exception as e:
            logger.error("[VisionIntegration] Task error: %s", e)
            return VisionTaskResult(
                success=False, instruction=instruction,
                steps_done=0, steps_total=0, result="",
                error=str(e), duration_ms=int((time.time()-t0)*1000),
            )

    @property
    def available(self) -> bool:
        return self._available


def extend_controller(controller_layer):
    """
    Monkey-patches ControllerLayer to add vision_task action.
    Call once after ControllerLayer is instantiated:
        extend_controller(l4_controller)
    """
    vision = VisionIntegration()

    original_execute = controller_layer.execute.__func__ if hasattr(
        controller_layer.execute, "__func__") else None

    async def execute_with_vision(self, action: str, **params):
        if action == "vision_task":
            instruction = params.get("instruction", "")
            if not instruction:
                from l4_controller.controller_layer import ControlResult, ControlAction
                return ControlResult(ControlAction.TERMINAL, False,
                                     "", "No instruction provided")
            r = await vision.run(instruction)
            from l4_controller.controller_layer import ControlResult, ControlAction
            return ControlResult(
                action      = ControlAction.APP_OPEN,  # closest action type
                success     = r.success,
                output      = r.result,
                error       = r.error,
                duration_ms = r.duration_ms,
            )
        # Fall through to original execute
        return await type(self).execute(self, action, **params)

    # Only patch if not already patched
    if not getattr(controller_layer.__class__, "_vision_patched", False):
        controller_layer.__class__._original_execute = (
            controller_layer.__class__.execute)
        controller_layer.__class__.execute = execute_with_vision
        controller_layer.__class__._vision_patched = True
        logger.info("[VisionIntegration] ControllerLayer extended with vision_task ✓")

    controller_layer._vision = vision
    return controller_layer
