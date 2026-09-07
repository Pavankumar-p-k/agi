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

# notes/activity_tracker.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date, time
from typing import Optional, List, Dict, Any

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import Note, Activity, DailySummary, User


class NotesManager:
    async def get_all(self, db: AsyncSession, user: User) -> List[Note]:
        res = await db.execute(
            select(Note).where(Note.user_id == user.id).order_by(Note.updated_at.desc())
        )
        return list(res.scalars().all())

    async def create(self, db: AsyncSession, user: User, title: str, content: str, tags: str = "") -> Note:
        note = Note(user_id=user.id, title=title, content=content, tags=tags)
        db.add(note)
        await db.commit()
        await db.refresh(note)
        return note

    async def update(
        self, db: AsyncSession, user: User, note_id: int, title: Optional[str], content: Optional[str]
    ) -> Optional[Note]:
        res = await db.execute(select(Note).where(Note.user_id == user.id, Note.id == note_id))
        note = res.scalar_one_or_none()
        if note is None:
            return None
        if title is not None:
            note.title = title
        if content is not None:
            note.content = content
        await db.commit()
        await db.refresh(note)
        return note

    async def delete(self, db: AsyncSession, user: User, note_id: int) -> bool:
        res = await db.execute(
            delete(Note).where(Note.user_id == user.id, Note.id == note_id)
        )
        await db.commit()
        return res.rowcount > 0


class ActivityTracker:
    async def log(
        self,
        db: AsyncSession,
        user_id: int,
        activity_type: str,
        description: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Activity:
        item = Activity(
            user_id=user_id,
            activity_type=activity_type,
            description=description,
            meta=metadata,
        )
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item

    async def get_today(self, db: AsyncSession, user_id: int) -> List[Activity]:
        start = datetime.combine(date.today(), time.min)
        res = await db.execute(
            select(Activity)
            .where(Activity.user_id == user_id, Activity.timestamp >= start)
            .order_by(Activity.timestamp.desc())
        )
        return list(res.scalars().all())


@dataclass
class SummaryResult:
    date: str
    summary: str
    productivity_score: float
    raw_data: Dict[str, Any]


class SummaryGenerator:
    async def generate(self, db: AsyncSession, user: User) -> SummaryResult:
        start = datetime.combine(date.today(), time.min)
        activities_res = await db.execute(
            select(Activity).where(Activity.user_id == user.id, Activity.timestamp >= start)
        )
        activities = list(activities_res.scalars().all())

        notes_res = await db.execute(
            select(Note).where(Note.user_id == user.id, Note.updated_at >= start)
        )
        notes = list(notes_res.scalars().all())

        activity_count = len(activities)
        notes_count = len(notes)

        productivity = min(1.0, (activity_count + notes_count) / 20.0) if (activity_count + notes_count) else 0.0
        summary = f"{activity_count} activities and {notes_count} notes recorded today."

        return SummaryResult(
            date=date.today().isoformat(),
            summary=summary,
            productivity_score=productivity,
            raw_data={
                "activity_count": activity_count,
                "notes_count": notes_count,
            },
        )


notes_manager = NotesManager()
activity_tracker = ActivityTracker()
summary_generator = SummaryGenerator()
