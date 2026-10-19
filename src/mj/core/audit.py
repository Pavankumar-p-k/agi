"""Hash-chained, append-only audit log.

Each entry hashes the previous entry's hash (genesis: 64 zeros), so any
tampering with recorded history breaks the chain. Only kernel code appends to
this log; other subsystems request audit records through this module.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from .store import Store, canonical_json

GENESIS_HASH = "0" * 64


def _entry_hash(
    prev_hash: str, ts: float, actor: str, action: str, payload_json: str
) -> str:
    blob = canonical_json(
        {
            "prev_hash": prev_hash,
            "ts": ts,
            "actor": actor,
            "action": action,
            "payload": json.loads(payload_json),
        }
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def append(store: Store, actor: str, action: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Append an audit record and return its seq and hash."""
    ts = time.time()
    prev = store.one("SELECT entry_hash FROM audit_entries ORDER BY seq DESC LIMIT 1")
    prev_hash = prev["entry_hash"] if prev else GENESIS_HASH
    payload_json = canonical_json(payload)
    entry_hash = _entry_hash(prev_hash, ts, actor, action, payload_json)
    cur = store.conn.execute(
        "INSERT INTO audit_entries (ts, actor, action, payload_json, prev_hash, entry_hash) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (ts, actor, action, payload_json, prev_hash, entry_hash),
    )
    return {"seq": int(cur.lastrowid), "entry_hash": entry_hash}


def entries(store: Store, limit: int = 100) -> list[dict[str, Any]]:
    rows = store.query(
        "SELECT seq, ts, actor, action, payload_json, prev_hash, entry_hash "
        "FROM audit_entries ORDER BY seq DESC LIMIT ?",
        (limit,),
    )
    return [dict(row) for row in rows]


def verify(store: Store) -> tuple[bool, int, str]:
    """Recompute the whole chain. Returns (ok, checked_count, problem)."""
    prev_hash = GENESIS_HASH
    count = 0
    for row in store.query(
        "SELECT seq, ts, actor, action, payload_json, prev_hash, entry_hash "
        "FROM audit_entries ORDER BY seq"
    ):
        if row["prev_hash"] != prev_hash:
            return False, count, f"entry {row['seq']} does not link to its predecessor"
        expected = _entry_hash(
            row["prev_hash"], row["ts"], row["actor"], row["action"], row["payload_json"]
        )
        if expected != row["entry_hash"]:
            return False, count, f"entry {row['seq']} hash mismatch (tampering)"
        prev_hash = row["entry_hash"]
        count += 1
    return True, count, ""
