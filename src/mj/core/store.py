"""SQLite state store of record for MJ.

One database file holds tasks, the event log, the audit chain, the capability
registry, world-model facts, plan steps, approvals and step results. WAL mode
gives crash-safe concurrent readers. Schema changes go through migrations.

Invariant 9: this is the *one* state store. Anything else that keeps state
(wrapped components) must be read through adapters and reconciled, never
treated as a second source of truth.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id          TEXT PRIMARY KEY,
    goal        TEXT NOT NULL,
    state       TEXT NOT NULL,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL,
    report_json TEXT
);

CREATE TABLE IF NOT EXISTS events (
    seq          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           REAL NOT NULL,
    task_id      TEXT,
    kind         TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS capabilities (
    id             TEXT PRIMARY KEY,
    manifest_json  TEXT NOT NULL,
    status         TEXT NOT NULL,
    registered_at  REAL NOT NULL,
    updated_at     REAL NOT NULL,
    last_verified  REAL
);

CREATE TABLE IF NOT EXISTS facts (
    scope        TEXT NOT NULL,
    key          TEXT NOT NULL,
    value_json   TEXT NOT NULL,
    source       TEXT NOT NULL,
    observed_at  REAL NOT NULL,
    ttl_seconds  REAL NOT NULL,
    label        TEXT NOT NULL,
    PRIMARY KEY (scope, key)
);

CREATE TABLE IF NOT EXISTS audit_entries (
    seq          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           REAL NOT NULL,
    actor        TEXT NOT NULL,
    action       TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    prev_hash    TEXT NOT NULL,
    entry_hash   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS plan_steps (
    task_id         TEXT NOT NULL,
    step_id         TEXT NOT NULL,
    name            TEXT NOT NULL,
    capability_id   TEXT NOT NULL,
    risk_class      TEXT NOT NULL,
    inputs_json     TEXT NOT NULL,
    depends_on_json TEXT NOT NULL,
    status          TEXT NOT NULL,
    idempotency_key TEXT,
    PRIMARY KEY (task_id, step_id)
);

CREATE TABLE IF NOT EXISTS approvals (
    id            TEXT PRIMARY KEY,
    task_id       TEXT NOT NULL,
    step_id       TEXT NOT NULL,
    payload_json  TEXT NOT NULL,
    payload_hash  TEXT NOT NULL,
    risk_class    TEXT NOT NULL,
    state         TEXT NOT NULL,
    requested_at  REAL NOT NULL,
    decided_at    REAL,
    decided_by    TEXT,
    decision      TEXT
);

CREATE TABLE IF NOT EXISTS step_results (
    idempotency_key TEXT PRIMARY KEY,
    task_id         TEXT NOT NULL,
    step_id         TEXT NOT NULL,
    output_json     TEXT NOT NULL,
    verified        INTEGER NOT NULL,
    evidence_json   TEXT,
    started_at      REAL NOT NULL,
    finished_at     REAL NOT NULL
);
"""


def canonical_json(obj: object) -> str:
    """Serialize deterministically: sorted keys, no whitespace variance."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


class Store:
    """Thin wrapper over one SQLite database with migrations applied."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    @classmethod
    def open(cls, root: Path | None = None) -> "Store":
        """Open (creating if needed) the store under the MJ home directory.

        The root can be redirected with the MJ_HOME environment variable,
        which is how tests get an isolated directory.
        """
        if root is None:
            env = os.environ.get("MJ_HOME")
            root = Path(env) if env else Path.home() / ".mj"
        return cls(Path(root) / "mj.sqlite3")

    def _migrate(self) -> None:
        # _SCHEMA is idempotent (CREATE TABLE IF NOT EXISTS), so it is safe to
        # apply on every open. Version bumps come later as real migrations.
        self.conn.executescript(_SCHEMA)
        if self.get_meta("schema_version") is None:
            self.set_meta("schema_version", str(SCHEMA_VERSION))
        if self.get_meta("created_at") is None:
            self.set_meta("created_at", str(time.time()))

    # -- meta ----------------------------------------------------------------

    def get_meta(self, key: str, default: str | None = None) -> str | None:
        row = self.conn.execute(
            "SELECT value FROM meta WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default

    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    def meta(self) -> dict[str, str]:
        return {
            row["key"]: row["value"]
            for row in self.conn.execute("SELECT key, value FROM meta")
        }

    # -- generic helpers ------------------------------------------------------

    def execute(self, sql: str, params: tuple | dict = ()) -> sqlite3.Cursor:
        return self.conn.execute(sql, params)

    def query(self, sql: str, params: tuple | dict = ()) -> list[sqlite3.Row]:
        return list(self.conn.execute(sql, params).fetchall())

    def one(self, sql: str, params: tuple | dict = ()) -> sqlite3.Row | None:
        return self.conn.execute(sql, params).fetchone()

    def close(self) -> None:
        self.conn.close()
