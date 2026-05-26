"""
core/database.py — All SQLAlchemy models + async DB engine
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, Text, DateTime, Boolean, Float, Integer, ForeignKey, JSON
from datetime import datetime
from typing import Optional, List
from .config import DATABASE_URL


# ── Engine & Session ──
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Migrate: add intent column if missing (SQLite)
    try:
        async with engine.begin() as conn:
            from sqlalchemy import text
            await conn.execute(text("ALTER TABLE chat_history ADD COLUMN intent VARCHAR(50) DEFAULT 'chat'"))
    except Exception:
        pass  # column already exists
    try:
        async with engine.begin() as conn:
            await conn.execute(text("ALTER TABLE chat_history ADD COLUMN session_id VARCHAR(36)"))
    except Exception:
        pass  # column already exists
    print("[DB] Database initialized")


class Base(DeclarativeBase):
    pass


# ══════════════════════════════════════════════
#  MODELS
# ══════════════════════════════════════════════

class User(Base):
    __tablename__ = "users"

    id:           Mapped[int]           = mapped_column(Integer, primary_key=True)
    uid:          Mapped[str]           = mapped_column(String(128), unique=True, index=True)  # Firebase UID
    email:        Mapped[str]           = mapped_column(String(255), unique=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(255))
    created_at:   Mapped[datetime]      = mapped_column(DateTime, default=datetime.utcnow)
    last_seen:    Mapped[Optional[datetime]] = mapped_column(DateTime)
    preferences:  Mapped[Optional[dict]] = mapped_column(JSON)

    notes:        Mapped[List["Note"]]      = relationship(back_populates="user")
    reminders:    Mapped[List["Reminder"]]  = relationship(back_populates="user")
    activities:   Mapped[List["Activity"]]  = relationship(back_populates="user")
    faces:        Mapped[List["KnownFace"]] = relationship(back_populates="owner")


class Note(Base):
    __tablename__ = "notes"

    id:         Mapped[int]           = mapped_column(Integer, primary_key=True)
    user_id:    Mapped[int]           = mapped_column(ForeignKey("users.id"))
    title:      Mapped[str]           = mapped_column(String(255))
    content:    Mapped[str]           = mapped_column(Text)
    tags:       Mapped[Optional[str]] = mapped_column(String(500))   # comma-separated
    created_at: Mapped[datetime]      = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime]      = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_pinned:  Mapped[bool]          = mapped_column(Boolean, default=False)

    user: Mapped["User"] = relationship(back_populates="notes")


class Reminder(Base):
    __tablename__ = "reminders"

    id:          Mapped[int]           = mapped_column(Integer, primary_key=True)
    user_id:     Mapped[int]           = mapped_column(ForeignKey("users.id"))
    title:       Mapped[str]           = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text)
    remind_at:   Mapped[datetime]      = mapped_column(DateTime)
    repeat:      Mapped[Optional[str]] = mapped_column(String(50))   # none|daily|weekly|monthly
    is_done:     Mapped[bool]          = mapped_column(Boolean, default=False)
    created_at:  Mapped[datetime]      = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="reminders")


class Activity(Base):
    __tablename__ = "activities"

    id:           Mapped[int]           = mapped_column(Integer, primary_key=True)
    user_id:      Mapped[int]           = mapped_column(ForeignKey("users.id"))
    activity_type: Mapped[str]          = mapped_column(String(100))  # app_opened|message_sent|location|voice_command
    description:  Mapped[str]           = mapped_column(Text)
    meta:         Mapped[Optional[dict]] = mapped_column("metadata", JSON)  # extra data
    timestamp:    Mapped[datetime]       = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="activities")


class DailySummary(Base):
    __tablename__ = "daily_summaries"

    id:          Mapped[int]  = mapped_column(Integer, primary_key=True)
    user_id:     Mapped[int]  = mapped_column(ForeignKey("users.id"))
    date:        Mapped[str]  = mapped_column(String(20))   # YYYY-MM-DD
    summary:     Mapped[str]  = mapped_column(Text)
    mood_score:  Mapped[Optional[float]] = mapped_column(Float)
    productivity_score: Mapped[Optional[float]] = mapped_column(Float)
    raw_data:    Mapped[Optional[dict]] = mapped_column(JSON)
    created_at:  Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class KnownFace(Base):
    __tablename__ = "known_faces"

    id:           Mapped[int]           = mapped_column(Integer, primary_key=True)
    owner_id:     Mapped[int]           = mapped_column(ForeignKey("users.id"))
    person_name:  Mapped[str]           = mapped_column(String(255))
    relation:     Mapped[Optional[str]] = mapped_column(String(100))   # friend|family|stranger|etc
    info:         Mapped[Optional[str]] = mapped_column(Text)          # extra stored info
    embedding_path: Mapped[str]         = mapped_column(String(500))   # path to face image/embedding
    image_count:  Mapped[int]           = mapped_column(Integer, default=0)
    first_seen:   Mapped[datetime]      = mapped_column(DateTime, default=datetime.utcnow)
    last_seen:    Mapped[Optional[datetime]] = mapped_column(DateTime)
    access_level: Mapped[str]           = mapped_column(String(50), default="visitor")  # owner|trusted|visitor|blocked

    owner: Mapped["User"] = relationship(back_populates="faces")


class ChatHistory(Base):
    __tablename__ = "chat_history"

    id:         Mapped[int]  = mapped_column(Integer, primary_key=True)
    user_id:    Mapped[int]  = mapped_column(ForeignKey("users.id"))
    role:       Mapped[str]  = mapped_column(String(20))   # user|assistant
    message:    Mapped[str]  = mapped_column(Text)
    intent:     Mapped[Optional[str]] = mapped_column(String(50), default="chat")
    session_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    timestamp:  Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ConnectedDevice(Base):
    __tablename__ = "connected_devices"

    id:           Mapped[int]           = mapped_column(Integer, primary_key=True)
    user_id:      Mapped[int]           = mapped_column(ForeignKey("users.id"))
    device_name:  Mapped[str]           = mapped_column(String(255))
    device_type:  Mapped[str]           = mapped_column(String(50))   # android|windows
    ip_address:   Mapped[Optional[str]] = mapped_column(String(45))
    last_connected: Mapped[Optional[datetime]] = mapped_column(DateTime)
    is_online:    Mapped[bool]          = mapped_column(Boolean, default=False)


class JarvisSkill(Base):
    __tablename__ = "skills"

    id:          Mapped[int]  = mapped_column(Integer, primary_key=True)
    name:        Mapped[str]  = mapped_column(String(255), unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    template:    Mapped[str]  = mapped_column(Text)
    created_at:  Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ExecutionLog(Base):
    __tablename__ = "execution_logs"

    id:          Mapped[int]       = mapped_column(Integer, primary_key=True)
    plan_id:     Mapped[Optional[str]] = mapped_column(String(128), index=True)
    goal:        Mapped[Optional[str]] = mapped_column(Text)
    step_id:     Mapped[int]       = mapped_column(Integer)
    agent:       Mapped[str]       = mapped_column(String(50))
    command:     Mapped[Optional[str]] = mapped_column(Text)
    status:      Mapped[str]       = mapped_column(String(20))
    result:      Mapped[Optional[str]] = mapped_column(Text)
    error:       Mapped[Optional[str]] = mapped_column(Text)
    duration_ms: Mapped[Optional[float]] = mapped_column(Float)
    created_at:  Mapped[datetime]  = mapped_column(DateTime, default=datetime.utcnow)
