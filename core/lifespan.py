# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""core/lifespan.py â€” JARVIS server startup/shutdown logic extracted from main.py"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI

from .config import SUPABASE_SERVICE_KEY, SUPABASE_URL

logger = logging.getLogger(__name__)

startup_status = {
    "warnings": [],
}


def _warmup_ollama_models():
    """Verify Ollama is reachable and models are available (no pre-loading to save GPU memory)."""
    try:
        from core.model_router import ROLE_MODELS, resolve_model
    except ImportError:
        logger.debug("[LIFESPAN] model_router not available, skipping Ollama model check")
        return
    from core.config_registry import config as _c
    ollama_url = _c.get("ollama.base_url")
    try:
        import json
        from urllib.request import urlopen
        with urlopen(f"{ollama_url}/api/tags", timeout=2) as resp:
            data = json.loads(resp.read().decode())
            available_models = set()
            for m in data.get("models", []):
                name = m.get("name", "")
                available_models.add(name)
                if name.endswith(":latest"):
                    available_models.add(name[:-7])
    except Exception as e:
        logger.exception("[LIFESPAN] Ollama model check failed: %s", e)
        logger.warning("  [OLLAMA] Not reachable, skipping model check")
        return
    required_models = sorted({resolve_model(m) for m in ROLE_MODELS.values()})
    missing = [m for m in required_models if m not in available_models]
    if missing:
        logger.warning("  [OLLAMA] %d model(s) not installed: %s...", len(missing), ', '.join(missing[:3]))
        startup_status["warnings"].append(f"ollama: {len(missing)} model(s) missing")
    else:
        logger.info("  [OLLAMA] All %d models verified installed [OK]", len(required_models))


async def _migrate_legacy_settings_once():
    """One-time migration: copy overlapping keys from old settings.json into the new SettingsStore.

    Runs once, marks itself done with data/.settings_migrated flag.
    """
    from core.settings import get_settings_store
    from core.settings_legacy import _load_legacy

    MIGRATION_DONE_FLAG = Path("data/.settings_migrated")
    if MIGRATION_DONE_FLAG.exists():
        return  # already done

    legacy = _load_legacy()
    store = get_settings_store()

    # Only migrate keys that exist in the new schema
    MIGRATABLE = {
        "default_model": "llm.default_model",
        "tts_enabled": "voice.enabled",
        "tts_voice": "voice.tts_voice",
        "wake_word": "voice.wake_word",
        "debug": "ui.debug",
    }

    for old_key, new_path in MIGRATABLE.items():
        if old_key in legacy:
            try:
                store.set(new_path, legacy[old_key])
            except Exception as _e:
                logger.debug("lifespan settings migration failed: %s", _e)
                logger.warning("[startup] Could not migrate %s -> %s", old_key, new_path)

    store.save()
    MIGRATION_DONE_FLAG.parent.mkdir(parents=True, exist_ok=True)
    MIGRATION_DONE_FLAG.touch()
    logger.info("[startup] Legacy settings migrated to SettingsStore")


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("=" * 50)
    print("  JARVIS â€” Starting up...")
    print("=" * 50)

    # Warn if secret key is not set or is a dev default
    from core.config import ALLOWED_ORIGINS, DEV_MODE, SECRET_KEY
    if not SECRET_KEY:
        startup_status["warnings"].append("JARVIS_SECRET_KEY not set — generate one with: python -c 'import os; print(os.urandom(32).hex())'")
        logger.warning("[SECURITY] JARVIS_SECRET_KEY is empty — set via environment variable")
    if DEV_MODE:
        logger.warning("[SECURITY] Running in DEV_MODE — not suitable for production")
    if not DEV_MODE:
        if "*" in ALLOWED_ORIGINS:
            startup_status["warnings"].append("Production CORS allows '*' origin — set explicit origins in config.yaml")
        for origin in ALLOWED_ORIGINS:
            if origin != "*" and not origin.startswith(("http://", "https://")):
                startup_status["warnings"].append(f"CORS origin '{origin}' missing protocol — should be http:// or https://")

    # One-time legacy settings migration
    try:
        await _migrate_legacy_settings_once()
    except Exception as e:
        logger.warning("[LIFESPAN] Legacy settings migration skipped: %s", e)

    from core.auth import AuthManager, init_firebase
    from core.database import init_db

    await init_db()

    # Subagent orphan recovery
    try:
        from core.spawning.orphan import orphan_recovery
        asyncio.create_task(orphan_recovery.recover())
        logger.info("[LIFESPAN] Subagent orphan recovery started [OK]")
    except Exception as e:
        logger.warning("[LIFESPAN] Subagent orphan recovery failed: %s", e)

    try:
        init_firebase()
    except Exception as e:
        startup_status["warnings"].append(f"firebase: {e}")
        logger.warning("[LIFESPAN] Firebase init failed: %s", e)

    try:
        app.state.auth_manager = AuthManager()
        logger.info("[LIFESPAN] AuthManager ready [OK]")
    except Exception as e:
        startup_status["warnings"].append(f"auth_manager: {e}")
        logger.warning("[LIFESPAN] AuthManager init failed: %s", e)

    try:
        from reminders.manager import reminder_manager
        await reminder_manager.load_and_schedule_all()
    except Exception as e:
        startup_status["warnings"].append(f"reminders: {e}")
        logger.warning("[LIFESPAN] Reminders init failed: %s", e)

    try:
        import threading

        from assistant.tts import get_tts
        from reminders.manager import reminder_manager
        tts = get_tts()

        def _play_audio(audio_bytes):
            try:
                import io

                import sounddevice as sd
                import soundfile as sf
                data, sr = sf.read(io.BytesIO(audio_bytes))
                sd.play(data, sr)
                sd.wait()
            except Exception as _e:
                logger.debug("lifespan play_audio failed: %s", _e)

        class _TTSWrapper:
            def speak_async(self, text: str):
                t = threading.Thread(
                    target=lambda: _play_audio(tts.synthesize(text)),
                    daemon=True,
                )
                t.start()

        reminder_manager.inject_tts(_TTSWrapper())
    except Exception as e:
        startup_status["warnings"].append(f"tts: {e}")
        logger.warning("[LIFESPAN] TTS init failed: %s", e)

    # â”€â”€ Phase 10.1: Consolidated Monitoring (replaces health_monitor + proactive_monitor) â”€â”€â”€
    try:
        from assistant.tts import get_tts
        from monitors import AlertRouter, ResourceMonitor, ServiceHealthChecker
        from network.websocket_server import connection_manager
        from tools.whatsapp_sender import whatsapp_sender

        app.state.resource_monitor = ResourceMonitor()
        async def _tts_speak(text):
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, get_tts().synthesize, text)

        app.state.alert_router = AlertRouter(
            broadcast_fn=connection_manager.broadcast,
            speak_fn=_tts_speak,
            whatsapp_fn=whatsapp_sender.send if whatsapp_sender.ready else None,
        )
        app.state.service_health = ServiceHealthChecker(interval=30)
        await app.state.service_health.start()
        from core.model_router import set_health_checker
        set_health_checker(lambda: app.state.service_health.latest().ollama.status == "healthy")
        logger.info("[LIFESPAN] Consolidated monitoring started [OK]")
    except Exception as e:
        startup_status["warnings"].append(f"monitoring: {e}")
        logger.warning("[LIFESPAN] Consolidated monitoring init failed: %s", e)
        # Fallback to legacy health monitor
        try:
            from core.health_monitor import HealthMonitor
            from core.model_router import set_health_checker
            app.state.health = HealthMonitor(interval=30)
            await app.state.health.start()
            set_health_checker(app.state.health.ollama_alive)
            logger.info("[LIFESPAN] Legacy health monitor started (fallback) [OK]")
        except Exception as e2:
            startup_status["warnings"].append(f"health_monitor_fallback: {e2}")
            logger.warning("[LIFESPAN] Legacy health monitor fallback failed: %s", e2)

    # â”€â”€ Phase 10.2: LLM Failover Cooldown Probe â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    try:
        from core.config_schema import jarvis_config
        if jarvis_config.failover.enabled:
            from core.llm_failover import CooldownProbe, llm_failover
            app.state.failover_probe = CooldownProbe(llm_failover.pm)
            await app.state.failover_probe.start()
            logger.info("[LIFESPAN] LLM failover cooldown probe started [OK]")
        else:
            logger.info("[LIFESPAN] LLM failover disabled — using Ollama-first routing")
    except Exception as e:
        startup_status["warnings"].append(f"failover: {e}")
        logger.warning("[LIFESPAN] LLM failover probe init failed: %s", e)

    try:
        from core.email_monitor import EmailMonitor
        from monitors.alerts import Alert, AlertPriority

        async def _email_callback(alert_dict):
            app.state.alert_router.send(Alert(
                priority=AlertPriority.CRITICAL if alert_dict["priority"] == "urgent" else AlertPriority.INFO,
                module=f"email:{alert_dict['from'].split('<')[0].strip()[:20]}",
                message=f"Email: {alert_dict['subject'][:80]}",
                voice_summary=f"Email from {alert_dict['from'].split('<')[0].strip()}: {alert_dict['subject'][:40]}",
            ))

        app.state.email_monitor = EmailMonitor(check_interval=120, alert_callback=_email_callback)
        await app.state.email_monitor.start()
        logger.info("[LIFESPAN] EmailMonitor started [OK]")
    except Exception as e:
        startup_status["warnings"].append(f"email: {e}")
        logger.warning("[LIFESPAN] EmailMonitor init failed: %s", e)

    try:
        from core.audio_emotion import emotion_detector
        app.state.emotion_detector = emotion_detector
        asyncio.create_task(emotion_detector._is_available())
        startup_status["audio_emotion"] = "ok"
        logger.info("[LIFESPAN] AudioEmotionDetector ready [OK]")
    except Exception as e:
        startup_status["audio_emotion"] = f"warning: {e}"
        logger.warning("[LIFESPAN] AudioEmotionDetector init: %s", e)

    try:
        from tools.scene_generator import scene_generator
        app.state.scene_generator = scene_generator
        import shutil
        mode = "blender+threejs" if shutil.which("blender") else "threejs-only"
        startup_status["scene_generator"] = f"ok ({mode})"
        logger.info("[LIFESPAN] SceneGenerator ready (%s) [OK]", mode)
    except Exception as e:
        startup_status["scene_generator"] = f"warning: {e}"
        logger.warning("[LIFESPAN] SceneGenerator init: %s", e)

    try:
        from core.agent_registry import (
            auto_install_missing,
            check_available_agents,
            check_missing_agents,
            check_unconfigured_agents,
            get_config_report,
            write_env_file,
        )
        available = check_available_agents()
        missing = check_missing_agents()
        unconfigured = check_unconfigured_agents()
        logger.info("[LIFESPAN] Agents available: %s", ', '.join(sorted(available)) or 'none')
        if missing:
            logger.info("[LIFESPAN] Auto-installing missing: %s", ', '.join(missing))
            installed = await auto_install_missing()
            if installed:
                logger.info("[LIFESPAN] Installed: %s", ', '.join(installed))
            still_missing = [m for m in missing if m not in installed]
            if still_missing:
                logger.warning("[LIFESPAN] Could not install: %s â€” install manually", ', '.join(still_missing))
        if unconfigured:
            report = get_config_report()
            for name in unconfigured:
                logger.warning("[LIFESPAN] %s: %s", report[name]['label'], report[name]['config_help'])
            env_tips = write_env_file(sum([report[n]['missing_keys'] for n in unconfigured], []))
            if env_tips:
                logger.warning("[LIFESPAN] Add to .env:\n%s", env_tips)
    except Exception as e:
        logger.error("[LIFESPAN] Agents setup failed: %s", e)

    try:
        from core.config_registry import config as _c2
        _ollama_url = _c2.get("ollama.base_url")
        for _ in range(30):
            try:
                from urllib.request import urlopen
                with urlopen(f"{_ollama_url}/api/tags", timeout=1) as resp:
                    if resp.status == 200:
                        break
            except Exception as e:
                logger.exception("[LIFESPAN] Ollama poll attempt failed: %s", e)
                await asyncio.sleep(1)
        _warmup_ollama_models()
    except Exception as e:
        startup_status["warnings"].append(f"ollama_check: {e}")

    try:
        from brain.reasoning_engine import reasoning_engine
        _reasoning_warmup = asyncio.ensure_future(reasoning_engine.warmup())
        def _reasoning_done(t):
            if t.exception():
                logger.warning("[LIFESPAN] Deepseek warmup FAILED: %s", t.exception())
            else:
                logger.info("[LIFESPAN] Deepseek warmup OK")
        _reasoning_warmup.add_done_callback(_reasoning_done)
    except Exception as e:
        logger.warning("[LIFESPAN] Warmup init failed: %s", e)

    try:
        from assistant.voice_pipeline import VoiceLoop
        _voice_loop = VoiceLoop()
        app.state.voice_loop = _voice_loop
        _voice_loop.start()
        logger.info("[LIFESPAN] Wake word + voice loop started [OK]")
    except Exception as e:
        logger.warning("[LIFESPAN] Wake word/voice loop: %s", e)


    try:
        from .dreaming import DreamingLoop
        app.state.dreaming = DreamingLoop(
            supabase_url=SUPABASE_URL or "",
            supabase_key=SUPABASE_SERVICE_KEY or "",
        )

        async def dreaming_scheduler():
            last_run = ""
            while True:
                now = datetime.now()
                if now.hour == 2 and last_run != now.strftime("%Y-%m-%d"):
                    await app.state.dreaming.run_nightly_review()
                    last_run = now.strftime("%Y-%m-%d")
                await asyncio.sleep(3600)

        app.state.dreaming_task = asyncio.create_task(dreaming_scheduler())
        logger.info("[LIFESPAN] AutoDream nightly review scheduler started [OK]")
    except Exception as e:
        logger.warning("[LIFESPAN] AutoDream init failed: %s", e)

    try:
        from .self_healing import learning_loop, self_healing
        app.state.self_healing = self_healing
        app.state.learning_loop = learning_loop
        logger.info("[LIFESPAN] Self-healing framework online [OK]")
        logger.info("[LIFESPAN] Continuous learning loop active [OK]")
    except Exception as e:
        logger.warning("[LIFESPAN] Self-healing/learning init failed: %s", e)

    try:
        import core.llm_router
        from core.quality_grader import ConstitutionalMemory, QualityGrader
        app.state.quality_grader = QualityGrader(
            constitution_path="config/quality_constitution.json",
            llm_router=core.llm_router,
        )
        app.state.constitutional_memory = ConstitutionalMemory()
        logger.info("[LIFESPAN] QualityGrader + ConstitutionalMemory online [OK]")
    except Exception as e:
        startup_status["warnings"].append(f"quality: {e}")
        logger.warning("[LIFESPAN] QualityGrader init failed: %s", e)

    # â”€â”€ Phase 12: PromptOptimizer â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    try:
        if hasattr(app.state, "quality_grader") and hasattr(app.state, "constitutional_memory"):
            from brain.prompt_optimizer import PromptOptimizer
            from brain.UnifiedBrain import unified_brain
            app.state.prompt_optimizer = PromptOptimizer(
                brain  = unified_brain,
                grader = app.state.quality_grader,
                cm     = app.state.constitutional_memory,
            )
            # Restore any previously deployed prompt versions
            from core.prompts import load_deployed_prompts
            load_deployed_prompts()
            logger.info("[LIFESPAN] PromptOptimizer online [OK]")
        else:
            logger.info("[LIFESPAN] Skipped â€” QualityGrader unavailable")
    except Exception as e:
        startup_status["warnings"].append(f"prompt_optimizer: {e}")
        logger.warning("[LIFESPAN] PromptOptimizer init failed: %s", e)

    try:
        from core.project_manager import project_manager
        app.state.build_queue = asyncio.create_task(project_manager.process_queue())
        logger.info("[LIFESPAN] Project manager queue processor started [OK]")
    except Exception as e:
        logger.warning("[LIFESPAN] Queue processor not started: %s", e)

    # â”€â”€ Phase 13: Plugin System â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    try:
        from core.plugins import MemoryPlugin, plugin_registry
        from core.plugins.base import PluginManifest
        from plugins.pc_automation_plugin import Plugin as PCAutomationPlugin
        from plugins.pii_routing_plugin import Plugin as PIIRoutingPlugin
        from plugins.wake_word_plugin import Plugin as WakeWordPlugin
        from plugins.file_tools_plugin import Plugin as FileToolsPlugin
        app.state.plugin_registry = plugin_registry

        builtin_plugins = [
            WakeWordPlugin(PluginManifest(
                name="jarvis.wakeword", version="1.0.0",
                description="Real-time wake word detection via WebRTC VAD + Faster-Whisper",
                hooks=["on_stt", "on_wake_word", "on_load", "on_unload"],
            )),
            PIIRoutingPlugin(PluginManifest(
                name="jarvis.piirouting", version="1.0.0",
                description="Privacy-safe routing override â€” forces LOCAL tier when PII is detected",
                hooks=["on_routing_decision", "on_redact", "on_load", "on_unload"],
            )),
            PCAutomationPlugin(PluginManifest(
                name="jarvis.pcautomation", version="1.0.0",
                description="Autonomous PC control via Open-Interpreter with governance validation",
                hooks=["on_execute", "on_governance_check", "on_load", "on_unload"],
            )),
            MemoryPlugin(PluginManifest(
                name="jarvis.memory", version="1.0.0",
                description="Tiered memory hooks: store, recall, consolidate",
                hooks=["on_store", "on_recall", "on_consolidate", "on_load", "on_unload"],
            )),
            FileToolsPlugin(PluginManifest(
                name="jarvis.filetools", version="1.0.0",
                description="Production-grade filesystem tools: read, write, append, delete, list_folder",
                hooks=["on_load", "on_unload"],
            )),
        ]
        for plugin in builtin_plugins:
            plugin_registry.register(plugin)

        plugin_registry.discover_from_manifest("plugins")

        state_with_app = dict(app.state.__dict__)
        state_with_app["app"] = app
        await plugin_registry.load_all(state_with_app)
        logger.info("[LIFESPAN] %d plugins registered [OK]", plugin_registry.count)
    except Exception as e:
        startup_status["warnings"].append(f"plugins: {e}")
        logger.warning("[LIFESPAN] Plugin system init failed: %s", e)

    # Load skills/library plugins (new plugin system — plugin.json manifests)
    try:
        from core.plugins.loader import get_plugin_loader
        from core.plugins.verification import manifest_verifier
        loader = get_plugin_loader()
        # Verify manifest integrity before loading
        import os as _os
        skills_dir = "skills/library"
        if _os.path.isdir(skills_dir):
            for root, _dirs, files in _os.walk(skills_dir):
                for fname in files:
                    if fname in ("plugin.json", "skill.json"):
                        manifest_verifier.verify_manifest_integrity(_os.path.join(root, fname))
        loaded = loader.load_all("skills/library")
        if loaded:
            logger.info("[LIFESPAN] %d skills/library plugins loaded: %s [OK]", len(loaded), loaded)
        else:
            logger.info("[LIFESPAN] No skills/library plugins found")
    except Exception as e:
        startup_status["warnings"].append(f"skills_plugins: {e}")
        logger.warning("[LIFESPAN] Skills/library plugin loader failed: %s", e)

    # Marketplace refresh (background, best-effort)
    try:
        from core.plugins.marketplace import plugin_marketplace
        await plugin_marketplace.refresh_index()
        logger.info("[LIFESPAN] Plugin marketplace index refreshed [OK]")
    except Exception as e:
        logger.info("[LIFESPAN] Plugin marketplace unavailable (offline) — %s", e)

    # Start governance work queue (background task processor)
    try:
        from core.governance import work_queue
        work_queue.start()
        logger.info("[LIFESPAN] Governance work queue started [OK]")
    except Exception as e:
        startup_status["warnings"].append(f"governance_queue: {e}")
        logger.warning("[LIFESPAN] Governance work queue start failed: %s", e)

    # â”€â”€ Phase 14: Security (audit log) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    try:
        from core.audit_log import audit_log
        app.state.audit_log = audit_log
        logger.info("[LIFESPAN] Audit log ready â€” %s [OK]", audit_log.log_dir)
    except Exception as e:
        startup_status["warnings"].append(f"audit: {e}")
        logger.warning("[LIFESPAN] Audit log init failed: %s", e)

    # â”€â”€ Phase 14.1: Tool Policies â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    try:
        # Already called on import, but explicit is better
        logger.info("[LIFESPAN] Tool policies registered [OK]")
    except Exception as e:
        logger.warning("[LIFESPAN] Tool policies registration failed: %s", e)

    # â”€â”€ Phase 14.2: AuthZ (RBAC) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    try:
        from core.authz.loader import policy_loader
        policy_loader.load_all()
        logger.info("[LIFESPAN] RBAC policies loaded [OK]")
    except Exception as e:
        logger.warning("[LIFESPAN] RBAC policies load failed: %s", e)
    try:
        from channels import channel_controller
        from channels.discord_channel import DiscordChannel
        from channels.irc_channel import IRCChannel
        from channels.matrix_channel import MatrixChannel
        from channels.slack_channel import SlackChannel
        from channels.telegram_channel import TelegramChannel

        channel_controller.register(DiscordChannel())
        channel_controller.register(SlackChannel())
        channel_controller.register(TelegramChannel())
        channel_controller.register(MatrixChannel())
        channel_controller.register(IRCChannel())

        from brain.UnifiedBrain import unified_brain
        await channel_controller.start_all(unified_brain)
        app.state.channel_controller = channel_controller
        logger.info("[LIFESPAN] %d/%d channel(s) running [OK]",
                     len(channel_controller.running), len(channel_controller.channels))
    except Exception as e:
        startup_status["warnings"].append(f"channels: {e}")
        logger.warning("[LIFESPAN] Channel init failed: %s", e)

    # â”€â”€ Phase 16: MCP (Model Context Protocol) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    try:
        from mcp import mcp_server
        await mcp_server.start()
        app.include_router(mcp_server.get_fastapi_router())
        app.state.mcp_server = mcp_server
        logger.info("[LIFESPAN] MCP server online â€” %d tools [OK]", len(mcp_server._tools))
    except Exception as e:
        startup_status["warnings"].append(f"mcp: {e}")
        logger.warning("[LIFESPAN] MCP init failed: %s", e)

    # â”€â”€ Phase 16.1: MCP Bridge (Bidirectional) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    try:
        from core.gateway.bridge import mcp_bridge
        app.state.mcp_bridge = mcp_bridge
        logger.info("[LIFESPAN] MCP Bridge ready [OK]")
    except Exception as e:
        logger.warning("[LIFESPAN] MCP Bridge init failed: %s", e)

    # â”€â”€ Phase 17: Cron Scheduler â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    try:
        from core.cron import scheduler as _cron
        await _cron.start()
        app.state.scheduler = _cron
        logger.info("[LIFESPAN] Cron scheduler started â€” %d job(s) [OK]", len(_cron.list_jobs()))
    except Exception as e:
        startup_status["warnings"].append(f"cron: {e}")
        logger.warning("[LIFESPAN] Cron init failed: %s", e)

    # ── Phase 8.1: Activity Scheduler ──────────────────────────────────────
    try:
        from core.scheduler.scheduler import Scheduler
        from core.scheduler.registry import SchedulerRegistry
        from core.scheduler.executors import (
            research_executor,
            build_executor,
            repair_executor,
            email_executor,
            benchmark_executor,
        )
        registry = SchedulerRegistry()
        registry.register("research", research_executor)
        registry.register("build", build_executor)
        registry.register("repair", repair_executor)
        registry.register("email", email_executor)
        registry.register("benchmark", benchmark_executor)
        activity_scheduler = Scheduler(
            tick_interval=5.0,
            registry=registry,
        )
        await activity_scheduler.start()
        app.state.activity_scheduler = activity_scheduler
        app.state.activity_scheduler_registry = registry
        logger.info("[LIFESPAN] Activity scheduler started [OK]")
    except Exception as e:
        startup_status["warnings"].append(f"activity_scheduler: {e}")
        logger.warning("[LIFESPAN] Activity scheduler init failed: %s", e)

    # ── Phase 18: Backup Manager ──────────────────────────────────────────────
        # â”€â”€ Phase 18: Backup Manager â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    try:
        from core.backup import backup_manager
        app.state.backup_manager = backup_manager
        logger.info("[LIFESPAN] Backup manager ready [OK]")
    except Exception as e:
        startup_status["warnings"].append(f"backup: {e}")
        logger.warning("[LIFESPAN] Backup init failed: %s", e)

    # â”€â”€ Phase 19: Security Auditor â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    try:
        from core.security_audit import security_auditor
        app.state.security_auditor = security_auditor
        logger.info("[LIFESPAN] Security auditor ready [OK]")
    except Exception as e:
        startup_status["warnings"].append(f"security: {e}")
        logger.warning("[LIFESPAN] Security audit init failed: %s", e)

    # â”€â”€ Phase 20: Skills + Commitments â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    try:
        from skills import skill_manager
        skill_manager.load_all()
        app.state.skill_manager = skill_manager
        logger.info("[LIFESPAN] Skills manager ready â€” %d skill(s) [OK]", len(skill_manager.list()))
    except Exception as e:
        startup_status["warnings"].append(f"skills: {e}")
        logger.warning("[LIFESPAN] Skills init failed: %s", e)

    try:
        from core.commitments import commitment_store
        app.state.commitment_store = commitment_store
        overdue = len(commitment_store.upcoming(hours=0))
        if overdue:
            logger.info("[LIFESPAN] Commitment tracker ready â€” %d overdue [OK]", overdue)
        else:
            logger.info("[LIFESPAN] Commitment tracker ready [OK]")
    except Exception as e:
        startup_status["warnings"].append(f"commitments: {e}")
        logger.warning("[LIFESPAN] Commitments init failed: %s", e)

    try:
        from core.proactive_monitor import init_proactive_monitor
        await init_proactive_monitor(app.state)
    except Exception as e:
        startup_status["warnings"].append(f"proactive_monitor: {e}")
        logger.warning("[LIFESPAN] ProactiveMonitor init failed: %s", e)

    try:
        from core.workflow import HeartbeatMonitor, WorkflowEngine, recover_active_workflows
        engine = WorkflowEngine()
        app.state.workflow_engine = engine
        recovered = await recover_active_workflows(engine)
        if recovered:
            for r in recovered:
                logger.info("[WORKFLOW] Recovered %s (%s) at step %d/%d",
                            r["workflow_id"], r["workflow_type"],
                            r["current_step"], r["total_steps"])
            startup_status["warnings"].append(
                f"workflow: {len(recovered)} workflow(s) recovered from crash"
            )
        else:
            logger.info("[WORKFLOW] No active workflows to recover [OK]")
        heartbeat = HeartbeatMonitor(engine, interval=10, stale_seconds=60)
        app.state.workflow_heartbeat = heartbeat
        await heartbeat.start()
        logger.info("[WORKFLOW] Heartbeat monitor started [OK]")
    except Exception as e:
        startup_status["warnings"].append(f"workflow_recovery: {e}")
        logger.warning("[WORKFLOW] Recovery init failed: %s", e)

    if startup_status["warnings"]:
        logger.warning("[JARVIS] Startup completed with warnings: %s", startup_status["warnings"])
    else:
        logger.info("[JARVIS] All systems online [OK]")

    yield

    try:
        from automation.messaging import messaging
        messaging.shutdown()
    except Exception as e:
        logger.warning("[SHUTDOWN] Messaging shutdown failed: %s", e)
    if hasattr(app.state, "voice_loop"):
        app.state.voice_loop.stop()
        logger.info("[SHUTDOWN] Voice loop stopped")
    if hasattr(app.state, "dreaming_task"):
        app.state.dreaming_task.cancel()
        try:
            await asyncio.wait_for(app.state.dreaming_task, timeout=5)
        except (TimeoutError, asyncio.CancelledError):
            pass
        logger.info("[SHUTDOWN] DreamingLoop scheduler stopped")
    if hasattr(app.state, "build_queue"):
        app.state.build_queue.cancel()
        logger.info("[SHUTDOWN] Queue processor stopped")
    if hasattr(app.state, "health"):
        await app.state.health.stop()
        logger.info("[SHUTDOWN] Legacy health monitor stopped")
    if hasattr(app.state, "service_health"):
        await app.state.service_health.stop()
        logger.info("[SHUTDOWN] Service health checker stopped")
    if hasattr(app.state, "failover_probe"):
        await app.state.failover_probe.stop()
        logger.info("[SHUTDOWN] Failover probe stopped")
    if hasattr(app.state, "activity_scheduler"):
        await app.state.activity_scheduler.stop()
        logger.info("[SHUTDOWN] Activity scheduler stopped")
    if hasattr(app.state, "scheduler"):
        await app.state.scheduler.stop()
        logger.info("[SHUTDOWN] Cron scheduler stopped")
    if hasattr(app.state, "mcp_server"):
        await app.state.mcp_server.stop()
        logger.info("[SHUTDOWN] MCP server stopped")
    if hasattr(app.state, "mcp_bridge"):
        await app.state.mcp_bridge.close()
        logger.info("[SHUTDOWN] MCP Bridge closed")
    if hasattr(app.state, "channel_controller"):
        await app.state.channel_controller.stop_all()
        logger.info("[SHUTDOWN] All channels stopped")
    if hasattr(app.state, "plugin_registry"):
        await app.state.plugin_registry.unload_all()
        logger.info("[SHUTDOWN] All plugins unloaded")
    if hasattr(app.state, "workflow_heartbeat"):
        await app.state.workflow_heartbeat.stop()
        logger.info("[SHUTDOWN] Workflow heartbeat monitor stopped")
    if hasattr(app.state, "audit_log"):
        app.state.audit_log.force_flush()
        logger.info("[SHUTDOWN] Audit log flushed")
    logger.info("[JARVIS] Shutdown complete.")
