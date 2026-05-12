# reminders/manager.py
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional, List

from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import Reminder, User, get_db


class ReminderManager:
    def __init__(self) -> None:
        self._tts = None
        self._loop_task = None

    def inject_tts(self, tts_fn) -> None:
        self._tts = tts_fn

    async def load_and_schedule_all(self) -> None:
        """Start the background reminder polling loop."""
        if self._loop_task is None or self._loop_task.done():
            self._loop_task = asyncio.create_task(self._reminder_loop())
            print("[Reminders] Background scheduler started ✓")

    async def _reminder_loop(self):
        """Poll the database for due reminders every 30 seconds."""
        while True:
            try:
                await self._check_due_reminders()
            except Exception as e:
                print(f"[Reminders] Loop error: {e}")
            await asyncio.sleep(30)

    async def _check_due_reminders(self):
        """Find reminders that are due and notify the user."""
        async for db in get_db():
            now = datetime.utcnow()
            result = await db.execute(
                select(Reminder).where(
                    Reminder.remind_at <= now,
                    Reminder.is_done == False
                )
            )
            due = result.scalars().all()

            for r in due:
                msg = f"REMINDER: {r.title}"
                if r.description:
                    msg += f". {r.description}"

                print(f"[Reminders] Firing: {msg}")

                # Trigger TTS if available
                if self._tts:
                    try:
                        self._tts.speak_async(msg)
                    except Exception as e:
                        print(f"[Reminders] TTS failed: {e}")

                # Mark as done
                r.is_done = True
                db.add(r)

            if due:
                await db.commit()

            break # Exit the generator after one session


reminder_manager = ReminderManager()


async def get_user_reminders(db: AsyncSession, user: User) -> List[Reminder]:
    res = await db.execute(
        select(Reminder).where(Reminder.user_id == user.id).order_by(Reminder.remind_at.asc())
    )
    return list(res.scalars().all())


async def create_reminder(
    db: AsyncSession,
    user: User,
    title: str,
    remind_at: datetime,
    description: Optional[str] = "",
    repeat: Optional[str] = "none",
) -> Reminder:
    r = Reminder(
        user_id=user.id,
        title=title,
        description=description,
        remind_at=remind_at,
        repeat=repeat,
    )
    db.add(r)
    await db.commit()
    await db.refresh(r)
    return r


async def delete_reminder(db: AsyncSession, user: User, reminder_id: int) -> bool:
    res = await db.execute(
        delete(Reminder).where(Reminder.user_id == user.id, Reminder.id == reminder_id)
    )
    await db.commit()
    return res.rowcount > 0


async def count_pending_reminders(db: AsyncSession, user: User) -> int:
    now = datetime.utcnow()
    res = await db.execute(
        select(Reminder).where(Reminder.user_id == user.id, Reminder.remind_at >= now, Reminder.is_done == False)
    )
    return len(res.scalars().all())
