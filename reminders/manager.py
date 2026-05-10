# reminders/manager.py
from __future__ import annotations

from datetime import datetime
from typing import Optional, List

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import Reminder, User


class ReminderManager:
    def __init__(self) -> None:
        self._tts = None

    def inject_tts(self, tts_fn) -> None:
        self._tts = tts_fn

    async def load_and_schedule_all(self) -> None:
        # Placeholder for scheduler integration
        return None


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
