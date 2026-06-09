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

"""core/dreaming.py
DreamingLoop — scheduled nightly review of past agent sessions.
Finds patterns, failures, preferences.
Updates JARVIS memory with [LEARNED] tagged insights.
"""

import json
import logging
import httpx
from datetime import datetime, timedelta

from .llm_router import complete as llm_complete
from .database import AsyncSessionLocal, ExecutionLog
from sqlalchemy import select, text

logger = logging.getLogger("dreaming")

N8N_WEBHOOK_URL = "http://localhost:5678/webhook/dreaming-review"


class DreamingLoop:
    """
    Scheduled nightly review of past agent sessions.
    Finds patterns, failures, preferences.
    Updates JARVIS memory with learnings.
    """

    def __init__(self, supabase_url: str = "", supabase_key: str = ""):
        self.supabase_url = supabase_url
        self.supabase_key = supabase_key
        self._last_run_date = ""

    async def run_nightly_review(self):
        logger.info("[DREAMING] Starting nightly review...")
        logs = await self._query_recent_logs()
        if not logs:
            logger.info("[DREAMING] No execution logs in the last 7 days, skipping.")
            return {"status": "skipped", "reason": "no data"}

        insights = await self._analyze_patterns(logs)
        await self._store_insights(insights)
        await self._push_to_supabase(insights)
        await self._notify_n8n(insights)
        await self._step_proactive_cleanup()
        await self._step_rotate_training_data()
        await self._step_prune_old_memories()
        await self._step_summarize_failures()
        await self._step_run_adversarial()
        await self._step_check_model_drift()
        await self._step_generate_weekly_report()
        await self._step_validate_preferences()
        await self._step_check_horizon_deadlines()
        await self._step_optimize_prompts()
        await self._check_training_pipeline()
        self._last_run_date = datetime.utcnow().strftime("%Y-%m-%d")
        logger.info("[DREAMING] Nightly review complete.")

        # Phase 3: Emit hook
        try:
            from core.plugins.events import PluginEventBus
            import asyncio
            asyncio.create_task(PluginEventBus.instance().emit("on_dreaming_cycle", insights=insights))
        except Exception as _e:
            logger.debug("dreaming emit hook failed: %s", _e)

        return {"status": "completed", "insights": insights}

    async def _query_recent_logs(self) -> list:
        since = datetime.utcnow() - timedelta(days=7)
        async with AsyncSessionLocal() as session:
            stmt = (
                select(ExecutionLog)
                .where(ExecutionLog.created_at >= since)
                .order_by(ExecutionLog.id.desc())
                .limit(100)
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [
                {
                    "step_id": r.step_id,
                    "agent": r.agent,
                    "command": r.command[:200] if r.command else "",
                    "status": r.status,
                    "error": r.error[:200] if r.error else "",
                    "created_at": r.created_at.isoformat() if r.created_at else "",
                }
                for r in rows
            ]

    async def _analyze_patterns(self, logs: list) -> dict:
        prompt = f"""Review these JARVIS execution logs from the last 7 days and identify:

1. PATTERNS: What repeated patterns do you see?
2. FAILURES: What failed repeatedly and why?
3. PREFERENCES: What can you infer about the user's preferences?
4. LEARNINGS: What should JARVIS learn or change based on this data?

Logs:
{json.dumps(logs[:50], indent=2, default=str)}

Return ONLY valid JSON with this exact structure:
{{
    "patterns": ["list of observed patterns"],
    "repeated_failures": ["list of failure modes"],
    "inferred_preferences": ["user preferences"],
    "learnings": ["actionable learnings for JARVIS"],
    "summary": "one sentence summary"
}}"""
        try:
            result = (await llm_complete(
                "analysis",
                [{"role": "user", "content": prompt}],
            )).unwrap_or("")
            content = result.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            return json.loads(content)
        except Exception as e:
            logger.warning(f"[DREAMING] Analysis failed: {e}")
            return {
                "patterns": [],
                "repeated_failures": [],
                "inferred_preferences": [],
                "learnings": [],
                "summary": f"Analysis failed: {e}",
            }

    async def _store_insights(self, insights: dict):
        async with AsyncSessionLocal() as session:
            stmt = text("""
                INSERT INTO chat_history (user_id, role, message, intent, timestamp)
                VALUES (:uid, :role, :msg, :intent, :ts)
            """)
            msg = f"[LEARNED] AutoDream nightly review: {json.dumps(insights, default=str)[:2000]}"
            await session.execute(stmt, {
                "uid": 1,
                "role": "assistant",
                "msg": msg,
                "intent": "autodream_review",
                "ts": datetime.utcnow(),
            })
            await session.commit()
        logger.info("[DREAMING] Insights stored in chat_history as [LEARNED]")

    async def _push_to_supabase(self, insights: dict):
        if not self.supabase_url or not self.supabase_key or self.supabase_url == "":
            logger.debug("[DREAMING] Supabase credentials not set, skipping push.")
            return
        try:
            async with httpx.AsyncClient() as http:
                await http.post(
                    f"{self.supabase_url}/rest/v1/notifications",
                    headers={
                        "Authorization": f"Bearer {self.supabase_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "user_id": "default",
                        "type": "autodream_review",
                        "title": "AutoDream Nightly Review",
                        "body": insights.get("summary", "Nightly review completed"),
                        "data": json.dumps(insights, default=str),
                        "created_at": datetime.utcnow().isoformat(),
                    },
                    timeout=10,
                )
        except Exception as e:
            logger.warning(f"[DREAMING] Supabase push failed: {e}")

    DOMAINS = ["code", "website_building", "summarization", "privacy_classification"]

    async def _check_training_pipeline(self):
        try:
            from learning.training_collector import TrainingCollector
            collector = TrainingCollector()
            total = collector.count()
            logger.info(f"[DREAMING] Training collector has {total} entries")

            MIN_ENTRIES = 500
            if total < MIN_ENTRIES:
                logger.info(f"[DREAMING] Need {MIN_ENTRIES} entries for fine-tuning, have {total}")
                return

            from train.lora_finetune import finetune, deploy_to_ollama
            from train.ab_eval import run_ab_eval

            for domain in self.DOMAINS:
                domain_count = collector.count(domain=domain)
                domain_min = max(MIN_ENTRIES // 4, 100)
                if domain_count < domain_min:
                    logger.info(f"[DREAMING] Domain '{domain}' only {domain_count} entries, need {domain_min}")
                    continue

                logger.info(f"[DREAMING] Fine-tuning domain: {domain} ({domain_count} entries)")
                result = finetune(domain=domain)

                if result.get("status") != "done":
                    logger.warning(f"[DREAMING] Fine-tune for '{domain}' failed: {result.get('reason', 'unknown')}")
                    continue

                model_path = result["model_path"]
                ab = await run_ab_eval("analysis", f"jarvis-{domain}", n_queries=5)

                if ab.deploy:
                    deploy_to_ollama(model_path, f"jarvis-{domain}")
                    logger.info(f"[DREAMING] Deployed jarvis-{domain} (improvement: {ab.improvement:+.1f})")
                else:
                    logger.info(f"[DREAMING] AB eval rejected jarvis-{domain} (base={ab.base_mean}, ft={ab.ft_mean})")

        except ImportError as e:
            logger.warning(f"[DREAMING] Training pipeline deps not available: {e}")
        except Exception as e:
            logger.warning(f"[DREAMING] Training pipeline error: {e}")

    async def _notify_n8n(self, insights: dict):
        try:
            async with httpx.AsyncClient() as http:
                await http.post(
                    N8N_WEBHOOK_URL,
                    json={
                        "insights": insights,
                        "timestamp": datetime.utcnow().isoformat(),
                        "source": "autodream",
                    },
                    timeout=10,
                )
            logger.info("[DREAMING] n8n webhook notified")
        except Exception as e:
            logger.warning(f"[DREAMING] n8n webhook failed: {e}")

    # ── Phase 9: 9 new dream tasks ──────────────────────────────────────

    async def _step_proactive_cleanup(self) -> None:
        try:
            from network.websocket_server import connection_manager
            cleaned = 0
            for key, ws in list(connection_manager.active.items()):
                try:
                    await ws.send_json({"type": "ping"})
                except Exception as e:
                    logger.exception("[DREAMING] Stale WS ping failed: %s", e)
                    connection_manager.active.pop(key, None)
                    cleaned += 1
            if cleaned:
                logger.info("[DREAMING] Cleaned %d stale WS connections", cleaned)
        except Exception as e:
            logger.warning("[DREAMING] Cleanup step failed: %s", e)

    async def _step_rotate_training_data(self) -> None:
        try:
            from learning.training_collector import TrainingCollector
            import sqlite3
            collector = TrainingCollector()
            with sqlite3.connect(collector.DB_PATH) as conn:
                conn.execute("DELETE FROM training_log WHERE id NOT IN (SELECT id FROM training_log ORDER BY id DESC LIMIT 10000)")
                logger.info("[DREAMING] Training data rotated (kept 10000)")
        except Exception as e:
            logger.warning("[DREAMING] Training rotate failed: %s", e)

    async def _step_prune_old_memories(self) -> None:
        try:
            from memory.tiered_memory import tiered_memory
            tiered_memory.consolidate()
            logger.info("[DREAMING] Memory consolidation done")
        except Exception as e:
            logger.warning("[DREAMING] Memory prune failed: %s", e)

    async def _step_summarize_failures(self) -> None:
        try:
            from core.health_monitor import HealthMonitor
            hm = HealthMonitor(interval=9999)
            summary = hm.to_dict()
            failed = [k for k, v in summary.get("modules", {}).items() if v.get("failures", 0) > 0]
            if failed:
                logger.info("[DREAMING] Modules with failures: %s", failed)
        except Exception as e:
            logger.warning("[DREAMING] Failure summary failed: %s", e)

    async def _step_run_adversarial(self) -> None:
        try:
            from core.adversarial import AdversarialTester
            from learning.training_collector import TrainingCollector
            from brain.UnifiedBrain import unified_brain
            collector = TrainingCollector()
            entries = collector.export_for_training(min_score=0)
            if entries:
                tester = AdversarialTester()
                result = await tester.test(entries[-1]["output"], "general", unified_brain)
                if not result.hardened:
                    logger.warning("[DREAMING] Adversarial found %d issues in latest output", len(result.findings))
        except Exception as e:
            logger.warning("[DREAMING] Adversarial step failed: %s", e)

    async def _step_check_model_drift(self) -> None:
        try:
            from learning.training_collector import TrainingCollector
            from core.quality_grader import ConstitutionalMemory
            cm = ConstitutionalMemory()
            patterns = cm.failure_patterns("response", min_entries=10)
            if patterns:
                logger.info("[DREAMING] Quality drift patterns: %s", patterns)
        except Exception as e:
            logger.warning("[DREAMING] Drift check failed: %s", e)

    async def _step_generate_weekly_report(self) -> None:
        try:
            from learning.training_collector import TrainingCollector
            import json
            from pathlib import Path
            collector = TrainingCollector()
            report = {
                "timestamp": datetime.utcnow().isoformat(),
                "type": "weekly_report",
                "training_count": collector.count(),
            }
            report_path = Path("reports") / f"weekly_{datetime.utcnow().strftime('%Y-W%V')}.json"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, indent=2, default=str))
            logger.info("[DREAMING] Weekly report saved to %s", report_path)
        except Exception as e:
            logger.warning("[DREAMING] Weekly report failed: %s", e)

    async def _step_validate_preferences(self) -> None:
        try:
            from memory.preferences import PreferenceStore
            ps = PreferenceStore()
            prefs = ps.all()
            logger.info("[DREAMING] %d stored preferences verified", len(prefs))
        except Exception as e:
            logger.warning("[DREAMING] Preference validation failed: %s", e)

    async def _step_check_horizon_deadlines(self) -> None:
        try:
            from core.horizon_planner import HorizonPlanner
            planner = HorizonPlanner()
            approaching = planner.get_approaching_deadlines(days_ahead=3)
            for goal in approaching:
                logger.warning("[HORIZON] Goal '%s' deadline approaching", goal.description[:40])
        except Exception as e:
            logger.warning("[DREAMING] Horizon deadline check failed: %s", e)

    async def _step_optimize_prompts(self) -> None:
        try:
            from brain.prompt_optimizer import PromptOptimizer
            from brain.UnifiedBrain import unified_brain
            from core.quality_grader import QualityGrader, ConstitutionalMemory
            import core.llm_router
            opt = PromptOptimizer(
                brain  = unified_brain,
                grader = QualityGrader(str(Path(__file__).resolve().parent.parent / "config" / "quality_constitution.json"), core.llm_router),
                cm     = ConstitutionalMemory(),
            )
            results = await opt.run_cycle()
            for r in results:
                if r.get("status") == "deployed":
                    logger.info("[DREAMING] Prompt optimized for '%s' (score +%.1f%%)",
                                r["agent"], r.get("improvement", 0))
                elif r.get("status") == "skipped":
                    logger.debug("[DREAMING] Prompt skip '%s': %s", r["agent"], r.get("reason", ""))
        except Exception as e:
            logger.warning("[DREAMING] Prompt optimization step failed: %s", e)
