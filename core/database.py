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

"""
core/database.py â€” All SQLAlchemy models + async DB engine
"""
import logging
from datetime import datetime
from pathlib import Path

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .config import DATABASE_URL

logger = logging.getLogger(__name__)


# â”€â”€ Engine & Session (tuned pool: pool_size=10, max_overflow=20, pool_pre_ping=True)
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    from alembic.config import Config

    from alembic import command

    _here = Path(__file__).resolve().parent.parent
    _ini = _here / "alembic.ini"
    if not _ini.exists():
        logger.warning("[DB] alembic.ini not found at %s — skipping migrations", _ini)
        return
    alembic_cfg = Config(str(_ini))
    command.upgrade(alembic_cfg, "head")
    print("[DB] Database initialized (alembic upgrade head)")


class Base(DeclarativeBase):
    pass


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  MODELS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class User(Base):
    __tablename__ = "users"

    id:           Mapped[int]           = mapped_column(Integer, primary_key=True)
    uid:          Mapped[str]           = mapped_column(String(128), unique=True, index=True)  # Firebase UID
    email:        Mapped[str]           = mapped_column(String(255), unique=True)
    display_name: Mapped[str | None] = mapped_column(String(255))
    created_at:   Mapped[datetime]      = mapped_column(DateTime, default=datetime.utcnow)
    last_seen:    Mapped[datetime | None] = mapped_column(DateTime)
    preferences:  Mapped[dict | None] = mapped_column(JSON)

    notes:        Mapped[list["Note"]]      = relationship(back_populates="user")
    reminders:    Mapped[list["Reminder"]]  = relationship(back_populates="user")
    activities:   Mapped[list["Activity"]]  = relationship(back_populates="user")
    faces:        Mapped[list["KnownFace"]] = relationship(back_populates="owner")


class Note(Base):
    __tablename__ = "notes"

    id:         Mapped[int]           = mapped_column(Integer, primary_key=True)
    user_id:    Mapped[int]           = mapped_column(ForeignKey("users.id"))
    title:      Mapped[str]           = mapped_column(String(255))
    content:    Mapped[str]           = mapped_column(Text)
    tags:       Mapped[str | None] = mapped_column(String(500))   # comma-separated
    created_at: Mapped[datetime]      = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime]      = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_pinned:  Mapped[bool]          = mapped_column(Boolean, default=False)

    user: Mapped["User"] = relationship(back_populates="notes")


class Reminder(Base):
    __tablename__ = "reminders"

    id:          Mapped[int]           = mapped_column(Integer, primary_key=True)
    user_id:     Mapped[int]           = mapped_column(ForeignKey("users.id"))
    title:       Mapped[str]           = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    remind_at:   Mapped[datetime]      = mapped_column(DateTime)
    repeat:      Mapped[str | None] = mapped_column(String(50))   # none|daily|weekly|monthly
    is_done:     Mapped[bool]          = mapped_column(Boolean, default=False)
    created_at:  Mapped[datetime]      = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="reminders")


class Activity(Base):
    __tablename__ = "activities"

    id:           Mapped[int]           = mapped_column(Integer, primary_key=True)
    user_id:      Mapped[int]           = mapped_column(ForeignKey("users.id"))
    activity_type: Mapped[str]          = mapped_column(String(100))  # app_opened|message_sent|location|voice_command
    description:  Mapped[str]           = mapped_column(Text)
    meta:         Mapped[dict | None] = mapped_column("metadata", JSON)  # extra data
    timestamp:    Mapped[datetime]       = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="activities")


class DailySummary(Base):
    __tablename__ = "daily_summaries"

    id:          Mapped[int]  = mapped_column(Integer, primary_key=True)
    user_id:     Mapped[int]  = mapped_column(ForeignKey("users.id"))
    date:        Mapped[str]  = mapped_column(String(20))   # YYYY-MM-DD
    summary:     Mapped[str]  = mapped_column(Text)
    mood_score:  Mapped[float | None] = mapped_column(Float)
    productivity_score: Mapped[float | None] = mapped_column(Float)
    raw_data:    Mapped[dict | None] = mapped_column(JSON)
    created_at:  Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class KnownFace(Base):
    __tablename__ = "known_faces"

    id:           Mapped[int]           = mapped_column(Integer, primary_key=True)
    owner_id:     Mapped[int]           = mapped_column(ForeignKey("users.id"))
    person_name:  Mapped[str]           = mapped_column(String(255))
    relation:     Mapped[str | None] = mapped_column(String(100))   # friend|family|stranger|etc
    info:         Mapped[str | None] = mapped_column(Text)          # extra stored info
    embedding_path: Mapped[str]         = mapped_column(String(500))   # path to face image/embedding
    image_count:  Mapped[int]           = mapped_column(Integer, default=0)
    first_seen:   Mapped[datetime]      = mapped_column(DateTime, default=datetime.utcnow)
    last_seen:    Mapped[datetime | None] = mapped_column(DateTime)
    access_level: Mapped[str]           = mapped_column(String(50), default="visitor")  # owner|trusted|visitor|blocked

    owner: Mapped["User"] = relationship(back_populates="faces")


class ChatHistory(Base):
    __tablename__ = "chat_history"

    id:         Mapped[int]  = mapped_column(Integer, primary_key=True)
    user_id:    Mapped[int]  = mapped_column(ForeignKey("users.id"))
    role:       Mapped[str]  = mapped_column(String(20))   # user|assistant
    message:    Mapped[str]  = mapped_column(Text)
    intent:     Mapped[str | None] = mapped_column(String(50), default="chat")
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    timestamp:  Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ConnectedDevice(Base):
    __tablename__ = "connected_devices"

    id:           Mapped[int]           = mapped_column(Integer, primary_key=True)
    user_id:      Mapped[int]           = mapped_column(ForeignKey("users.id"))
    device_name:  Mapped[str]           = mapped_column(String(255))
    device_type:  Mapped[str]           = mapped_column(String(50))   # android|windows
    ip_address:   Mapped[str | None] = mapped_column(String(45))
    last_connected: Mapped[datetime | None] = mapped_column(DateTime)
    is_online:    Mapped[bool]          = mapped_column(Boolean, default=False)


class JarvisSkill(Base):
    __tablename__ = "skills"

    id:          Mapped[int]  = mapped_column(Integer, primary_key=True)
    name:        Mapped[str]  = mapped_column(String(255), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    template:    Mapped[str]  = mapped_column(Text)
    created_at:  Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ExecutionLog(Base):
    __tablename__ = "execution_logs"

    id:          Mapped[int]       = mapped_column(Integer, primary_key=True)
    plan_id:     Mapped[str | None] = mapped_column(String(128), index=True)
    goal:        Mapped[str | None] = mapped_column(Text)
    step_id:     Mapped[int]       = mapped_column(Integer)
    agent:       Mapped[str]       = mapped_column(String(50))
    command:     Mapped[str | None] = mapped_column(Text)
    status:      Mapped[str]       = mapped_column(String(20))
    result:      Mapped[str | None] = mapped_column(Text)
    error:       Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[float | None] = mapped_column(Float)
    created_at:  Mapped[datetime]  = mapped_column(DateTime, default=datetime.utcnow)


class SubagentRun(Base):
    __tablename__ = "subagent_runs"

    run_id:             Mapped[str]           = mapped_column(String(128), primary_key=True)
    agent_id:           Mapped[str]           = mapped_column(String(100))
    parent_session_key: Mapped[str | None] = mapped_column(String(255), index=True)
    child_session_key:  Mapped[str]           = mapped_column(String(255), index=True)
    task:               Mapped[str]           = mapped_column(Text)
    status:             Mapped[str]           = mapped_column(String(20), default="pending") # pending|running|completed|failed|killed
    depth:              Mapped[int]           = mapped_column(Integer, default=0)
    created_at:         Mapped[datetime]      = mapped_column(DateTime, default=datetime.utcnow)
    started_at:         Mapped[datetime | None] = mapped_column(DateTime)
    ended_at:           Mapped[datetime | None] = mapped_column(DateTime)
    result_text:        Mapped[str | None] = mapped_column(Text)
    error:              Mapped[str | None] = mapped_column(Text)
    outcome:            Mapped[str | None] = mapped_column(String(20)) # ok|error|timeout|killed
    cleanup:            Mapped[str]           = mapped_column(String(20), default="delete") # delete|keep
    meta:               Mapped[dict | None] = mapped_column("metadata", JSON, default={})
