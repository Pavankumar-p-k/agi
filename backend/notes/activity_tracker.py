from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import Activity, DailySummary, Note, User


class NotesManager:
    async def get_all(self, db: AsyncSession, user: User) -> list[Note]:
        result = await db.execute(
            select(Note)
            .where(Note.user_id == user.id)
            .order_by(Note.updated_at.desc())
        )
        return list(result.scalars().all())

    async def create(self, db: AsyncSession, user: User, title: str, content: str, tags: str = '') -> Note:
        note = Note(user_id=user.id, title=title, content=content, tags=tags)
        db.add(note)
        await db.commit()
        await db.refresh(note)
        return note

    async def update(self, db: AsyncSession, user: User, note_id: int, title: str | None, content: str | None) -> Note | None:
        result = await db.execute(select(Note).where(Note.id == note_id, Note.user_id == user.id))
        note = result.scalar_one_or_none()
        if not note:
            return None
        if title is not None:
            note.title = title
        if content is not None:
            note.content = content
        note.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(note)
        return note

    async def delete(self, db: AsyncSession, user: User, note_id: int) -> bool:
        result = await db.execute(select(Note).where(Note.id == note_id, Note.user_id == user.id))
        note = result.scalar_one_or_none()
        if not note:
            return False
        await db.delete(note)
        await db.commit()
        return True


class ActivityTracker:
    async def log(self, db: AsyncSession, user_id: int, activity_type: str, description: str, metadata: dict | None = None) -> None:
        entry = Activity(
            user_id=user_id,
            activity_type=activity_type,
            description=description,
            metadata_json=metadata,
        )
        db.add(entry)
        await db.commit()

    async def get_today(self, db: AsyncSession, user_id: int) -> list[Activity]:
        today = datetime.utcnow().date()
        start = datetime(today.year, today.month, today.day)
        end = datetime(today.year, today.month, today.day, 23, 59, 59)
        result = await db.execute(
            select(Activity)
            .where(and_(Activity.user_id == user_id, Activity.timestamp >= start, Activity.timestamp <= end))
            .order_by(Activity.timestamp.desc())
        )
        return list(result.scalars().all())


@dataclass
class SummaryView:
    date: str
    summary: str
    productivity_score: float
    raw_data: dict


class SummaryGenerator:
    async def generate(self, db: AsyncSession, user: User) -> SummaryView:
        today = datetime.utcnow().strftime('%Y-%m-%d')
        result = await db.execute(
            select(func.count(Activity.id)).where(Activity.user_id == user.id)
        )
        total = int(result.scalar() or 0)
        productivity = min(100.0, float(total * 5))
        summary_text = f'{total} tracked activities so far.'

        summary = DailySummary(
            user_id=user.id,
            date=today,
            summary=summary_text,
            productivity_score=productivity,
            raw_data={'activity_count': total},
        )
        db.add(summary)
        await db.commit()

        return SummaryView(
            date=today,
            summary=summary_text,
            productivity_score=productivity,
            raw_data={'activity_count': total},
        )


notes_manager = NotesManager()
activity_tracker = ActivityTracker()
summary_generator = SummaryGenerator()
