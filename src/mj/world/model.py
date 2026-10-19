"""Fact records in the one state store.

A fact is {scope, key, value, source, observed_at, ttl_seconds, label}.
Reading a fact never refreshes it; readers get the honest label, including
``stale`` once the TTL has passed. Probes refresh facts on schedule or before
high-impact use (plan failure mode 5).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from mj.core import audit
from mj.core.store import Store, canonical_json

LABELS = ("verified", "reported", "stale")


@dataclass(frozen=True)
class Fact:
    scope: str
    key: str
    value: Any
    source: str
    ttl_seconds: float = 0.0
    label: str = "verified"  # verified | reported | stale
    observed_at: float | None = None  # set at save/refresh time when None


def save(
    store: Store,
    scope: str,
    key: str,
    value: Any,
    source: str,
    ttl_seconds: float,
    label: str = "verified",
    observed_at: float | None = None,
) -> Fact:
    """Upsert one fact (latest observation wins; history lives in the event log)."""
    if label not in LABELS:
        raise ValueError(f"unknown fact label {label!r}")
    observed_at = observed_at if observed_at is not None else time.time()
    store.conn.execute(
        "INSERT INTO facts (scope, key, value_json, source, observed_at, ttl_seconds, label) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(scope, key) DO UPDATE SET "
        "value_json=excluded.value_json, source=excluded.source, "
        "observed_at=excluded.observed_at, ttl_seconds=excluded.ttl_seconds, "
        "label=excluded.label",
        (scope, key, canonical_json(value), source, observed_at, ttl_seconds, label),
    )
    return Fact(scope, key, value, source, observed_at, ttl_seconds, label)


def get(store: Store, scope: str, key: str, as_of: float | None = None) -> Fact | None:
    """Fetch one fact with its honest label; expired facts read as ``stale``."""
    row = store.one("SELECT * FROM facts WHERE scope = ? AND key = ?", (scope, key))
    if row is None:
        return None
    now = as_of if as_of is not None else time.time()
    label = row["label"]
    if label != "stale" and now > row["observed_at"] + row["ttl_seconds"]:
        label = "stale"
    return Fact(
        scope=row["scope"],
        key=row["key"],
        value=json.loads(row["value_json"]),
        source=row["source"],
        observed_at=row["observed_at"],
        ttl_seconds=row["ttl_seconds"],
        label=label,
    )


def list_all(store: Store, scope: str | None = None, as_of: float | None = None) -> list[Fact]:
    sql = "SELECT * FROM facts"
    params: tuple = ()
    if scope is not None:
        sql += " WHERE scope = ?"
        params = (scope,)
    sql += " ORDER BY scope, key"
    now = as_of if as_of is not None else time.time()
    out = []
    for row in store.query(sql, params):
        label = row["label"]
        if label != "stale" and now > row["observed_at"] + row["ttl_seconds"]:
            label = "stale"
        out.append(
            Fact(
                scope=row["scope"],
                key=row["key"],
                value=json.loads(row["value_json"]),
                source=row["source"],
                observed_at=row["observed_at"],
                ttl_seconds=row["ttl_seconds"],
                label=label,
            )
        )
    return out


def refresh(store: Store, facts: list[Fact], actor: str = "probe") -> int:
    """Persist probe results and audit the refresh."""
    now = time.time()
    for f in facts:
        save(store, f.scope, f.key, f.value, f.source, f.ttl_seconds, f.label, f.observed_at if f.observed_at is not None else now)
    if facts:
        audit.append(
            store,
            actor,
            "world.refresh",
            {"scopes": sorted({f.scope for f in facts}), "count": len(facts)},
        )
    return len(facts)
