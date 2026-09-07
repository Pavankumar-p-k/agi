"""Database engine and Base metadata."""
import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker

env_file = os.getenv("JARVIS_ENV_FILE")
if env_file:
    load_dotenv(env_file, override=False)
elif os.getenv("JARVIS_ENV", "").lower() == "production":
    load_dotenv(Path(__file__).resolve().parents[1] / ".env.production", override=False)
DATABASE_URL = os.getenv("JARVIS_DB__URL") or os.getenv("DATABASE_URL") or "sqlite+aiosqlite:///:memory:"

if DATABASE_URL.startswith("sqlite") and "://" in DATABASE_URL:
    database_path = DATABASE_URL.rsplit("///", 1)[-1]
    if database_path and database_path != ":memory:":
        Path(database_path).expanduser().parent.mkdir(parents=True, exist_ok=True)

engine = create_async_engine(DATABASE_URL, echo=False)
Base = declarative_base()
SessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
