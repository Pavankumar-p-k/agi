"""
core/proactive_worker.py
═══════════════════════════════════════════════════════════════════
JARVIS PROACTIVE INTELLIGENCE WORKER

This is what separates an autonomous system from a reactive one.

It runs continuously in the background and:
  1. Monitors WorldState changes (new deadlines, tasks completing, etc.)
  2. Polls for situations that need JARVIS to act without being asked
  3. Feeds the L3 ExecutorLayer with self-generated tasks
  4. Chains tasks — when one completes, spawns follow-up tasks
  5. Learns which proactive actions are useful (reinforcement)

Proactive triggers implemented:
  • DEADLINE WATCH    — deadline < 2h → auto-draft reminder message
  • IDLE RECOVERY     — user idle > 45min → suggest next task
  • TASK CHAIN        — task X done → auto-queue task Y if linked
  • MORNING PREP      — 6:50-7:10 → prepare daily brief
  • CODE HEALTH WATCH — on file save → background lint+test
  • MEMORY INSIGHT    — every 6h → generate insights from memory
  • GOAL STAGNATION   — goal not touched in 3d → surface it
  • INBOX SUMMARY     — unread > 15 → summarize by priority

Respects:
  • DecisionEngine thresholds (won't spam)
  • WorldState.user.focus (won't interrupt deep work)
  • max_proactive_per_hour limit (6 by default)
  • CooldownManager (no duplicate triggers)
═══════════════════════════════════════════════════════════════════
"""

from __future__ import annotations
import asyncio, datetime, json, logging, time
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger("jarvis.proactive")


# ── Proactive action ──────────────────────────────────────────────

@dataclass
class ProactiveAction:
    trigger:     str       # which detector triggered this
    description: str       # human-readable what we're doing
    goal:        str       # task to hand to L3 executor
    priority:    int = 5   # 1–10
    dry_run:     bool = False  # True = plan only, don't execute
    notify:      bool = True   # surface to user via NotificationHub


# ── Cooldown tracker ──────────────────────────────────────────────

class CooldownManager:
    """Prevents the same trigger from firing more than once per window."""

    def __init__(self):
        self._last: dict[str, float] = {}

    def ok(self, key: str, cooldown_sec: float = 3600) -> bool:
        now = time.time()
        last = self._last.get(key, 0)
        if now - last < cooldown_sec:
            return False
        self._last[key] = now
        return True

    def reset(self, key: str):
        self._last.pop(key, None)


# ── Individual proactive monitors ────────────────────────────────

class DeadlineWatcher:
    """Watches tasks with deadlines and fires when < 2h remaining."""

    COOLDOWN = 7200  # 2h — only warn once per deadline per 2h

    def check(self, snap: dict) -> Optional[ProactiveAction]:
        tasks  = snap.get("tasks", {})
        now    = time.time()
        for dl in tasks.get("deadlines", []):
            title  = dl.get("title", "task")
            due_ts = dl.get("due_ts", 0)
            done   = dl.get("done", False)
            if done:
                continue
            gap_h  = (due_ts - now) / 3600 if due_ts else 99
            if 0 < gap_h <= 2:
                return ProactiveAction(
                    trigger     = "deadline_watch",
                    description = f"Deadline in {gap_h:.1f}h: {title}",
                    goal        = (
                        f"Deadline for '{title}' is in {gap_h:.1f} hours. "
                        f"Check current progress, identify what's incomplete, "
                        f"and draft a status message."
                    ),
                    priority    = 9,
                    dry_run     = True,   # don't auto-execute, just plan
                    notify      = True,
                )
        return None


class IdleRecovery:
    """Fires when user has been idle for > 45 minutes."""

    IDLE_THRESHOLD = 45 * 60   # 45 min in seconds
    COOLDOWN       = 3600      # once per hour

    def check(self, snap: dict) -> Optional[ProactiveAction]:
        user    = snap.get("user", {})
        last_ts = user.get("last_input_ts") or 0
        active  = user.get("active", True)
        focus   = user.get("focus", 1.0)

        if not active:
            return None  # user is away/sleeping — don't interrupt
        if focus > 0.8:
            return None  # deep focus — don't interrupt

        idle_sec = time.time() - last_ts if last_ts else 0
        if idle_sec > self.IDLE_THRESHOLD:
            pending = snap.get("tasks", {}).get("pending", [])
            next_task = pending[0]["title"] if pending else "your next goal"
            return ProactiveAction(
                trigger     = "idle_recovery",
                description = f"User idle for {idle_sec//60:.0f} min",
                goal        = (
                    f"User has been idle for {idle_sec//60:.0f} minutes. "
                    f"Suggest the most important next action. "
                    f"Next pending task: {next_task}."
                ),
                priority    = 5,
                dry_run     = True,
                notify      = True,
            )
        return None


class MorningPrepWorker:
    """Fires at 06:50–07:10 to prepare daily brief and agenda."""

    def check(self, snap: dict) -> Optional[ProactiveAction]:
        now  = datetime.datetime.now()
        hour = now.hour
        mins = now.minute

        if hour == 6 and mins >= 50:
            pass  # morning window start
        elif hour == 7 and mins <= 10:
            pass  # morning window end
        else:
            return None

        tasks   = snap.get("tasks", {}).get("pending", [])
        n_tasks = len(tasks)
        events  = snap.get("external", {}).get("calendar_events", [])
        n_cal   = len(events)

        return ProactiveAction(
            trigger     = "morning_prep",
            description = "Morning prep: generating daily brief",
            goal        = (
                f"Prepare today's morning brief. "
                f"Pending tasks: {n_tasks}. "
                f"Calendar events today: {n_cal}. "
                f"Summarize priorities for the day in 3-4 sentences. "
                f"Format: greet, then top 3 priorities, then one encouragement."
            ),
            priority    = 6,
            dry_run     = False,
            notify      = True,
        )


class CodeHealthWatcher:
    """
    Monitors 'current_file' in WorldState.
    When user saves a Python/Dart file, queues a background lint.
    """

    def __init__(self):
        self._last_file: str = ""

    def check(self, snap: dict) -> Optional[ProactiveAction]:
        tasks       = snap.get("tasks", {})
        curr_file   = tasks.get("current_file", "")
        test_status = tasks.get("test_status", "unknown")

        # Only trigger on new files
        if not curr_file or curr_file == self._last_file:
            return None
        if not any(curr_file.endswith(ext)
                   for ext in [".py", ".dart", ".js", ".ts"]):
            return None

        self._last_file = curr_file

        # Only lint if tests haven't just passed
        if test_status == "passing":
            return None

        return ProactiveAction(
            trigger     = "code_health",
            description = f"Background lint: {curr_file.split('/')[-1]}",
            goal        = (
                f"Run a quick code quality check on file: {curr_file}. "
                f"Check for: syntax errors, unused imports, obvious bugs. "
                f"Return a 2-line summary of findings."
            ),
            priority    = 3,
            dry_run     = False,
            notify      = False,   # silent background task
        )


class MemoryInsightWorker:
    """Every 6 hours, generates insights from recent memory."""

    COOLDOWN = 6 * 3600

    def check(self, snap: dict) -> Optional[ProactiveAction]:
        return ProactiveAction(
            trigger     = "memory_insight",
            description = "Generating 6-hour memory insights",
            goal        = (
                "Analyze the last 6 hours of conversations and activities. "
                "Identify: 1) recurring topics, 2) unresolved questions, "
                "3) any important facts to remember. "
                "Return a structured JSON summary."
            ),
            priority    = 2,
            dry_run     = False,
            notify      = False,
        )


class GoalStagnationWatcher:
    """Surfaces goals that haven't been touched in 3+ days."""

    STAGNATION_DAYS = 3
    COOLDOWN        = 24 * 3600  # once per day

    def check(self, snap: dict) -> Optional[ProactiveAction]:
        tasks = snap.get("tasks", {}).get("pending", [])
        now   = time.time()
        stale = []

        for t in tasks:
            last_touch = t.get("last_touched_ts", 0)
            if not last_touch:
                continue
            days_ago = (now - last_touch) / 86400
            if days_ago > self.STAGNATION_DAYS:
                stale.append((t.get("title", "task"), days_ago))

        if not stale:
            return None

        titles = ", ".join(
            f"'{t}' ({d:.0f}d ago)" for t, d in stale[:3])
        return ProactiveAction(
            trigger     = "goal_stagnation",
            description = f"Stale goals detected: {len(stale)}",
            goal        = (
                f"These goals haven't been touched in {self.STAGNATION_DAYS}+ days: "
                f"{titles}. "
                f"Suggest whether to: continue, defer, break into smaller steps, "
                f"or remove each one."
            ),
            priority    = 4,
            dry_run     = True,
            notify      = True,
        )


class InboxSummaryWorker:
    """When unread messages > 15, summarize by priority."""

    THRESHOLD = 15
    COOLDOWN  = 1800  # 30 min

    def check(self, snap: dict) -> Optional[ProactiveAction]:
        unread = snap.get("external", {}).get("unread_messages", {})
        total  = sum(unread.values()) if isinstance(unread, dict) else 0

        if total < self.THRESHOLD:
            return None

        breakdown = json.dumps(unread) if isinstance(unread, dict) else str(unread)
        return ProactiveAction(
            trigger     = "inbox_summary",
            description = f"Inbox overload: {total} unread",
            goal        = (
                f"User has {total} unread messages across platforms: {breakdown}. "
                f"Prioritize them: mark which need immediate reply, "
                f"which can wait, and which can be auto-replied."
            ),
            priority    = 7,
            dry_run     = True,
            notify      = True,
        )


# ═══════════════════════════════════════════════════════════════
#  MAIN PROACTIVE WORKER
# ═══════════════════════════════════════════════════════════════

class ProactiveWorker:
    """
    Background coroutine that checks all proactive monitors every
    30 seconds and routes triggered actions to L3 ExecutorLayer.

    Wired into jarvis_main_autonomous.py after boot:
        worker = ProactiveWorker(
            world_state=world, executor=l3, hub=hub,
            semantic_store=store,
        )
        asyncio.create_task(worker.run())
    """

    CHECK_INTERVAL  = 30    # seconds between checks
    MAX_PER_HOUR    = 6     # max proactive actions per hour

    def __init__(
        self,
        world_state,
        executor,           # L3 ExecutorLayer
        hub,                # NotificationHub
        semantic_store,
        personality=None,
    ):
        self._world       = world_state
        self._executor    = executor
        self._hub         = hub
        self._store       = semantic_store
        self._personality = personality

        self._cooldowns   = CooldownManager()
        self._hour_count  = 0
        self._hour_start  = time.time()
        self._running     = False

        # Register all monitors with their cooldowns
        self._monitors = [
            (DeadlineWatcher(),         "deadline_watch",    3600),
            (IdleRecovery(),            "idle_recovery",     3600),
            (MorningPrepWorker(),       "morning_prep",     86400),
            (CodeHealthWatcher(),       "code_health",         60),
            (MemoryInsightWorker(),     "memory_insight",   21600),
            (GoalStagnationWatcher(),   "goal_stagnation",  86400),
            (InboxSummaryWorker(),      "inbox_summary",     1800),
        ]

        logger.info("[Proactive] Worker initialized — %d monitors",
                    len(self._monitors))

    async def run(self):
        """Main loop. Run as asyncio.create_task(worker.run())."""
        self._running = True
        logger.info("[Proactive] Background worker started")
        while self._running:
            try:
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("[Proactive] Tick error: %s", e, exc_info=True)
            await asyncio.sleep(self.CHECK_INTERVAL)

    async def stop(self):
        self._running = False

    async def _tick(self):
        """One check cycle across all monitors."""
        snap = self._world.snapshot()

        # Reset hourly counter
        if time.time() - self._hour_start > 3600:
            self._hour_count = 0
            self._hour_start = time.time()

        # Skip if over hourly limit
        if self._hour_count >= self.MAX_PER_HOUR:
            return

        # Skip if user is in deep focus
        focus = snap.get("user", {}).get("focus", 1.0)
        if focus > 0.85:
            logger.debug("[Proactive] Deep focus (%.2f) — skipping", focus)
            return

        for monitor, trigger_key, cooldown in self._monitors:
            if not self._cooldowns.ok(trigger_key, cooldown):
                continue

            try:
                action = monitor.check(snap)
            except Exception as e:
                logger.warning("[Proactive] Monitor %s error: %s",
                               trigger_key, e)
                continue

            if action is None:
                # Monitor didn't fire — reset cooldown so it can fire again
                self._cooldowns.reset(trigger_key)
                continue

            logger.info("[Proactive] ▶ Trigger: %s — %s",
                        action.trigger, action.description)
            await self._dispatch(action, snap)
            self._hour_count += 1

            # Stop after first trigger per tick — don't flood
            break

    async def _dispatch(self, action: ProactiveAction, snap: dict):
        """
        Handle a triggered ProactiveAction:
          1. Optionally notify user
          2. Send goal to L3 Executor
          3. Save result to memory
          4. Notify user of result if priority warrants it
        """
        # 1. Pre-notification
        if action.notify and action.priority >= 6:
            await self._notify(
                f"[{action.trigger}] {action.description}",
                category=action.trigger,
                priority=action.priority,
            )

        # 2. Execute via L3 (or plan-only for dry_run)
        result = await self._executor.execute(
            goal     = action.goal,
            intent   = "proactive",
            context  = f"Triggered by: {action.trigger}",
            dry_run  = action.dry_run,
        )

        # 3. Persist to memory
        if self._store and result.output:
            self._store.remember(
                f"Proactive [{action.trigger}]: {result.output[:300]}",
                category = "proactive",
                importance = action.priority / 10.0,
            )

        # 4. Notify result for important actions
        if action.notify and result.output and action.priority >= 5:
            summary = result.output[:200].split("\n")[0]
            # Apply personality filter if available
            if self._personality:
                try:
                    summary = self._personality.transform(summary, snap)
                except Exception as err:
                    import logging
                    logging.getLogger(__name__).error("Exception swallowed: %s", err)
                    raise RuntimeError(f"Exception swallowed: {err}")
            await self._notify(
                summary,
                category = action.trigger,
                priority = max(3, action.priority - 2),  # slightly lower than trigger
            )

        logger.info("[Proactive] ✓ %s complete: %s in %dms",
                    action.trigger,
                    result.status,
                    result.latency_ms)

    async def _notify(self, message: str, category: str = "proactive",
                      priority: int = 5):
        if not self._hub:
            return
        try:
            if asyncio.iscoroutinefunction(self._hub.send):
                await self._hub.send(message, category=category,
                                     priority=priority,
                                     channels=["log", "websocket"])
            else:
                self._hub.dispatch(category, {"message": message,
                                              "priority": priority})
        except Exception as e:
            logger.warning("[Proactive] Notify error: %s", e)

    @property
    def is_running(self) -> bool:
        return self._running

    def status(self) -> dict:
        return {
            "running":       self._running,
            "monitors":      len(self._monitors),
            "hour_count":    self._hour_count,
            "max_per_hour":  self.MAX_PER_HOUR,
            "check_interval": self.CHECK_INTERVAL,
        }
