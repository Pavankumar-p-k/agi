"""
patches/world_state_patch.py
═══════════════════════════════════════════════════════════════════
Monkey-patches WorldState to add the .update() convenience method
that the new autonomous layers use.

Also patches SemanticStore to ensure .recall() and .retrieve() are
both available (they are, per semantic_store.py GAP 16, but this
confirms it at runtime).

Import this ONCE at the top of jarvis_main_autonomous.py
(already done — it calls apply_injections() on startup).

Does NOT modify any original file.
"""
from __future__ import annotations
import logging

logger = logging.getLogger("jarvis.patches")


def apply_injections():
    """Call once at startup. Idempotent — safe to call multiple times."""
    _inject_world_state()
    _inject_semantic_store()
    _inject_notification_hub()
    logger.info("[Patches] All compatibility patches applied ✓")


# ── WorldState.update() ───────────────────────────────────────────

def _inject_world_state():
    """
    Adds .update(bucket, **kwargs) convenience method.
    Brain layer calls:
        world.update("user", last_input_ts=..., last_voice_input=...)
    But WorldState only has .update_user_state(**kwargs).
    """
    try:
        from core.world_state import WorldState

        if hasattr(WorldState, "_patched_update"):
            return

        def update(self, bucket: str, **kwargs):
            """
            Convenience: world.update("user", focus=0.8)
            Dispatches to the correct typed updater.
            """
            dispatch = {
                "user":     self.update_user_state,
                "tasks":    self.update_task_state,
                "external": self.update_external_state,
                "system":   self.update_system_state,
            }
            fn = dispatch.get(bucket)
            if fn:
                fn(**kwargs)
            else:
                # Fallback — update user state
                self.update_user_state(**kwargs)

        WorldState.update         = update
        WorldState._patched_update = True
        logger.debug("[Patches] WorldState.update() added")

    except ImportError as e:
        logger.warning("[Patches] WorldState patch skipped: %s", e)


# ── SemanticStore method aliases ──────────────────────────────────

def _inject_semantic_store():
    """
    Ensures both .recall() and .retrieve() exist (they do per GAP 16
    but we verify at runtime and add cross-aliases just in case).
    Also adds .search() alias used by some modules.
    """
    try:
        from jarvis_os.memory.memory_manager import MemoryManager

        if hasattr(SemanticStore, "_patched_aliases"):
            return

        # Add .search() → .recall() alias
        if not hasattr(SemanticStore, "search"):
            SemanticStore.search = SemanticStore.recall

        # Ensure .retrieve() exists (alias to recall)
        if not hasattr(SemanticStore, "retrieve"):
            SemanticStore.retrieve = SemanticStore.recall

        # Ensure .remember() exists (alias to store)
        if not hasattr(SemanticStore, "remember"):
            SemanticStore.remember = SemanticStore.store

        SemanticStore._patched_aliases = True
        logger.debug("[Patches] SemanticStore aliases added")

    except ImportError as e:
        logger.warning("[Patches] SemanticStore patch skipped: %s", e)


# ── NotificationHub.dispatch() sync wrapper ───────────────────────

def _inject_notification_hub():
    """
    CognitiveCore's _dispatcher is called as a sync function:
        self._dispatcher(category, payload)
    But NotificationHub.send() is async.

    Adds a sync .dispatch() that creates an asyncio task.
    """
    try:
        from notifications.notification_hub import NotificationHub
        import asyncio

        if hasattr(NotificationHub, "_patched_dispatch"):
            return

        def route_event(self, category: str, payload: dict) -> None:
            """
            Sync dispatcher called by CognitiveCore._dispatcher.
            Creates an asyncio task for the async send().
            """
            body      = payload.get("message", str(payload)[:120])
            priority  = payload.get("priority", 5)
            ui_alert  = payload.get("ui_alert", False)
            channels  = ["log", "tts"]
            if ui_alert:
                channels.append("websocket")
            if priority >= 9:
                channels.extend(["desktop", "android"])

            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(
                        self.send(body, category=category,
                                  priority=priority, channels=channels)
                    )
                else:
                    loop.run_until_complete(
                        self.send(body, category=category,
                                  priority=priority, channels=channels)
                    )
            except Exception as e:
                logger.warning("[Hub.route_event] Failed: %s", e)

        NotificationHub.dispatch         = route_event
        NotificationHub._patched_dispatch = True
        logger.debug("[Patches] NotificationHub.dispatch() added")

    except ImportError as e:
        logger.warning("[Patches] NotificationHub patch skipped: %s", e)
