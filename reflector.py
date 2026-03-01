# self_improve/reflector.py
#
# SELF-IMPROVEMENT / SELF-REFLECTION ENGINE
# ──────────────────────────────────────────────────────────────
# JARVIS periodically looks at its own decisions and asks:
#  "Was I right to do that?"
#  "Which model should I use for this type of problem?"
#  "Are my predictions accurate?"
#  "What can I improve?"
#
# Every 10 AGI loops (~5 minutes), it:
#  1. Reviews last 50 decisions
#  2. Calculates success rate per action type
#  3. Adjusts confidence thresholds
#  4. Logs insights to memory
#  5. Can auto-update its own routing logic weights
#
# This is the "learning from mistakes" layer.

import time
import json
import httpx
from collections import defaultdict


REFLECT_SYSTEM = """You are JARVIS's self-improvement engine.
Analyze the AI's recent decisions and identify what to improve.
Return ONLY valid JSON:
{
  "success_rate": 0.0,
  "best_performing_action": "",
  "worst_performing_action": "",
  "key_insight": "",
  "recommendation": "",
  "confidence_adjustment": 0.0
}"""


class SelfReflector:

    def __init__(self, memory):
        self.memory = memory
        self._reflection_log: list = []
        self._action_stats: dict = defaultdict(lambda: {"success": 0, "fail": 0})
        self._model_accuracy: dict = defaultdict(list)  # model → [quality_scores]

    async def reflect(self, decisions: list, state) -> dict:
        """
        Analyze recent decisions and generate improvement insights.
        Called every 10 AGI loops.
        """
        if len(decisions) < 5:
            return {}  # need enough data to reflect

        print(f"[Reflector] Reflecting on {len(decisions)} decisions...")

        # ── Compute stats ────────────────────────────────────
        for d in decisions:
            action  = d.get("action","")
            success = d.get("success", False)
            model   = d.get("model","")
            quality = d.get("quality", 0)

            if action:
                if success:
                    self._action_stats[action]["success"] += 1
                else:
                    self._action_stats[action]["fail"] += 1

            if model and quality:
                self._model_accuracy[model].append(quality)

        # ── Overall success rate ─────────────────────────────
        total_success = sum(s["success"] for s in self._action_stats.values())
        total_fail    = sum(s["fail"]    for s in self._action_stats.values())
        total         = total_success + total_fail
        success_rate  = total_success / total if total > 0 else 0

        # ── Best / worst actions ─────────────────────────────
        best_action  = max(self._action_stats, key=lambda a: self._action_stats[a]["success"], default="")
        worst_action = max(self._action_stats, key=lambda a: self._action_stats[a]["fail"],    default="")

        # ── Model accuracy ───────────────────────────────────
        model_avg = {}
        for model, scores in self._model_accuracy.items():
            if scores:
                model_avg[model] = round(sum(scores) / len(scores), 2)

        # ── LLM reflection ───────────────────────────────────
        insight = await self._ask_llm_to_reflect(decisions[-20:], success_rate)

        reflection = {
            "timestamp":       time.time(),
            "decisions_analyzed": len(decisions),
            "success_rate":    round(success_rate, 2),
            "best_action":     best_action,
            "worst_action":    worst_action,
            "model_accuracy":  model_avg,
            "llm_insight":     insight,
            "loop_count":      self.memory._loop_count if hasattr(self.memory,'_loop_count') else 0,
        }

        self._reflection_log.append(reflection)
        await self.memory.save_reflection(reflection)

        print(f"[Reflector] Success rate: {success_rate:.0%} | Best: {best_action} | Worst: {worst_action}")
        if insight.get("key_insight"):
            print(f"[Reflector] Insight: {insight['key_insight']}")

        return reflection

    async def _ask_llm_to_reflect(self, decisions: list, success_rate: float) -> dict:
        """Use phi3 to generate improvement insights from decision data."""
        summary = json.dumps({
            "success_rate": round(success_rate, 2),
            "recent_decisions": [
                {"action": d.get("action"), "success": d.get("success"), "confidence": d.get("confidence",0)}
                for d in decisions[-10:]
            ]
        })
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(
                    "http://localhost:11434/api/generate",
                    json={"model":"phi3:mini","system":REFLECT_SYSTEM,"prompt":f"Analyze: {summary}",
                          "stream":False,"options":{"num_predict":200,"num_gpu":99,"temperature":0.3}},
                )
                raw = r.json().get("response","")
                import re
                m = re.search(r'\{.*?\}', raw, re.DOTALL)
                if m:
                    return json.loads(m.group())
        except:
            pass
        return {"key_insight": "", "recommendation": "", "confidence_adjustment": 0.0}

    def get_stats(self) -> dict:
        return {
            "action_stats":     dict(self._action_stats),
            "model_accuracy":   {m: round(sum(s)/len(s),2) for m,s in self._model_accuracy.items() if s},
            "reflections_done": len(self._reflection_log),
        }


# ──────────────────────────────────────────────────────────────
# memory/agi_memory.py

import sqlite3, json, time
from pathlib import Path

DB_PATH = Path("data/jarvis_agi.db")

class AGIMemory:

    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._loop_count = 0
        print("[AGIMemory] Database ready ✓")

    def _conn(self):
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS agi_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT, content TEXT, intent TEXT,
                    emotion TEXT, user_id TEXT,
                    hour INTEGER, day INTEGER,
                    timestamp REAL
                );
                CREATE TABLE IF NOT EXISTS agi_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT, tool TEXT, reasoning TEXT,
                    confidence REAL, success INTEGER,
                    latency_ms INTEGER, state_hour INTEGER,
                    state_mood TEXT, timestamp REAL
                );
                CREATE TABLE IF NOT EXISTS agi_goals (
                    id TEXT PRIMARY KEY, description TEXT,
                    steps TEXT, current_step INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'active', context TEXT,
                    created_at REAL
                );
                CREATE TABLE IF NOT EXISTS agi_patterns (
                    key TEXT PRIMARY KEY, data TEXT, updated_at REAL
                );
                CREATE TABLE IF NOT EXISTS agi_reflections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    data TEXT, timestamp REAL
                );
                CREATE TABLE IF NOT EXISTS agi_solve_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    problem TEXT, steps_total INTEGER, steps_done INTEGER,
                    success INTEGER, duration_s REAL, timestamp REAL
                );
                CREATE INDEX IF NOT EXISTS idx_events_ts ON agi_events(timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_decisions_ts ON agi_decisions(timestamp DESC);
            """)

    async def save_event(self, event: dict):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO agi_events (type,content,intent,emotion,user_id,hour,day,timestamp) VALUES (?,?,?,?,?,?,?,?)",
                (event.get("type",""), event.get("content",""),
                 event.get("intent",""), event.get("emotion",""),
                 event.get("user_id","pavan"), event.get("hour",0),
                 event.get("day",0), event.get("timestamp",time.time()))
            )

    async def save_decision(self, d: dict):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO agi_decisions (action,tool,reasoning,confidence,success,latency_ms,state_hour,state_mood,timestamp) VALUES (?,?,?,?,?,?,?,?,?)",
                (d.get("action",""), d.get("tool",""), d.get("reasoning",""),
                 d.get("confidence",0), 1 if d.get("success") else 0,
                 d.get("latency_ms",0), d.get("state_hour",0),
                 d.get("state_mood",""), d.get("timestamp",time.time()))
            )

    async def save_goal(self, goal: dict):
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO agi_goals (id,description,steps,current_step,status,context,created_at) VALUES (?,?,?,?,?,?,?)",
                (goal["id"], goal["description"], json.dumps(goal["steps"]),
                 goal.get("current_step",0), goal.get("status","active"),
                 json.dumps(goal.get("context",{})), goal.get("created_at",time.time()))
            )

    async def update_goal(self, goal_id: str, current_step: int, status: str):
        with self._conn() as conn:
            conn.execute("UPDATE agi_goals SET current_step=?,status=? WHERE id=?",
                        (current_step, status, goal_id))

    async def save_patterns(self, patterns: dict, sequences):
        with self._conn() as conn:
            conn.execute("INSERT OR REPLACE INTO agi_patterns (key,data,updated_at) VALUES (?,?,?)",
                        ("patterns", json.dumps(patterns), time.time()))
            conn.execute("INSERT OR REPLACE INTO agi_patterns (key,data,updated_at) VALUES (?,?,?)",
                        ("sequences", json.dumps(dict(sequences.most_common(100))), time.time()))

    async def save_reflection(self, reflection: dict):
        with self._conn() as conn:
            conn.execute("INSERT INTO agi_reflections (data,timestamp) VALUES (?,?)",
                        (json.dumps(reflection), time.time()))

    async def save_solve_result(self, result: dict):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO agi_solve_results (problem,steps_total,steps_done,success,duration_s,timestamp) VALUES (?,?,?,?,?,?)",
                (result["problem"],result["steps_total"],result["steps_done"],
                 1 if result["success"] else 0, result["duration_s"],result["timestamp"])
            )

    async def get_recent_events(self, n: int = 10) -> list:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM agi_events ORDER BY timestamp DESC LIMIT ?", (n,)
            ).fetchall()
        return [dict(r) for r in rows]

    async def get_latest_mood(self) -> str:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT emotion FROM agi_events WHERE emotion != '' AND emotion != 'neutral' ORDER BY timestamp DESC LIMIT 1"
            ).fetchone()
        return row["emotion"] if row else "neutral"

    async def get_stats(self) -> dict:
        with self._conn() as conn:
            events    = conn.execute("SELECT COUNT(*) FROM agi_events").fetchone()[0]
            decisions = conn.execute("SELECT COUNT(*) FROM agi_decisions").fetchone()[0]
            successes = conn.execute("SELECT COUNT(*) FROM agi_decisions WHERE success=1").fetchone()[0]
            goals     = conn.execute("SELECT COUNT(*) FROM agi_goals").fetchone()[0]
            reflections = conn.execute("SELECT COUNT(*) FROM agi_reflections").fetchone()[0]
        return {
            "events":       events,
            "decisions":    decisions,
            "success_rate": round(successes/decisions,2) if decisions else 0,
            "goals":        goals,
            "reflections":  reflections,
        }


# ──────────────────────────────────────────────────────────────
# tools/jarvis_tools.py — Bridge to all JARVIS capabilities

import httpx, json

JARVIS_API = "http://localhost:8000"

class JarvisTools:
    """Bridge from AGI layer to all existing JARVIS tools."""

    async def speak(self, text: str):
        """Make JARVIS speak something."""
        if not text: return
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                await c.post(f"{JARVIS_API}/api/tts", json={"text": text})
        except: pass

    async def ask_brain(self, query: str, user_id: str = "pavan") -> str:
        """Query the multi-agent brain."""
        try:
            async with httpx.AsyncClient(timeout=60) as c:
                r = await c.post(f"{JARVIS_API}/brain/chat",
                                json={"message": query, "user_id": user_id})
                return r.json().get("reply","")
        except Exception as e:
            return ""

    async def play_music(self, mode: str = "random") -> dict:
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.post(f"{JARVIS_API}/api/media/play", json={"mode": mode})
                return r.json()
        except: return {}

    async def list_reminders(self) -> list:
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(f"{JARVIS_API}/api/reminders")
                return r.json().get("reminders", [])
        except: return []

    async def count_pending_reminders(self) -> int:
        reminders = await self.list_reminders()
        return len([r for r in reminders if not r.get("done")])

    async def count_unread_messages(self) -> int:
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(f"{JARVIS_API}/api/messages/unread_count")
                return r.json().get("count", 0)
        except: return 0

    async def create_reminder(self, title: str, time_str: str = "") -> bool:
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.post(f"{JARVIS_API}/api/reminders",
                                json={"title": title, "time": time_str})
                return r.status_code == 200
        except: return False

    async def list_recent_notes(self) -> list:
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(f"{JARVIS_API}/api/notes?limit=10")
                return r.json().get("notes", [])
        except: return []

    async def open_url(self, url: str):
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                await c.post(f"{JARVIS_API}/api/automation/browser/open", json={"url": url})
        except: pass

    async def get_daily_briefing(self) -> str:
        """Generate morning briefing text."""
        reminders = await self.list_reminders()
        notes     = await self.list_recent_notes()
        parts = ["Good morning, Pavan! Here's your briefing."]
        if reminders:
            parts.append(f"You have {len(reminders)} reminder{'s' if len(reminders)>1 else ''}.")
        if notes:
            parts.append(f"You have {len(notes)} recent notes.")
        parts.append("Have a great day!")
        return " ".join(parts)

    async def get_daily_summary(self) -> str:
        """Generate end-of-day summary."""
        try:
            async with httpx.AsyncClient(timeout=30) as c:
                r = await c.get(f"{JARVIS_API}/api/activity/summary")
                return r.json().get("summary","Day complete. Rest well, Pavan.")
        except: return "Day complete. Rest well, Pavan."

    async def get_task_list(self) -> list:
        notes = await self.list_recent_notes()
        return [n for n in notes if "task" in n.get("tags","").lower()]

    async def call(self, tool_name: str, params: dict) -> dict:
        """Generic tool call."""
        try:
            async with httpx.AsyncClient(timeout=30) as c:
                r = await c.post(f"{JARVIS_API}/api/tools/{tool_name}", json=params)
                return r.json()
        except: return {}
