"""
db/schema.py — JARVIS Social AI — Complete Database Schema
All tables, indexes, constraints, and helper functions.
Trait values are clamped 0.0–1.0 at the DB layer via CHECK constraints.
"""
from __future__ import annotations
import sqlite3, json, time, os
from pathlib import Path
from typing import Optional

DB_PATH = os.environ.get("JARVIS_DB", "jarvis_social.db")
SHORT_TERM_KEY = os.environ.get("JARVIS_ENCRYPT_KEY", "")  # set to enable encryption


def connect(db_path: str = DB_PATH) -> sqlite3.Connection:
    con = sqlite3.connect(db_path, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA cache_size=-16000")
    return con


CLAMP_CHECK = "CHECK(val >= 0.0 AND val <= 1.0)"


SCHEMA = """
-- ══════════════════════════════════════════════════
--  PERSONALITY VECTORS  (one row per friend)
-- ══════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS personality_vectors (
    friend_id          TEXT PRIMARY KEY,
    humor              REAL DEFAULT 0.5  CHECK(humor >= 0.0 AND humor <= 1.0),
    caring             REAL DEFAULT 0.6  CHECK(caring >= 0.0 AND caring <= 1.0),
    formality          REAL DEFAULT 0.4  CHECK(formality >= 0.0 AND formality <= 1.0),
    emoji              REAL DEFAULT 0.4  CHECK(emoji >= 0.0 AND emoji <= 1.0),
    energy             REAL DEFAULT 0.5  CHECK(energy >= 0.0 AND energy <= 1.0),
    directness         REAL DEFAULT 0.5  CHECK(directness >= 0.0 AND directness <= 1.0),
    engagement_score   REAL DEFAULT 0.5  CHECK(engagement_score >= 0.0 AND engagement_score <= 1.0),
    special_mode       INTEGER DEFAULT 0,
    cooldown_until     REAL DEFAULT 0,   -- unix timestamp
    last_interaction   REAL DEFAULT 0,
    total_messages     INTEGER DEFAULT 0,
    -- Hard-locked harmful traits (always 0)
    aggression         REAL DEFAULT 0.0  CHECK(aggression = 0.0),
    manipulation       REAL DEFAULT 0.0  CHECK(manipulation = 0.0),
    dependency         REAL DEFAULT 0.0  CHECK(dependency = 0.0),
    jealousy           REAL DEFAULT 0.0  CHECK(jealousy = 0.0),
    conflict_escalation REAL DEFAULT 0.0 CHECK(conflict_escalation = 0.0),
    created_at         REAL DEFAULT (unixepoch()),
    updated_at         REAL DEFAULT (unixepoch())
);
CREATE INDEX IF NOT EXISTS idx_pv_special ON personality_vectors(special_mode);
CREATE INDEX IF NOT EXISTS idx_pv_cooldown ON personality_vectors(cooldown_until);

-- ══════════════════════════════════════════════════
--  GLOBAL JARVIS TRAITS
-- ══════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS global_jarvis_traits (
    id                  INTEGER PRIMARY KEY CHECK(id = 1),  -- singleton
    confidence          REAL DEFAULT 0.7  CHECK(confidence >= 0.0 AND confidence <= 1.0),
    playfulness_bias    REAL DEFAULT 0.5  CHECK(playfulness_bias >= 0.0 AND playfulness_bias <= 1.0),
    philosophical_depth REAL DEFAULT 0.4  CHECK(philosophical_depth >= 0.0 AND philosophical_depth <= 1.0),
    initiative_tendency REAL DEFAULT 0.3  CHECK(initiative_tendency >= 0.0 AND initiative_tendency <= 1.0),
    updated_at          REAL DEFAULT (unixepoch())
);
INSERT OR IGNORE INTO global_jarvis_traits (id) VALUES (1);

-- ══════════════════════════════════════════════════
--  FRIEND REGISTRY
-- ══════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS friends (
    friend_id        TEXT PRIMARY KEY,
    display_name     TEXT NOT NULL,
    phone            TEXT UNIQUE,
    instagram_id     TEXT UNIQUE,
    nickname         TEXT,
    platform         TEXT DEFAULT 'whatsapp',
    special_mode     INTEGER DEFAULT 0,
    notes            TEXT DEFAULT '',
    last_interaction REAL DEFAULT 0,
    created_at       REAL DEFAULT (unixepoch())
);
CREATE INDEX IF NOT EXISTS idx_friends_phone ON friends(phone);
CREATE INDEX IF NOT EXISTS idx_friends_insta ON friends(instagram_id);

-- ══════════════════════════════════════════════════
--  SHORT TERM MESSAGES  (content — 30 day retention)
-- ══════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS short_term_messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    friend_id   TEXT NOT NULL REFERENCES friends(friend_id) ON DELETE CASCADE,
    role        TEXT NOT NULL CHECK(role IN ('user','jarvis','manual')),
    content     TEXT NOT NULL,
    platform    TEXT DEFAULT 'whatsapp',
    session_id  TEXT DEFAULT '',
    timestamp   REAL DEFAULT (unixepoch()),
    expires_at  REAL DEFAULT (unixepoch() + 2592000)  -- +30 days
);
CREATE INDEX IF NOT EXISTS idx_stm_friend_ts ON short_term_messages(friend_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_stm_expires ON short_term_messages(expires_at);

-- ══════════════════════════════════════════════════
--  METADATA LOGS  (permanent analytics)
-- ══════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS metadata_logs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    friend_id      TEXT NOT NULL,
    tone_score     REAL DEFAULT 0.5,
    emoji_density  REAL DEFAULT 0.0,
    response_time  REAL DEFAULT 0.0,   -- seconds
    message_length INTEGER DEFAULT 0,
    sentiment      REAL DEFAULT 0.5,   -- 0=negative, 1=positive
    conflict_flag  INTEGER DEFAULT 0,
    engagement     REAL DEFAULT 0.5,
    timestamp      REAL DEFAULT (unixepoch())
);
CREATE INDEX IF NOT EXISTS idx_ml_friend_ts ON metadata_logs(friend_id, timestamp DESC);

-- ══════════════════════════════════════════════════
--  EXPERIMENT HISTORY
-- ══════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS experiment_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    friend_id       TEXT NOT NULL,
    trait_name      TEXT NOT NULL,
    original_value  REAL NOT NULL,
    test_value      REAL NOT NULL,
    messages_tested INTEGER DEFAULT 0,
    target_messages INTEGER DEFAULT 20,
    engagement_before REAL DEFAULT 0.0,
    engagement_after  REAL DEFAULT 0.0,
    result          TEXT DEFAULT 'pending',  -- pending|kept|reverted
    started_at      REAL DEFAULT (unixepoch()),
    ended_at        REAL
);
CREATE INDEX IF NOT EXISTS idx_exp_friend ON experiment_history(friend_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_exp_pending ON experiment_history(result) WHERE result='pending';

-- ══════════════════════════════════════════════════
--  INTERVENTION LOGS
-- ══════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS intervention_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    friend_id       TEXT NOT NULL,
    trigger_reason  TEXT NOT NULL,   -- engagement_drop|conflict_spike|cold_response
    severity        TEXT NOT NULL CHECK(severity IN ('LOW','MEDIUM','HIGH')),
    trait_adjusted  TEXT DEFAULT '',
    old_value       REAL DEFAULT 0.0,
    new_value       REAL DEFAULT 0.0,
    manual_suggested INTEGER DEFAULT 0,
    resolved        INTEGER DEFAULT 0,
    timestamp       REAL DEFAULT (unixepoch())
);
CREATE INDEX IF NOT EXISTS idx_il_friend ON intervention_logs(friend_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_il_unresolved ON intervention_logs(resolved) WHERE resolved=0;

-- ══════════════════════════════════════════════════
--  LONG-TERM MEMORY TOKENS (permanent, extracted)
-- ══════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS memory_tokens (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    friend_id   TEXT NOT NULL,
    token_type  TEXT NOT NULL,  -- nickname|inside_joke|preference|fact|topic
    token_value TEXT NOT NULL,
    context     TEXT DEFAULT '',
    confidence  REAL DEFAULT 1.0,
    times_used  INTEGER DEFAULT 0,
    created_at  REAL DEFAULT (unixepoch()),
    UNIQUE(friend_id, token_type, token_value)
);
CREATE INDEX IF NOT EXISTS idx_mt_friend ON memory_tokens(friend_id);

-- ══════════════════════════════════════════════════
--  REPLY QUEUE  (prevent double-text)
-- ══════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS reply_queue (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    friend_id   TEXT NOT NULL UNIQUE,
    pending     INTEGER DEFAULT 0,
    last_sent   REAL DEFAULT 0,
    last_received REAL DEFAULT 0,
    awaiting_reply INTEGER DEFAULT 0  -- 1 = jarvis sent, waiting for response
);

-- ══════════════════════════════════════════════════
--  ADMIN SETTINGS
-- ══════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS admin_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at REAL DEFAULT (unixepoch())
);
INSERT OR IGNORE INTO admin_settings (key, value) VALUES
    ('auto_reply_enabled',  'true'),
    ('presence_enabled',    'true'),
    ('experiment_enabled',  'true'),
    ('system_paused',       'false'),
    ('admin_password_hash', ''),
    ('laptop_status',       'online');
"""


def init_db(db_path: str = DB_PATH) -> None:
    """Create all tables. Safe to call multiple times."""
    from pathlib import Path
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    try:
        con.executescript(SCHEMA)   # executescript handles multi-statement correctly
    except Exception as e:
        print(f"[Schema] Warning: {e}")
    con.close()
    print(f"[DB] Schema initialized ✓  ({db_path})")


def clamp(val: float) -> float:
    """Clamp trait value to [0.0, 1.0]."""
    return max(0.0, min(1.0, float(val)))


def get_setting(key: str, db_path: str = DB_PATH) -> str:
    con = connect(db_path)
    row = con.execute("SELECT value FROM admin_settings WHERE key=?", (key,)).fetchone()
    con.close()
    return row["value"] if row else ""


def set_setting(key: str, value: str, db_path: str = DB_PATH) -> None:
    con = connect(db_path)
    con.execute("INSERT OR REPLACE INTO admin_settings (key,value,updated_at) VALUES (?,?,?)",
                (key, value, time.time()))
    con.commit()
    con.close()


if __name__ == "__main__":
    init_db()
    print("Tables created.")
