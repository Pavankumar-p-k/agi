"""Capability registry: the one registry of everything MJ can do.

A capability's manifest is validated before registration. The planner may only
reference capabilities present here (plan failure mode 4), and only ones with
status ``healthy``. Wrapped components register behind manifests too; they do
not replace this registry.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from .audit import append as audit_append
from .store import Store, canonical_json

RISK_CLASSES = ("R0", "R1", "R2", "R3", "R4")
CAPABILITY_TYPES = ("mcp", "cli", "http", "os", "agent", "browser", "skill")
STATUSES = ("candidate", "quarantined", "testing", "healthy", "degraded", "retired")

# Legal status changes; anything else must go through promotion/rollback flows.
STATUS_TRANSITIONS: dict[str, set[str]] = {
    "candidate": {"testing", "retired"},
    "quarantined": {"testing", "retired"},
    "testing": {"healthy", "candidate", "retired"},
    "healthy": {"degraded", "retired"},
    "degraded": {"healthy", "retired"},
    "retired": set(),
}


class RegistryError(ValueError):
    """Raised when a manifest is malformed or a transition is illegal."""


@dataclass
class Manifest:
    id: str
    type: str
    version: str
    source: str  # builtin | vetted-repo | generated | ...
    risk_class: str
    description: str
    requires_scopes: list[str] = field(default_factory=list)
    has_verifier: bool = False
    has_undo: bool = False
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "version": self.version,
            "source": self.source,
            "risk_class": self.risk_class,
            "description": self.description,
            "requires_scopes": self.requires_scopes,
            "has_verifier": self.has_verifier,
            "has_undo": self.has_undo,
            "provenance": self.provenance,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Manifest":
        return cls(
            id=data["id"],
            type=data["type"],
            version=data["version"],
            source=data["source"],
            risk_class=data["risk_class"],
            description=data["description"],
            requires_scopes=list(data.get("requires_scopes", [])),
            has_verifier=bool(data.get("has_verifier", False)),
            has_undo=bool(data.get("has_undo", False)),
            provenance=dict(data.get("provenance", {})),
        )


def validate_manifest(m: Manifest) -> None:
    if not m.id or not m.id.replace("-", "").replace(".", "").isalnum():
        raise RegistryError(f"manifest id {m.id!r} is malformed")
    if m.type not in CAPABILITY_TYPES:
        raise RegistryError(f"manifest {m.id}: unknown capability type {m.type!r}")
    if m.risk_class not in RISK_CLASSES:
        raise RegistryError(f"manifest {m.id}: risk class {m.risk_class!r} is not one of {RISK_CLASSES}")
    if not m.version:
        raise RegistryError(f"manifest {m.id}: version is required")


def register(store: Store, manifest: Manifest, status: str = "candidate", actor: str = "kernel") -> None:
    """Idempotent registration; bumps version on re-registration."""
    validate_manifest(manifest)
    if status not in STATUSES:
        raise RegistryError(f"unknown capability status {status!r}")
    now = time.time()
    existing = store.one("SELECT manifest_json, status FROM capabilities WHERE id = ?", (manifest.id,))
    if existing is None:
        store.conn.execute(
            "INSERT INTO capabilities (id, manifest_json, status, registered_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (manifest.id, canonical_json(manifest.to_dict()), status, now, now),
        )
        audit_append(store, actor, "registry.register", {"id": manifest.id, "status": status})
    else:
        old = json.loads(existing["manifest_json"])
        if old == manifest.to_dict() and existing["status"] == status:
            return  # same version already registered; nothing to do
        store.conn.execute(
            "UPDATE capabilities SET manifest_json = ?, status = ?, updated_at = ? WHERE id = ?",
            (canonical_json(manifest.to_dict()), status, now, manifest.id),
        )
        audit_append(store, actor, "registry.update", {"id": manifest.id, "status": status})


def set_status(store: Store, capability_id: str, new_status: str, actor: str = "kernel") -> None:
    row = store.one("SELECT status FROM capabilities WHERE id = ?", (capability_id,))
    if row is None:
        raise RegistryError(f"unknown capability {capability_id!r}")
    current = row["status"]
    if new_status == current:
        return
    if new_status not in STATUS_TRANSITIONS.get(current, set()):
        raise RegistryError(f"illegal status transition {current!r} -> {new_status!r} for {capability_id!r}")
    store.conn.execute(
        "UPDATE capabilities SET status = ?, updated_at = ? WHERE id = ?",
        (new_status, time.time(), capability_id),
    )
    audit_append(store, actor, "registry.status", {"id": capability_id, "from": current, "to": new_status})


def mark_verified(store: Store, capability_id: str, actor: str = "verifier") -> None:
    row = store.one("SELECT id FROM capabilities WHERE id = ?", (capability_id,))
    if row is None:
        raise RegistryError(f"unknown capability {capability_id!r}")
    store.conn.execute(
        "UPDATE capabilities SET last_verified = ?, updated_at = ? WHERE id = ?",
        (time.time(), time.time(), capability_id),
    )
    audit_append(store, actor, "registry.verified", {"id": capability_id})


def get(store: Store, capability_id: str) -> tuple[Manifest, str] | None:
    """Return (manifest, status) or None if not registered."""
    row = store.one(
        "SELECT manifest_json, status, last_verified FROM capabilities WHERE id = ?",
        (capability_id,),
    )
    if row is None:
        return None
    return Manifest.from_dict(json.loads(row["manifest_json"])), row["status"]


def list_all(store: Store, healthy_only: bool = False) -> list[dict[str, Any]]:
    sql = "SELECT id, manifest_json, status, last_verified FROM capabilities"
    sql += " WHERE status = 'healthy'" if healthy_only else ""
    sql += " ORDER BY id"
    out = []
    for row in store.query(sql):
        m = json.loads(row["manifest_json"])
        out.append(
            {
                "id": row["id"],
                "type": m["type"],
                "risk_class": m["risk_class"],
                "status": row["status"],
                "last_verified": row["last_verified"],
            }
        )
    return out
