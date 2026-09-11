"""Database engine and Base metadata."""
import os
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv

from sqlalchemy import (
    create_engine, Column, Integer, String, Boolean, DateTime, Text, ForeignKey,
    select, delete, update
)
from sqlalchemy.orm import declarative_base, sessionmaker, Mapped, mapped_column

env_file = os.getenv("JARVIS_ENV_FILE")
if env_file:
    load_dotenv(env_file, override=False)
elif os.getenv("JARVIS_ENV", "").lower() == "production":
    load_dotenv(Path(__file__).resolve().parents[1] / ".env.production", override=False)
DATABASE_URL = os.getenv("JARVIS_DB__URL") or os.getenv("DATABASE_URL") or "sqlite:///data/memory.db"

if DATABASE_URL.startswith("sqlite") and "://" in DATABASE_URL:
    database_path = DATABASE_URL.rsplit("///", 1)[-1]
    if database_path and database_path != ":memory:":
        Path(database_path).expanduser().parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(DATABASE_URL, echo=False, future=True)
Base = declarative_base()


# ────────────────────────────────────────────────────────────── Exports
# Re-export commonly used symbols for convenience
__all__ = [
    "engine", "Base", "User", "Reminder", "get_db", "init_db",
    "select", "delete", "update",
]


# ────────────────────────────────────────────────────────────── Models
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    username: Mapped[str] = mapped_column(String(128), default="user")
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), default=1)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    remind_at: Mapped[datetime] = mapped_column(DateTime)
    repeat: Mapped[str] = mapped_column(String(20), default="none")  # "none", "daily", "weekly", "monthly"
    is_done: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


# ────────────────────────────────────────────────────────────── Helpers
def get_db():
    """Return a new sync DB session."""
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return SessionLocal()


# ────────────────────────────────────────────────────────────── Init
def init_db():
    """Create all tables."""
    Base.metadata.create_all(engine)