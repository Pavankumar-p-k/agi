from __future__ import annotations

import os
import tempfile

import pytest
from alembic.config import Config
from alembic import command
from sqlalchemy import create_engine, text


@pytest.fixture
def alembic_cfg():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    orig_url = os.environ.get("JARVIS_DB__URL")
    os.environ["JARVIS_DB__URL"] = f"sqlite+aiosqlite:///{db_path}"
    cfg = Config("alembic.ini")
    yield cfg
    os.environ.pop("JARVIS_DB__URL", None)
    if orig_url is not None:
        os.environ["JARVIS_DB__URL"] = orig_url
    if os.path.exists(db_path):
        os.unlink(db_path)


def _sync_url() -> str:
    return os.environ["JARVIS_DB__URL"].replace("sqlite+aiosqlite://", "sqlite://")


def _execute(statement):
    engine = create_engine(_sync_url())
    try:
        with engine.begin() as conn:
            conn.execute(text(statement))
    finally:
        engine.dispose()


def _fetch(statement):
    engine = create_engine(_sync_url())
    try:
        with engine.begin() as conn:
            return conn.execute(text(statement)).fetchall()
    finally:
        engine.dispose()


class TestMigrationRoundtrip:
    def test_upgrade_downgrade_roundtrip(self, alembic_cfg):
        command.upgrade(alembic_cfg, "head")
        command.downgrade(alembic_cfg, "base")
        command.upgrade(alembic_cfg, "head")

    def test_upgrade_twice_idempotent(self, alembic_cfg):
        command.upgrade(alembic_cfg, "head")
        command.upgrade(alembic_cfg, "head")

    def test_downgrade_twice_idempotent(self, alembic_cfg):
        command.upgrade(alembic_cfg, "head")
        command.downgrade(alembic_cfg, "base")
        command.downgrade(alembic_cfg, "base")

    def test_current_returns_head_after_upgrade(self, alembic_cfg):
        command.upgrade(alembic_cfg, "head")
        import alembic.script
        script = alembic.script.ScriptDirectory.from_config(alembic_cfg)
        head_revision = script.get_current_head()
        from alembic.runtime.migration import MigrationContext
        engine = create_engine(_sync_url())
        try:
            conn = engine.connect()
            ctx = MigrationContext.configure(conn)
            current = ctx.get_current_revision()
            conn.close()
        finally:
            engine.dispose()
        assert current == head_revision


class TestDataPreservation:
    def test_data_survives_idempotent_upgrade(self, alembic_cfg):
        command.upgrade(alembic_cfg, "head")
        _execute(
            "INSERT INTO users (uid, email, display_name, created_at) "
            "VALUES ('test_uid', 'test@example.com', 'Test', datetime('now'))"
        )
        result = _fetch("SELECT uid, email FROM users")
        assert result[0][0] == "test_uid"

        command.upgrade(alembic_cfg, "head")

        result = _fetch("SELECT uid, email FROM users")
        assert result[0][0] == "test_uid"


class TestAllTablesCreated:
    def test_all_11_tables_exist(self, alembic_cfg):
        command.upgrade(alembic_cfg, "head")
        rows = _fetch("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [r[0] for r in rows if r[0] != "alembic_version"]
        expected = [
            "activities", "chat_history", "connected_devices",
            "daily_summaries", "execution_logs", "known_faces",
            "notes", "reminders", "skills", "subagent_runs", "users",
        ]
        assert tables == expected

    def test_all_6_indexes_exist(self, alembic_cfg):
        command.upgrade(alembic_cfg, "head")
        rows = _fetch("SELECT name FROM sqlite_master WHERE type='index' ORDER BY name")
        indexes = [
            r[0] for r in rows
            if not r[0].startswith("sqlite_") and r[0] != "alembic_version"
        ]
        expected = [
            "ix_chat_history_session_id",
            "ix_execution_logs_plan_id",
            "ix_skills_name",
            "ix_subagent_runs_child_session_key",
            "ix_subagent_runs_parent_session_key",
            "ix_users_uid",
        ]
        assert indexes == expected
