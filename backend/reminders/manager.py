from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import AsyncSessionLocal, Reminder, User


class ReminderManager:
    def __init__(self) -> None:
        self.tts = None
        self._tasks: dict[int, asyncio.Task] = {}

    async def load_and_schedule_all(self) -> None:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Reminder)
                .where(Reminder.is_done == False)  # noqa: E712
                .order_by(Reminder.remind_at.asc())
            )
            reminders = list(result.scalars().all())

        for reminder in reminders:
            self.schedule(reminder)
        print(f'[Reminder] Loaded {len(reminders)} pending reminders')

    def inject_tts(self, tts) -> None:
        self.tts = tts

    def schedule(self, reminder: Reminder) -> None:
        self.cancel(reminder.id)
        self._tasks[reminder.id] = asyncio.create_task(self._run(reminder))

    def cancel(self, reminder_id: int) -> None:
        task = self._tasks.pop(reminder_id, None)
        if task and not task.done():
            task.cancel()

    def shutdown(self) -> None:
        for reminder_id in list(self._tasks.keys()):
            self.cancel(reminder_id)

    async def _run(self, reminder: Reminder) -> None:
        try:
            while True:
                wait_s = (reminder.remind_at - datetime.now()).total_seconds()
                if wait_s > 0:
                    await asyncio.sleep(wait_s)

                message = f"Reminder: {reminder.title}"
                print(f'[Reminder] {message}')
                if self.tts:
                    try:
                        self.tts.speak_async(message)
                    except Exception:
                        pass

                async with AsyncSessionLocal() as db:
                    db_reminder = await db.get(Reminder, reminder.id)
                    if not db_reminder:
                        return

                    repeat = (db_reminder.repeat or 'none').lower()
                    if repeat == 'daily':
                        db_reminder.remind_at = db_reminder.remind_at + timedelta(days=1)
                    elif repeat == 'weekly':
                        db_reminder.remind_at = db_reminder.remind_at + timedelta(days=7)
                    elif repeat == 'monthly':
                        db_reminder.remind_at = db_reminder.remind_at + timedelta(days=30)
                    else:
                        db_reminder.is_done = True

                    await db.commit()
                    await db.refresh(db_reminder)

                    if db_reminder.is_done:
                        return
                    reminder = db_reminder
        except asyncio.CancelledError:
            return


reminder_manager = ReminderManager()


async def get_user_reminders(db: AsyncSession, user: User) -> list[Reminder]:
    result = await db.execute(
        select(Reminder).where(Reminder.user_id == user.id).order_by(Reminder.remind_at.asc())
    )
    return list(result.scalars().all())


async def create_reminder(
    db: AsyncSession,
    user: User,
    title: str,
    remind_at: datetime,
    description: str = '',
    repeat: str = 'none',
) -> Reminder:
    reminder = Reminder(
        user_id=user.id,
        title=title,
        remind_at=remind_at,
        description=description,
        repeat=repeat,
    )
    db.add(reminder)
    await db.commit()
    await db.refresh(reminder)
    reminder_manager.schedule(reminder)
    return reminder


async def delete_reminder(db: AsyncSession, user: User, reminder_id: int) -> bool:
    result = await db.execute(
        select(Reminder).where(Reminder.id == reminder_id, Reminder.user_id == user.id)
    )
    reminder = result.scalar_one_or_none()
    if not reminder:
        return False

    await db.delete(reminder)
    await db.commit()
    reminder_manager.cancel(reminder_id)
    return True


async def complete_reminder(db: AsyncSession, user: User, reminder_id: int) -> Reminder | None:
    result = await db.execute(
        select(Reminder).where(Reminder.id == reminder_id, Reminder.user_id == user.id)
    )
    reminder = result.scalar_one_or_none()
    if not reminder:
        return None

    reminder.is_done = True
    await db.commit()
    await db.refresh(reminder)
    reminder_manager.cancel(reminder_id)
    return reminder
