"""
core/autonomous_orchestrator.py
═══════════════════════════════════════════════════════════════════
JARVIS AUTONOMOUS ORCHESTRATOR
Wires all 4 layers. Every user request flows through here.

Request flow:
  Input
    → L1 Brain: classify + reason + plan + route
      → BRAIN route:       reply directly
      → ASSISTANT route:   → L2 (code understanding)
      → EXECUTOR route:    → L3 (plan → execute → verify)
      → CONTROLLER route:  → L4 (system action with safety guard)
    → personality filter
    → WorldState update
    → SemanticStore write
    → return OrchestratorResult

DOES NOT replace:
  existing JarvisBrain, WorldState, CognitiveCore, FusionEngine,
  DecisionEngine, PersonalityFilter, NotificationHub, ADB, etc.
"""
from __future__ import annotations
import asyncio, logging, re, time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("jarvis.orchestrator")


@dataclass
class OrchestratorResult:
    reply:        str
    source:       str        # l1_brain | l2_assistant | l3_executor | l4_controller
    intent:       str
    emotion:      str
    confidence:   float
    latency_ms:   int
    plan:         list       = field(default_factory=list)
    exec_output:  str        = ""
    route:        str        = "brain"
    model_used:   str        = "qwen3:4b"


class AutonomousOrchestrator:
    """
    Master coordinator for all 4 intelligence layers.
    Instantiated once at startup via dependency injection.
    """

    def __init__(
        self,
        brain_layer,        # L1 BrainLayer
        assistant_layer,    # L2 AssistantLayer
        executor_layer,     # L3 ExecutorLayer
        controller_layer,   # L4 ControllerLayer
        # Existing systems — passed through, not replaced
        world_state,
        personality,
        fusion_engine,
        semantic_store,
        notification_hub,
    ):
        self._brain      = brain_layer
        self._assistant  = assistant_layer
        self._executor   = executor_layer
        self._controller = controller_layer
        self._world      = world_state
        self._personality= personality
        self._fusion     = fusion_engine
        self._store      = semantic_store
        self._hub        = notification_hub
        logger.info("[Orchestrator] All 4 layers wired ✓")

    async def process(self, text: str, platform: str = "chat",
                       image_b64: str = "",
                       session: str = "") -> OrchestratorResult:
        t0 = time.time()

        # ── 1. L1 Brain: classify + route + plan ─────────────────
        l1 = await self._brain.process(text, platform, image_b64, session)
        logger.info("[Orch] route=%s intent=%s conf=%.2f",
                    l1.route, l1.intent, l1.confidence)

        reply    = l1.reply
        exec_out = ""
        source   = "l1_brain"

        # Use the packaged autonomy modules (not top-level l1_brain)
        from autonomy.l1_brain.brain_layer import LayerRoute

        # ── 2. Route to correct layer ─────────────────────────────
        if l1.route == LayerRoute.ASSISTANT:
            source = "l2_assistant"
            try:
                r     = await self._assistant.handle(
                    action       = self._code_action(l1.intent, text),
                    code         = self._extract_code(text),
                    language     = self._infer_lang(text),
                    current_file = "",
                )
                reply = r.content
            except Exception as e:
                logger.warning("[Orch] L2 error: %s", e)
                reply = l1.reply

        elif l1.route == LayerRoute.EXECUTOR:
            source = "l3_executor"
            try:
                ctx = ""
                if self._store:
                    hits = self._store.recall(text, top_k=3)
                    ctx  = " | ".join(
                        h.get("text","")[:80] for h in hits)
                r       = await self._executor.execute(
                    goal    = text,
                    intent  = l1.intent,
                    context = ctx,
                )
                exec_out = r.output
                reply    = self._exec_reply(r, l1.reply)
            except Exception as e:
                logger.warning("[Orch] L3 error: %s", e)
                reply = l1.reply

        elif l1.route == LayerRoute.CONTROLLER:
            source = "l4_controller"
            try:
                r     = await self._dispatch_ctrl(l1, text)
                reply = (r.output if r.success
                          else l1.reply or f"Failed: {r.error}")
            except Exception as e:
                logger.warning("[Orch] L4 error: %s", e)
                reply = l1.reply

        # ── 3. Personality filter (only for L1 brain replies) ─────
        if source == "l1_brain" and self._personality and reply:
            try:
                snap  = self._world.snapshot() if self._world else {}
                reply = self._personality.transform(reply, snap)
            except Exception as e:
                logger.error("[Orch] Personality filter failed: %s", e)
                raise RuntimeError(f"Personality filter failed: {e}")

        # ── 4. Update WorldState ──────────────────────────────────
        if self._world:
            try:
                self._world.update_user_state(
                    last_voice_input  = text,
                    last_input_ts     = time.time(),
                    active            = True,
                    current_activity  = "talking",
                )
            except Exception as e:
                logger.error("[Orch] WorldState update failed: %s", e)
                raise RuntimeError(f"WorldState update failed: {e}")

        # ── 5. Persist to memory ──────────────────────────────────
        if self._store:
            try:
                self._store.remember(
                    f"User: {text}", category="conversation",
                    importance=0.6)
                if reply:
                    self._store.remember(
                        f"JARVIS: {reply}", category="conversation",
                        importance=0.5)
            except Exception as e:
                logger.error("[Orch] Memory persistence failed: %s", e)
                raise RuntimeError(f"Memory persistence failed: {e}")

        return OrchestratorResult(
            reply=reply, source=source,
            intent=l1.intent, emotion=l1.emotion,
            confidence=l1.confidence,
            latency_ms=int((time.time()-t0)*1000),
            plan=l1.plan, exec_output=exec_out,
            route=l1.route, model_used=l1.model_used,
        )

    # ── Helpers ───────────────────────────────────────────────────

    def _code_action(self, intent: str, text: str) -> str:
        tl = text.lower()
        if "explain" in tl or "what does" in tl: return "explain"
        if "review"  in tl or "check"    in tl: return "review"
        if "fix"     in tl or "bug"      in tl: return "fix"
        if "refactor"in tl or "clean up" in tl: return "refactor"
        if "test"    in tl:                      return "test"
        if "document"in tl or "docstring"in tl: return "docs"
        return "explain"

    def _extract_code(self, text: str) -> str:
        m = re.search(r"```\w*\n?(.*?)```", text, re.DOTALL)
        return m.group(1).strip() if m else text

    def _infer_lang(self, text: str) -> str:
        for lang in ["python","dart","javascript","typescript",
                      "java","kotlin","go","rust","cpp"]:
            if lang in text.lower():
                return lang
        return "python"

    async def _dispatch_ctrl(self, l1, text: str):
        tl = text.lower()

        # Vision task — "do X on screen / automate / go to website and..."
        if any(k in tl for k in ["on screen", "automate", "navigate to",
                                   "go to website", "click on", "open chrome",
                                   "open instagram", "open whatsapp",
                                   "search amazon", "buy ", "order "]):
            return await self._controller.execute(
                "vision_task", instruction=text)

        if any(k in tl for k in ["open ", "launch ", "start "]):
            m = re.search(r"(?:open|launch|start)\s+(\w+)", tl)
            app = m.group(1) if m else "chrome"
            return await self._controller.execute("app_open", app=app)
        if "screenshot" in tl:
            return await self._controller.execute("android_screenshot")
        if "battery" in tl:
            return await self._controller.execute("android_battery")
        if any(k in tl for k in ["http://", "https://"]):
            m = re.search(r"(https?://\S+)", text)
            if m:
                return await self._controller.execute(
                    "browser", url=m.group(1))
        if "run " in tl or "terminal" in tl:
            m = re.search(r"(?:run|execute|terminal)\s+(.+)", tl)
            if m:
                return await self._controller.execute(
                    "terminal", cmd=m.group(1).strip())
        if "read " in tl or "cat " in tl:
            m = re.search(r"(?:read|cat)\s+(\S+)", tl)
            if m:
                return await self._controller.execute(
                    "file_read", path=m.group(1))
        if "list " in tl or "ls " in tl or "dir " in tl:
            m = re.search(r"(?:list|ls|dir)\s+(\S+)?", tl)
            path = m.group(1) if m and m.group(1) else "."
            return await self._controller.execute("file_list", path=path)

        # Fallback
        class _R:
            success = True
            output  = l1.reply
            error   = ""
            duration_ms = 0
        return _R()

    def _exec_reply(self, result, fallback: str) -> str:
        from l3_executor.executor_layer import ExecStatus
        if result.status == ExecStatus.SUCCESS:
            out = result.output[:400] if result.output else ""
            return (f"Done. Completed {result.steps_done} steps."
                    + (f"\n{out}" if out else ""))
        if result.status == ExecStatus.PARTIAL:
            return (f"Partial: {result.steps_done}/"
                    f"{result.steps_total} steps done. "
                    f"Issue: {result.error[:150]}")
        if result.status == ExecStatus.BLOCKED:
            return f"Blocked for safety: {result.error}"
        return fallback or f"Failed: {result.error[:150]}"
