# core/agi_core.py
#
# ╔══════════════════════════════════════════════════════════════╗
# ║          J.A.R.V.I.S  —  AGI BRAIN v1.0                    ║
# ║  Autonomous General Intelligence Layer                       ║
# ╠══════════════════════════════════════════════════════════════╣
# ║  What makes this AGI (not just AI):                          ║
# ║                                                              ║
# ║  1. AUTONOMOUS DECISIONS  — acts without being asked         ║
# ║  2. PATTERN LEARNING      — learns YOUR habits over time     ║
# ║  3. PREDICTION ENGINE     — predicts what you'll need next   ║
# ║  4. PROBLEM SOLVING       — breaks problems into steps       ║
# ║  5. SELF-IMPROVEMENT      — reflects & improves its prompts  ║
# ║  6. TOOL ACCESS           — can call any JARVIS function     ║
# ║  7. GOAL PURSUIT          — pursues multi-step goals alone   ║
# ║  8. CONTEXT AWARENESS     — time, mood, habits, location     ║
# ╚══════════════════════════════════════════════════════════════╝
#
# AGI Loop (runs every 30 seconds in background):
#
#   Observe World State
#         ↓
#   Pattern Recognition → "Pavan usually listens to music at 9pm"
#         ↓
#   Predict Needs → "It's 9pm → suggest/play music"
#         ↓
#   Decide Action → Goal Planner selects best action
#         ↓
#   Execute Action → calls JARVIS tools
#         ↓
#   Learn from Result → was it good? store outcome
#         ↓
#   Self-Reflect → improve decision weights
#         ↓
#   Sleep 30s → repeat

import asyncio
import time
import json
import random
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from pathlib import Path
from dataclasses import dataclass, field, asdict

from learning.pattern_engine  import PatternEngine
from learning.habit_tracker   import HabitTracker
from learning.style_engine    import MessageStyleEngine
from prediction.predictor     import PredictionEngine
from decision.goal_planner    import GoalPlanner
from decision.action_executor import ActionExecutor
from problem_solver.solver    import ProblemSolver
from self_improve.reflector   import SelfReflector
from memory.agi_memory        import AGIMemory
from tools.jarvis_tools       import JarvisTools


# ── Types ────────────────────────────────────────────────────

@dataclass
class WorldState:
    timestamp:    float    = field(default_factory=time.time)
    hour:         int      = 0
    day_of_week:  int      = 0   # 0=Mon
    is_weekend:   bool     = False
    recent_intents: list   = field(default_factory=list)  # last 10 user intents
    active_apps:  list     = field(default_factory=list)
    last_command: str      = ""
    pavan_mood:   str      = "neutral"
    battery_pct:  int      = 100
    is_home:      bool     = True
    pending_reminders: int = 0
    unread_messages:   int = 0

@dataclass
class AGIDecision:
    action:        str
    tool:          str
    params:        dict
    reasoning:     str
    confidence:    float
    priority:      int         # 1=urgent, 2=high, 3=normal, 4=low
    autonomous:    bool = True  # True = JARVIS decided this itself
    goal_id:       str  = ""


@dataclass
class Goal:
    id:          str
    description: str
    steps:       list
    current_step: int = 0
    status:      str = "active"    # active / done / failed / paused
    created_at:  float = field(default_factory=time.time)
    context:     dict = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────

class JarvisAGI:
    """
    The AGI Core — autonomous intelligence layer.
    Wraps the multi-agent brain and adds:
    - autonomous decision making
    - pattern learning from user behavior
    - predictive assistance
    - self-directed goal pursuit
    - self-improvement loop
    """

    def __init__(self):
        print("\n" + "=" * 58)
        print("  J.A.R.V.I.S AGI BRAIN - Initializing...")
        print("=" * 58)

        self.memory        = AGIMemory()
        self.patterns      = PatternEngine(self.memory)
        self.habits        = HabitTracker(self.memory)
        self.style         = MessageStyleEngine(self.memory)
        self.predictor     = PredictionEngine(self.patterns, self.habits)
        self.goal_planner  = GoalPlanner(self.memory)
        self.executor      = ActionExecutor()
        self.solver        = ProblemSolver()
        self.reflector     = SelfReflector(self.memory)
        self.tools         = JarvisTools()

        self._goals: List[Goal]         = []
        self._decision_history: List[dict] = []
        self._world_state              = WorldState()
        self._running                  = False
        self._loop_task                = None
        self._loop_count               = 0
        self._autonomous_enabled       = True
        self._confidence_threshold     = 0.65   # only act if confidence > this
        self._auto_message_count       = 0
        self._call_config = {
            "auto_lift_enabled": False,
            "auto_lift_start_hour": 9,
            "auto_lift_end_hour": 18,
            "auto_lift_all": False,
            "auto_busy_reply": True,
            "busy_reply_template": "Sir is busy right now. You can leave a note or reminder.",
            "lift_script_template": "Hello. This is JARVIS assistant for Sir. Please share your message.",
            "create_callback_reminder": True,
        }

        print("  [OK] All AGI modules loaded")
        print("=" * 58 + "\n")

    # ═══════════════════════════════════════════════════════
    #  STARTUP & MAIN LOOP
    # ═══════════════════════════════════════════════════════

    async def start(self):
        """Start AGI background loop."""
        if self._running:
            return
        self._running = True
        print("[AGI] Background loop started [OK]")
        self._loop_task = asyncio.create_task(self._agi_loop())

    async def stop(self):
        if not self._running:
            return
        self._running = False
        if self._loop_task:
            self._loop_task.cancel()
            self._loop_task = None
        print("[AGI] Stopped")

    async def _agi_loop(self):
        """
        Main AGI loop — runs every 30 seconds.
        Observes → Learns → Predicts → Decides → Acts → Reflects.
        """
        while self._running:
            try:
                self._loop_count += 1
                loop_start = time.time()

                # ── 1. Observe world state ──────────────────
                state = await self._observe()

                # ── 2. Learn from recent events ─────────────
                await self.patterns.learn_from_state(state)
                await self.habits.update(state)

                # ── 3. Check active goals ────────────────────
                if self._goals:
                    await self._advance_goals(state)

                # ── 4. Predict what Pavan needs ──────────────
                if self._autonomous_enabled:
                    predictions = await self.predictor.predict(state)

                    for pred in predictions:
                        if pred["confidence"] >= self._confidence_threshold:
                            decision = await self.goal_planner.make_decision(
                                prediction=pred,
                                state=state,
                                history=self._decision_history[-20:],
                            )
                            if decision:
                                await self._execute_decision(decision, state)

                # ── 5. Self-reflect every 10 loops ──────────
                if self._loop_count % 10 == 0:
                    await self.reflector.reflect(
                        decisions=self._decision_history[-50:],
                        state=state,
                    )

                loop_ms = int((time.time() - loop_start) * 1000)
                print(f"[AGI] Loop #{self._loop_count} done in {loop_ms}ms")

            except Exception as e:
                print(f"[AGI] Loop error: {e}")

            await asyncio.sleep(30)   # check every 30 seconds

    # ═══════════════════════════════════════════════════════
    #  WORLD STATE OBSERVATION
    # ═══════════════════════════════════════════════════════

    async def _observe(self) -> WorldState:
        """Collect current state of the world."""
        now = datetime.now()
        recent = await self.memory.get_recent_events(n=10)

        state = WorldState(
            timestamp   = time.time(),
            hour        = now.hour,
            day_of_week = now.weekday(),
            is_weekend  = now.weekday() >= 5,
            last_command = recent[0]["content"] if recent else "",
            recent_intents = [r.get("intent","") for r in recent],
            pavan_mood  = await self.memory.get_latest_mood(),
            pending_reminders = await self.tools.count_pending_reminders(),
            unread_messages   = await self.tools.count_unread_messages(),
        )
        self._world_state = state
        return state

    # ═══════════════════════════════════════════════════════
    #  DECISION EXECUTION
    # ═══════════════════════════════════════════════════════

    async def _execute_decision(self, decision: AGIDecision, state: WorldState):
        """Execute a decision and record the outcome."""
        print(f"[AGI] Autonomous action: {decision.action}")
        print(f"[AGI]    Reason: {decision.reasoning}")
        print(f"[AGI]    Confidence: {decision.confidence:.2f}")

        t0 = time.time()
        try:
            result = await self.executor.execute(decision, self.tools)
            success = result.get("success", False)
            latency_ms = int((time.time() - t0) * 1000)

            # Record for learning
            record = {
                "timestamp":  time.time(),
                "action":     decision.action,
                "tool":       decision.tool,
                "reasoning":  decision.reasoning,
                "confidence": decision.confidence,
                "success":    success,
                "latency_ms": latency_ms,
                "state_hour": state.hour,
                "state_mood": state.pavan_mood,
            }
            self._decision_history.append(record)
            await self.memory.save_decision(record)

            print(f"[AGI]    Result: {'success' if success else 'failed'} ({latency_ms}ms)")

        except Exception as e:
            print(f"[AGI]    Execution error: {e}")

    # ═══════════════════════════════════════════════════════
    #  GOAL MANAGEMENT
    # ═══════════════════════════════════════════════════════

    async def set_goal(self, description: str, context: dict = None) -> str:
        """
        Give JARVIS a high-level goal to pursue autonomously.
        JARVIS will break it into steps and execute them over time.

        e.g. "Organize my notes by topic"
             "Remind me about my meeting prep every day this week"
             "Send Rahul a message every morning this week"
        """
        print(f"[AGI] New goal: {description}")

        # Use solver to break into steps
        steps = await self.solver.decompose(description, context or {})
        goal_id = f"goal_{int(time.time())}"

        goal = Goal(
            id=goal_id,
            description=description,
            steps=steps,
            context=context or {},
        )
        self._goals.append(goal)
        await self.memory.save_goal(asdict(goal))

        print(f"[AGI] Goal '{goal_id}' created with {len(steps)} steps")
        return goal_id

    async def _advance_goals(self, state: WorldState):
        """Try to advance each active goal by one step."""
        for goal in self._goals:
            if goal.status != "active": continue
            if goal.current_step >= len(goal.steps): 
                goal.status = "done"
                print(f"[AGI] Goal completed: {goal.description}")
                continue

            step = goal.steps[goal.current_step]
            print(f"[AGI] Advancing goal '{goal.description[:40]}' step {goal.current_step+1}/{len(goal.steps)}")

            try:
                decision = await self.goal_planner.step_to_decision(step, goal, state)
                if decision:
                    await self._execute_decision(decision, state)
                    goal.current_step += 1
                    await self.memory.update_goal(goal.id, goal.current_step, goal.status)
            except Exception as e:
                print(f"[AGI] Goal step failed: {e}")
                goal.status = "failed"

    # ═══════════════════════════════════════════════════════
    #  PROBLEM SOLVING (interactive)
    # ═══════════════════════════════════════════════════════

    async def solve(self, problem: str, context: dict = None) -> dict:
        """
        Solve a complex problem step by step.
        Returns full solution plan + execution results.
        """
        print(f"[AGI] Solving: {problem}")
        return await self.solver.solve(
            problem=problem,
            context=context or {},
            tools=self.tools,
            memory=self.memory,
        )

    # ═══════════════════════════════════════════════════════
    #  REACT TO USER INPUT (called by main chat pipeline)
    # ═══════════════════════════════════════════════════════

    async def on_user_input(self, text: str, intent: str, emotion: str, user_id: str = "pavan"):
        """
        Called every time Pavan says something.
        AGI learns from this and may decide to act proactively.
        """
        event = {
            "type":      "user_input",
            "content":   text,
            "intent":    intent,
            "emotion":   emotion,
            "user_id":   user_id,
            "timestamp": time.time(),
            "hour":      datetime.now().hour,
            "day":       datetime.now().weekday(),
        }
        await self.memory.save_event(event)
        await self.patterns.observe(event)
        await self.habits.observe(event)
        await self.style.observe(event)

        # If emotion is negative → proactively offer help
        if emotion in ("sad", "angry", "frustrated", "anxious"):
            asyncio.create_task(self._proactive_support(emotion, text))

    async def _proactive_support(self, emotion: str, trigger: str):
        """JARVIS proactively offers support when mood is negative."""
        await asyncio.sleep(2)   # small delay before offering
        support_messages = {
            "sad":         "I noticed you seem a bit down. Want me to play some uplifting music or is there anything I can help with?",
            "angry":       "It sounds like something's frustrating you. I can help you think it through or just give you some space.",
            "frustrated":  "Frustrating situation. Want me to help break it down step by step?",
            "anxious":     "Everything's going to be okay. Want me to run through your tasks so we can prioritize?",
        }
        msg = support_messages.get(emotion)
        if msg:
            await self.tools.speak(msg)
            print(f"[AGI] Proactive support offered for emotion: {emotion}")

    def set_call_config(self, config: dict[str, Any]) -> dict[str, Any]:
        for k, v in (config or {}).items():
            if k in self._call_config:
                self._call_config[k] = v
        self._call_config["auto_lift_start_hour"] = int(self._call_config["auto_lift_start_hour"]) % 24
        self._call_config["auto_lift_end_hour"] = int(self._call_config["auto_lift_end_hour"]) % 24
        return dict(self._call_config)

    def _in_auto_lift_window(self, hour: int) -> bool:
        start = int(self._call_config["auto_lift_start_hour"])
        end = int(self._call_config["auto_lift_end_hour"])
        if start == end:
            return True
        if start < end:
            return start <= hour <= end
        return hour >= start or hour < end

    async def handle_incoming_call(
        self,
        caller_name: str,
        relation: str = "",
        phone: str = "",
        allow_auto_actions: bool = False,
    ) -> dict[str, Any]:
        caller = (caller_name or "Unknown caller").strip()
        rel = (relation or "").strip().lower()
        now = datetime.now()
        hour = now.hour

        family_relations = {"mother", "mom", "father", "dad", "wife", "husband", "sister", "brother"}
        high_priority = rel in family_relations

        if rel in {"mother", "mom"}:
            announce = (
                "Sir, your mother is calling. Tell me what to do: lift for you, "
                "or respond that you are busy and can call back?"
            )
        else:
            relation_label = relation.strip() if relation else "contact"
            announce = (
                f"Sir, {caller} is calling ({relation_label}). Tell me: lift now, "
                "or send busy response with note request."
            )

        await self.tools.speak(announce)

        auto_lift_allowed = (
            allow_auto_actions
            and bool(self._call_config["auto_lift_enabled"])
            and self._in_auto_lift_window(hour)
            and (high_priority or bool(self._call_config["auto_lift_all"]))
        )

        action_taken = "awaiting_user_instruction"
        action_success = False
        sent_text = ""

        if auto_lift_allowed:
            script = str(self._call_config["lift_script_template"]).replace("{caller}", caller)
            action_success = await self.tools.answer_call_with_tts(caller=caller, script=script)
            action_taken = "auto_lifted" if action_success else "auto_lift_failed"
            sent_text = script
            if not action_success and bool(self._call_config["auto_busy_reply"]):
                sent_text = str(self._call_config["busy_reply_template"]).replace("{caller}", caller)
                target = phone.strip() or caller
                action_success = await self.tools.send_message(contact=target, text=sent_text, platform="call_sms")
                action_taken = "busy_reply_sent" if action_success else "busy_reply_failed"
        elif allow_auto_actions and bool(self._call_config["auto_busy_reply"]):
            sent_text = str(self._call_config["busy_reply_template"]).replace("{caller}", caller)
            target = phone.strip() or caller
            action_success = await self.tools.send_message(contact=target, text=sent_text, platform="call_sms")
            action_taken = "busy_reply_sent" if action_success else "busy_reply_failed"
            if action_success and bool(self._call_config["create_callback_reminder"]):
                await self.tools.create_reminder(title=f"Call back {caller}")

        if action_success:
            self._auto_message_count += 1
            await self.memory.save_event(
                {
                    "type": "auto_reply_sent",
                    "content": sent_text,
                    "intent": "call_assist",
                    "emotion": "neutral",
                    "user_id": "pavan",
                    "timestamp": time.time(),
                    "hour": hour,
                    "day": now.weekday(),
                }
            )

        await self.memory.save_event(
            {
                "type": "incoming_call",
                "content": json.dumps(
                    {
                        "caller": caller,
                        "relation": rel,
                        "phone": phone,
                        "action_taken": action_taken,
                    }
                ),
                "intent": "call_assist",
                "emotion": "neutral",
                "user_id": "pavan",
                "timestamp": time.time(),
                "hour": hour,
                "day": now.weekday(),
            }
        )

        return {
            "caller": caller,
            "relation": rel,
            "announcement": announce,
            "options": [
                "lift_for_me",
                "send_busy_note",
                "set_callback_reminder",
            ],
            "auto_action_allowed": allow_auto_actions,
            "action_taken": action_taken,
            "success": action_success,
            "configured_window": {
                "start_hour": self._call_config["auto_lift_start_hour"],
                "end_hour": self._call_config["auto_lift_end_hour"],
            },
        }

    async def build_styled_reply(
        self,
        incoming_text: str,
        intent: str = "small_talk",
        user_id: str = "pavan",
        contact: str = "",
        platform: str = "auto",
        auto_send: bool = False,
    ) -> dict[str, Any]:
        styled = await self.style.generate_reply(incoming_text=incoming_text, intent=intent, user_id=user_id)
        sent = False
        if auto_send and contact.strip():
            sent = await self.tools.send_message(contact=contact, text=styled["reply"], platform=platform)
            if sent:
                self._auto_message_count += 1
                now = datetime.now()
                await self.memory.save_event(
                    {
                        "type": "auto_reply_sent",
                        "content": styled["reply"],
                        "intent": intent,
                        "emotion": "neutral",
                        "user_id": user_id,
                        "timestamp": time.time(),
                        "hour": now.hour,
                        "day": now.weekday(),
                    }
                )
        return {
            **styled,
            "sent": sent,
            "contact": contact,
            "platform": platform,
        }

    async def get_work_summary(self) -> dict[str, Any]:
        auto_replies = await self.memory.count_events("auto_reply_sent")
        call_events = await self.memory.count_events("incoming_call")
        user_inputs = await self.memory.count_events("user_input")
        stats = await self.memory.get_stats()
        return {
            "auto_responses_sent": auto_replies,
            "incoming_calls_handled": call_events,
            "user_messages_observed": user_inputs,
            "decisions_made": stats.get("decisions", 0),
            "active_goals": stats.get("active_goals", 0),
        }

    # ═══════════════════════════════════════════════════════
    #  STATUS & CONTROL
    # ═══════════════════════════════════════════════════════

    def get_status(self) -> dict:
        return {
            "running":              self._running,
            "loop_count":           self._loop_count,
            "autonomous_enabled":   self._autonomous_enabled,
            "confidence_threshold": self._confidence_threshold,
            "active_goals":         len([g for g in self._goals if g.status=="active"]),
            "total_goals":          len(self._goals),
            "decisions_made":       len(self._decision_history),
            "world_state": {
                "hour":     self._world_state.hour,
                "mood":     self._world_state.pavan_mood,
                "weekend":  self._world_state.is_weekend,
            },
            "auto_messages_sent": self._auto_message_count,
            "call_assistant": {
                "auto_lift_enabled": self._call_config["auto_lift_enabled"],
                "auto_lift_start_hour": self._call_config["auto_lift_start_hour"],
                "auto_lift_end_hour": self._call_config["auto_lift_end_hour"],
            },
        }

    def set_confidence_threshold(self, threshold: float):
        self._confidence_threshold = max(0.1, min(1.0, threshold))
        print(f"[AGI] Confidence threshold set to {self._confidence_threshold}")

    def toggle_autonomous(self, enabled: bool):
        self._autonomous_enabled = enabled
        print(f"[AGI] Autonomous mode: {'ON' if enabled else 'OFF'}")

    def get_goals(self) -> list:
        return [asdict(g) for g in self._goals]

    def get_decision_history(self, n: int = 20) -> list:
        return self._decision_history[-n:]


# ── Singleton ────────────────────────────────────────────────
_agi: Optional[JarvisAGI] = None

def get_agi() -> JarvisAGI:
    global _agi
    if _agi is None:
        _agi = JarvisAGI()
    return _agi
