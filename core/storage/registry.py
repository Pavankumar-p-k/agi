from __future__ import annotations

from pathlib import Path

DATA_DIR = Path("data")
HOME_DIR = Path.home() / ".jarvis"

# ── Bounded-context databases (target architecture) ──────────

SYSTEM_DB = str(DATA_DIR / "system.db")
"""System-wide operational data: workflow, activity, research, scheduler, etc."""

APP_DB = str(DATA_DIR / "app.db")
"""Application ORM data: users, chat_history, notes, reminders, skills."""

MEMORY_DB = str(DATA_DIR / "memory.db")
"""Memory subsystem: episodic, semantic, task, decision stores."""

PLANNER_DB = str(DATA_DIR / "planner.db")
"""Planner subsystem: unified goals/plans/outcomes."""

USER_DB = str(HOME_DIR / "user.db")
"""User-scoped stores: agent_state, cron, feedback, commitments, etc."""

# ── Legacy database paths (being consolidated) ───────────────

LEGACY_WORKFLOW_DB = str(DATA_DIR / "workflow.db")
LEGACY_BRAIN_DB = str(DATA_DIR / "brain.db")
LEGACY_GOALS_DB = str(DATA_DIR / "goals.db")
LEGACY_JARVIS_MEMORY_DB = str(DATA_DIR / "jarvis_memory.db")
LEGACY_BROWSER_FACTS_DB = str(DATA_DIR / "browser_facts.db")
LEGACY_INBOX_DB = str(DATA_DIR / "inbox.db")
LEGACY_BENCHMARK_DB = str(DATA_DIR / "benchmark.db")
LEGACY_TRAINING_LOG_DB = str(DATA_DIR / "training_log.db")
LEGACY_FAILURE_MEMORY_DB = str(DATA_DIR / "failure_memory.db")
LEGACY_PLUGIN_STATE_DB = str(DATA_DIR / "plugin_state.db")
LEGACY_PLUGIN_SECRETS_DB = str(DATA_DIR / "plugin_secrets.db")
LEGACY_JARVIS_DB = str(DATA_DIR / "jarvis.db")


def ensure_db_dir(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
