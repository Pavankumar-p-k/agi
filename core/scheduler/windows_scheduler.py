"""Windows Task Scheduler integration for persistent daily alarms.

Uses `schtasks.exe` — no external dependencies. Windows only.
Survives JARVIS restarts because tasks are system-level.
"""

import re
import logging
import subprocess
from datetime import datetime, time as dt_time
from pathlib import Path

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────── Helpers
def _schtasks(args: list[str]) -> subprocess.CompletedProcess:
    """Run schtasks and return the CompletedProcess."""
    try:
        return subprocess.run(
            ["schtasks"] + args,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        logger.error("schtasks.exe not found — this is a Windows-only feature.")
        return subprocess.CompletedProcess("schtasks", returncode=-1, stdout="", stderr="schtasks.exe not found")


def _task_name(label: str) -> str:
    """Generate a unique task name from the alarm label."""
    import hashlib
    h = hashlib.md5(label.encode()).hexdigest()[:8]
    return f"JARVIS_Alarm_{h}"


# ────────────────────────────────────────────────────────────── Public API


def create_daily_task(label: str, at_time: str) -> dict:
    """Create a daily schtasks alarm.

    Parameters
    ----------
    label : str
        Human-readable alarm label (e.g. "Morning briefing").
    at_time : str
        Time in "HH:MM" format (24‑hour), e.g. "05:00".
    """
    task_name = _task_name(label)

    # Build a simple command file path. We'll write a tiny .vbs script
    # that JARVIS can recognise when it starts next.
    # The scheduler task will run this script at the appointed time.
    import tempfile
    tmp = Path(tempfile.mktemp(suffix=".vbs", prefix="jarvis_alarm_"))
    tmp.write_text(
        f'CreateObject("WScript.Shell").Popup "JARVIS Alarm: {label}" '
        f'16, 16, "JARVIS Alarm", 64\n'
    )
    cmd_path = tmp.resolve().as_posix()

    # Create the task: daily, run at HH:MM, with the command script
    args_create = [
        "/Create", "/SC", "Daily", "/ST", at_time,
        "/TN", task_name,
        "/TR", cmd_path,
        "/F",  # Force overwrite if task exists
    ]
    r = _schtasks(args_create)
    if r.returncode != 0:
        logger.error(f"schtasks /Create failed: stderr={r.stderr}")
        return {"status": "error", "stderr": r.stderr}

    # Store the alarm info in the local DB so the agent can list/manage it
    try:
        from core.database import Reminder, init_db, get_db
        import asyncio

        async def _store():
            await init_db()
            db = get_db()
            r = Reminder(
                title=label,
                remind_at=datetime.combine(datetime.today(), dt_time(int(at_time[:2]), int(at_time[3:]))),
                repeat="daily",
                is_done=False,
            )
            db.add(r)
            await db.commit()
            await db.close()

        asyncio.run(_store())
    except Exception as e:
        logger.warning(f"Could not store reminder in DB: {e}")

    return {"status": "ok", "task_name": task_name, "at_time": at_time, "cmd_script": str(tmp)}


def delete_task(label: str) -> dict:
    """Delete a daily alarm task."""
    task_name = _task_name(label)

    args_delete = ["/Delete", "/TN", task_name, "/F"]
    r = _schtasks(args_delete)

    # Also remove from DB
    try:
        from core.database import Reminder, get_db, init_db
        import asyncio

        async def _delete():
            await init_db()
            db = get_db()
            from sqlalchemy import delete
            await db.execute(delete(Reminder).where(Reminder.title == label))
            await db.commit()
            await db.close()

        asyncio.run(_delete())
    except Exception as e:
        logger.warning(f"Could not delete reminder from DB: {e}")

    return {"status": "ok" if r.returncode == 0 else "error", "stderr": r.stderr}


def list_tasks() -> list[dict]:
    """List all JARVIS alarm tasks from schtasks."""
    args = ["/Query", "/TN", "JARVIS_Alarm_*"]
    r = _schtasks(args)
    tasks = []
    if r.returncode != 0:
        return tasks

    for line in r.stdout.splitlines():
        m = re.search(r"JARVIS_Alarm_\S+", line)
        if m:
            tasks.append({"task_name": m.group(0)})
    return tasks


def check_pending_alarms() -> list[dict]:
    """Check the DB for daily reminders that are due (remind_at <= now, not done).

    Called when JARVIS starts up so it can fire any pending daily alarms.
    """
    try:
        from core.database import Reminder, get_db, init_db
        import asyncio

        async def _check():
            await init_db()
            db = get_db()
            from sqlalchemy import select
            now = datetime.utcnow()
            res = await db.execute(
                select(Reminder).where(
                    Reminder.remind_at <= now,
                    Reminder.repeat == "daily",
                    Reminder.is_done == False,
                )
            )
            due = res.scalars().all()
            results = []
            for r in due:
                results.append(
                    {
                        "title": r.title,
                        "remind_at": r.remind_at.isoformat(),
                        "repeat": r.repeat,
                    }
                )
                r.is_done = True
                db.add(r)
                await db.commit()
            await db.close()
            return results

        return asyncio.run(_check())
    except Exception as e:
        logger.warning(f"Could not check pending alarms: {e}")
        return []


# ────────────────────────────────────────────────────────────── Module init
# On import, ensure any existing schtasks are reflected in the DB.
try:
    # List existing tasks and make DB entries for any that don't have one
    from core.database import init_db, get_db, Reminder
    import asyncio, subprocess

    async def _init():
        await init_db()
        db = get_db()
        args = ["/Query", "/TN", "JARVIS_Alarm_*"]
        res = subprocess.run(["schtasks"] + args, capture_output=True, text=True, timeout=30)
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                m = re.search(r"JARVIS_Alarm_\S+", line)
                if m:
                    task_name = m.group(0)
                    # Extract the label from the VBS script inside the task
                    # (simple approach: just use the task name as identifier)
                    existing = (
                        db.query(Reminder)
                        .filter(Reminder.title.like(f"%{task_name.replace('JARVIS_Alarm_', '')}%"))
                        .first()
                    )
                    if not existing:
                        # Create a minimal entry so the alarm is "active"
                        try:
                            time_match = re.search(r"_(\d{2})(\d{2})$", task_name)
                            hour = minute = "00"
                            if time_match:
                                hour = time_match.group(1)
                                minute = time_match.group(2)
                            r = Reminder(
                                title=task_name.replace("JARVIS_Alarm_", ""),
                                remind_at=datetime.combine(
                                    datetime.today(),
                                    dt_time(int(hour), int(minute)),
                                ),
                                repeat="daily",
                                is_done=False,
                            )
                            db.add(r)
                        except Exception:
                            pass
        await db.close()
        await asyncio.sleep(0)  # yield

    asyncio.run(_init())
except Exception as e:
    logger.warning(f"Alarm migration on import failed: {e}")