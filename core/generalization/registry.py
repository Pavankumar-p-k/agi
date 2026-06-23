"""Phase 14.0 — Structural Property Registry.

Manages property definitions (what dimensions exist) and system profiles
(what values each system has for those dimensions).

Backed by SQLite for persistence across restarts.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core.generalization.models import (
    PropertySource,
    PropertyValueType,
    StructuralProperty,
    SystemProfile,
    SystemType,
)

logger = logging.getLogger(__name__)

_BUILTIN_PROPERTIES: list[StructuralProperty] = [
    StructuralProperty(
        property_id="prop_retry_capable",
        name="retry_capable",
        category="execution_model",
        value_type=PropertyValueType.BOOL,
        source=PropertySource.STATIC,
        description="System can retry on failure",
    ),
    StructuralProperty(
        property_id="prop_repair_capable",
        name="repair_capable",
        category="execution_model",
        value_type=PropertyValueType.BOOL,
        source=PropertySource.STATIC,
        description="System can repair/self-heal on failure",
    ),
    StructuralProperty(
        property_id="prop_verification_builtin",
        name="verification_builtin",
        category="verification",
        value_type=PropertyValueType.BOOL,
        source=PropertySource.STATIC,
        description="System has built-in verification steps",
    ),
    StructuralProperty(
        property_id="prop_stateful",
        name="stateful",
        category="execution_model",
        value_type=PropertyValueType.BOOL,
        source=PropertySource.STATIC,
        description="System maintains state across executions",
    ),
    StructuralProperty(
        property_id="prop_has_failure_memory",
        name="has_failure_memory",
        category="memory",
        value_type=PropertyValueType.BOOL,
        source=PropertySource.STATIC,
        description="System records failures for future avoidance",
    ),
    # Derived properties (computed from runtime data)
    StructuralProperty(
        property_id="prop_avg_retry_count",
        name="avg_retry_count",
        category="execution_model",
        value_type=PropertyValueType.FLOAT,
        source=PropertySource.DERIVED,
        description="Average retry count across executions",
    ),
    StructuralProperty(
        property_id="prop_avg_repair_count",
        name="avg_repair_count",
        category="execution_model",
        value_type=PropertyValueType.FLOAT,
        source=PropertySource.DERIVED,
        description="Average repair attempts across executions",
    ),
    StructuralProperty(
        property_id="prop_artifact_count",
        name="artifact_count",
        category="verification",
        value_type=PropertyValueType.INT,
        source=PropertySource.DERIVED,
        description="Number of artifacts produced per execution",
    ),
]

_BUILTIN_PROFILES: list[SystemProfile] = [
    SystemProfile(
        system_id="build_project",
        system_type=SystemType.TOOL,
        properties={
            "retry_capable": False,
            "repair_capable": False,
            "verification_builtin": False,
            "stateful": False,
            "has_failure_memory": False,
        },
    ),
    SystemProfile(
        system_id="automated_build",
        system_type=SystemType.TOOL,
        properties={
            "retry_capable": True,
            "repair_capable": True,
            "verification_builtin": True,
            "stateful": True,
            "has_failure_memory": True,
        },
    ),
]


class StructuralPropertyRegistry:
    """Manages structural property definitions and system profiles.

    Thread-safe, SQLite-backed. Creates the principles database on first use.
    """

    def __init__(self, db_path: str = ""):
        if not db_path:
            data_dir = Path.home() / ".jarvis"
            data_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(data_dir / "principles.db")
        self._db_path = db_path
        self._lock = threading.Lock()
        self._init_db()
        self._seed_builtins()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock, self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS structural_properties (
                    property_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    value_type TEXT NOT NULL,
                    source TEXT NOT NULL,
                    description TEXT DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS system_profiles (
                    system_id TEXT PRIMARY KEY,
                    system_type TEXT NOT NULL,
                    properties_json TEXT NOT NULL DEFAULT '{}'
                );
            """)

    def _seed_builtins(self) -> None:
        with self._lock, self._conn() as conn:
            for prop in _BUILTIN_PROPERTIES:
                conn.execute(
                    """INSERT OR IGNORE INTO structural_properties
                       (property_id, name, category, value_type, source, description)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (prop.property_id, prop.name, prop.category,
                     prop.value_type.value, prop.source.value, prop.description),
                )
            for profile in _BUILTIN_PROFILES:
                conn.execute(
                    """INSERT OR IGNORE INTO system_profiles
                       (system_id, system_type, properties_json)
                       VALUES (?, ?, ?)""",
                    (profile.system_id, profile.system_type.value,
                     json.dumps(profile.properties)),
                )

    # ── Property CRUD ────────────────────────────────────────────

    def register_property(self, prop: StructuralProperty) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO structural_properties
                   (property_id, name, category, value_type, source, description)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (prop.property_id, prop.name, prop.category,
                 prop.value_type.value, prop.source.value, prop.description),
            )

    def get_property(self, property_id: str) -> StructuralProperty | None:
        with self._lock, self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM structural_properties WHERE property_id = ?",
                (property_id,),
            ).fetchone()
            if not row:
                return None
            return StructuralProperty(
                property_id=row["property_id"],
                name=row["name"],
                category=row["category"],
                value_type=PropertyValueType(row["value_type"]),
                source=PropertySource(row["source"]),
                description=row["description"],
            )

    def list_properties(self, category: str | None = None,
                        source: str | None = None) -> list[StructuralProperty]:
        with self._lock, self._conn() as conn:
            query = "SELECT * FROM structural_properties WHERE 1=1"
            params: list[str] = []
            if category:
                query += " AND category = ?"
                params.append(category)
            if source:
                query += " AND source = ?"
                params.append(source)
            rows = conn.execute(query, params).fetchall()
            return [
                StructuralProperty(
                    property_id=r["property_id"],
                    name=r["name"],
                    category=r["category"],
                    value_type=PropertyValueType(r["value_type"]),
                    source=PropertySource(r["source"]),
                    description=r["description"],
                )
                for r in rows
            ]

    def get_property_by_name(self, name: str) -> StructuralProperty | None:
        with self._lock, self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM structural_properties WHERE name = ?", (name,),
            ).fetchone()
            if not row:
                return None
            return StructuralProperty(
                property_id=row["property_id"],
                name=row["name"],
                category=row["category"],
                value_type=PropertyValueType(row["value_type"]),
                source=PropertySource(row["source"]),
                description=row["description"],
            )

    # ── Profile CRUD ─────────────────────────────────────────────

    def register_profile(self, profile: SystemProfile) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO system_profiles
                   (system_id, system_type, properties_json)
                   VALUES (?, ?, ?)""",
                (profile.system_id, profile.system_type.value,
                 json.dumps(profile.properties)),
            )

    def get_profile(self, system_id: str) -> SystemProfile | None:
        with self._lock, self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM system_profiles WHERE system_id = ?",
                (system_id,),
            ).fetchone()
            if not row:
                return None
            return SystemProfile(
                system_id=row["system_id"],
                system_type=SystemType(row["system_type"]),
                properties=json.loads(row["properties_json"]),
            )

    def list_profiles(self, system_type: str | None = None) -> list[SystemProfile]:
        with self._lock, self._conn() as conn:
            query = "SELECT * FROM system_profiles WHERE 1=1"
            params: list[str] = []
            if system_type:
                query += " AND system_type = ?"
                params.append(system_type)
            rows = conn.execute(query, params).fetchall()
            return [
                SystemProfile(
                    system_id=r["system_id"],
                    system_type=SystemType(r["system_type"]),
                    properties=json.loads(r["properties_json"]),
                )
                for r in rows
            ]

    def clear(self) -> None:
        """Clear all data. Used for testing."""
        with self._lock, self._conn() as conn:
            conn.execute("DELETE FROM structural_properties")
            conn.execute("DELETE FROM system_profiles")
