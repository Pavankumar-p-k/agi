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
core/database_models.py — Legacy sync SQLite ORM models.

These are the original sync models used by agent_loop and other legacy paths.
They coexist with core/database.py which has async models for the web app.
"""
import asyncio
import contextlib
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

logger = logging.getLogger(__name__)

_db_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="db")

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "jarvis.db"
os.makedirs(str(DB_PATH.parent), exist_ok=True)
engine = create_engine(
    f"sqlite:///{DB_PATH.as_posix()}",
    echo=False,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


@contextlib.asynccontextmanager
async def get_sync_db():
    """Async context manager for sync DB — runs session open/close in a thread."""
    loop = asyncio.get_running_loop()
    db = await loop.run_in_executor(_db_executor, SessionLocal)
    try:
        yield db
    finally:
        await loop.run_in_executor(_db_executor, db.close)


from functools import wraps


def run_db(f):
    """Decorator: run a sync DB function in a thread to avoid blocking the event loop."""
    @wraps(f)
    async def wrapper(*args, **kwargs):
        return await asyncio.to_thread(f, *args, **kwargs)
    return wrapper


Base = declarative_base()


class Session(Base):
    __tablename__ = "sessions"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=True)
    owner = Column(String, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey("sessions.id"), index=True)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Document(Base):
    __tablename__ = "documents"
    id = Column(String, primary_key=True)
    title = Column(String, default="")
    content = Column(Text, default="")
    language = Column(String, default="text")
    owner = Column(String, nullable=True, index=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    id = Column(String, primary_key=True)
    document_id = Column(String, ForeignKey("documents.id"), index=True)
    content = Column(Text, default="")
    version = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)


class McpServer(Base):
    __tablename__ = "mcp_servers"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    transport = Column(String, default="stdio")
    command = Column(String, nullable=True)
    args = Column(Text, nullable=True)
    env = Column(Text, nullable=True)
    url = Column(String, nullable=True)
    is_enabled = Column(Boolean, default=True)
    disabled_tools = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ScheduledTask(Base):
    __tablename__ = "scheduled_tasks"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    schedule = Column(String, nullable=True)
    task_type = Column(String, nullable=True)
    config = Column(Text, nullable=True)
    owner = Column(String, nullable=True, index=True)
    is_active = Column(Boolean, default=True)
    status = Column(String, default="active")
    action = Column(String, nullable=True)
    prompt = Column(Text, nullable=True)
    scheduled_time = Column(String, nullable=True)
    scheduled_day = Column(String, nullable=True)
    trigger_type = Column(String, default="schedule")
    trigger_event = Column(String, nullable=True)
    trigger_count = Column(Integer, nullable=True)
    trigger_counter = Column(Integer, default=0)
    next_run = Column(DateTime, nullable=True)
    last_run = Column(DateTime, nullable=True)
    run_count = Column(Integer, default=0)
    output_target = Column(String, default="session")
    created_at = Column(DateTime, default=datetime.utcnow)


class ModelEndpoint(Base):
    __tablename__ = "model_endpoints"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    base_url = Column(String, nullable=False)
    api_key = Column(String, nullable=True)
    is_enabled = Column(Boolean, default=True)
    supports_tools = Column(Boolean, default=True)
    cached_models = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Webhook(Base):
    __tablename__ = "webhooks"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    url = Column(String, nullable=False)
    events = Column(String, default="chat.completed")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ApiToken(Base):
    __tablename__ = "api_tokens"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    token_hash = Column(String, nullable=True)
    token_prefix = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CalendarCal(Base):
    __tablename__ = "calendar_cals"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    color = Column(String, nullable=True)
    owner = Column(String, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class CalendarEvent(Base):
    __tablename__ = "calendar_events"
    id = Column(Integer, primary_key=True, autoincrement=True)
    uid = Column(String, unique=True, nullable=False)
    calendar_id = Column(String, ForeignKey("calendar_cals.id"), nullable=False)
    summary = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    location = Column(String, nullable=True)
    dtstart = Column(DateTime, nullable=False)
    dtend = Column(DateTime, nullable=False)
    all_day = Column(Boolean, default=False)
    is_utc = Column(Boolean, default=False)
    rrule = Column(String, nullable=True)
    event_type = Column(String, nullable=True)
    importance = Column(String, default="normal")
    status = Column(String, default="confirmed")
    timezone = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Note(Base):
    __tablename__ = "agent_notes"
    id = Column(String, primary_key=True)
    owner = Column(String, nullable=True, index=True)
    title = Column(String, nullable=False)
    content = Column(Text, nullable=True)
    items = Column(Text, nullable=True)
    note_type = Column(String, default="note")
    label = Column(String, nullable=True)
    due_date = Column(String, nullable=True)
    source = Column(String, nullable=True)
    archived = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class GalleryImage(Base):
    __tablename__ = "gallery_images"
    id = Column(String, primary_key=True)
    prompt = Column(Text, nullable=True)
    image_data = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    owner = Column(String, nullable=True, index=True)


def ensure_tables():
    Base.metadata.create_all(engine)
