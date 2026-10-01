"""Structural property registry (Phase 14.0)."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from typing import Dict, List, Optional

from core.generalization.models import (
    PropertySource,
    PropertyValueType,
    StructuralProperty,
    SystemProfile,
    SystemType,
)


def _builtin_properties() -> List[StructuralProperty]:
    return [
        StructuralProperty("prop_retry_capable", "retry_capable",
                           "execution_model", PropertyValueType.BOOL,
                           PropertySource.STATIC),
        StructuralProperty("prop_stateful", "stateful",
                           "execution_model", PropertyValueType.BOOL,
                           PropertySource.STATIC),
        StructuralProperty("prop_verification_builtin", "verification_builtin",
                           "verification", PropertyValueType.BOOL,
                           PropertySource.STATIC),
        StructuralProperty("prop_has_failure_memory", "has_failure_memory",
                           "execution_model", PropertyValueType.BOOL,
                           PropertySource.STATIC),
        StructuralProperty("prop_artifact_count", "artifact_count",
                           "verification", PropertyValueType.FLOAT,
                           PropertySource.DERIVED),
        StructuralProperty("prop_avg_retry_count", "avg_retry_count",
                           "execution_model", PropertyValueType.FLOAT,
                           PropertySource.DERIVED),
    ]


def _builtin_profiles() -> List[SystemProfile]:
    return [
        SystemProfile("build_project", SystemType.TOOL, {
            "retry_capable": False,
            "stateful": True,
            "verification_builtin": False,
            "has_failure_memory": False,
        }),
        SystemProfile("automated_build", SystemType.TOOL, {
            "retry_capable": True,
            "stateful": True,
            "verification_builtin": True,
            "has_failure_memory": True,
        }),
    ]


class StructuralPropertyRegistry:
    """Persist structural properties and per-system profiles."""

    def __init__(self, db_path: str = "data/generalization.db") -> None:
        self.db_path = db_path
        if db_path and db_path != ":memory:":
            directory = os.path.dirname(os.path.abspath(db_path))
            if directory:
                os.makedirs(directory, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()
        self._seed_if_empty()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS gen_properties ("
                "property_id TEXT PRIMARY KEY, name TEXT, data TEXT NOT NULL)"
            )
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS gen_profiles ("
                "system_id TEXT PRIMARY KEY, data TEXT NOT NULL)"
            )
            self._conn.commit()

    def _seed_if_empty(self) -> None:
        with self._lock:
            n = self._conn.execute(
                "SELECT COUNT(*) AS n FROM gen_properties"
            ).fetchone()["n"]
        if n == 0:
            for prop in _builtin_properties():
                self.register_property(prop)
        with self._lock:
            m = self._conn.execute(
                "SELECT COUNT(*) AS n FROM gen_profiles"
            ).fetchone()["n"]
        if m == 0:
            for profile in _builtin_profiles():
                self.register_profile(profile)

    # ── properties ───────────────────────────────────────────────────

    def register_property(self, prop: StructuralProperty) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO gen_properties (property_id, name, data) "
                "VALUES (?, ?, ?)",
                (prop.property_id, prop.name, json.dumps(prop.to_dict())),
            )
            self._conn.commit()

    def get_property(self, property_id: str) -> Optional[StructuralProperty]:
        with self._lock:
            row = self._conn.execute(
                "SELECT data FROM gen_properties WHERE property_id = ?",
                (property_id,),
            ).fetchone()
        return StructuralProperty.from_dict(json.loads(row["data"])) if row else None

    def get_property_by_name(self, name: str) -> Optional[StructuralProperty]:
        with self._lock:
            row = self._conn.execute(
                "SELECT data FROM gen_properties WHERE name = ?", (name,)
            ).fetchone()
        return StructuralProperty.from_dict(json.loads(row["data"])) if row else None

    def list_properties(
        self, category: Optional[str] = None
    ) -> List[StructuralProperty]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT data FROM gen_properties"
            ).fetchall()
        props = [StructuralProperty.from_dict(json.loads(r["data"])) for r in rows]
        if category is not None:
            props = [p for p in props if p.category == category]
        return props

    # ── profiles ─────────────────────────────────────────────────────

    def register_profile(self, profile: SystemProfile) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO gen_profiles (system_id, data) "
                "VALUES (?, ?)",
                (profile.system_id, json.dumps(profile.to_dict())),
            )
            self._conn.commit()

    def get_profile(self, system_id: str) -> Optional[SystemProfile]:
        with self._lock:
            row = self._conn.execute(
                "SELECT data FROM gen_profiles WHERE system_id = ?", (system_id,)
            ).fetchone()
        return SystemProfile.from_dict(json.loads(row["data"])) if row else None

    def list_profiles(self) -> List[SystemProfile]:
        with self._lock:
            rows = self._conn.execute("SELECT data FROM gen_profiles").fetchall()
        return [SystemProfile.from_dict(json.loads(r["data"])) for r in rows]

    # ── misc ─────────────────────────────────────────────────────────

    def derived_property_names(self) -> List[str]:
        return [
            p.name for p in self.list_properties()
            if getattr(p.source, "value", p.source) == "derived"
        ]

    def clear(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM gen_properties")
            self._conn.execute("DELETE FROM gen_profiles")
            self._conn.commit()
