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
        self._last_run_date = datetime.utcnow().strftime("%Y-%m-%d")
        logger.info("[DREAMING] Nightly review complete.")
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
            result = await llm_complete(
                "analysis",
                [{"role": "user", "content": prompt}],
            )
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
        if not self.supabase_url or not self.supabase_key:
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
