"""ActivityChain — lightweight chain grouping over existing scheduled activities.

Chains are NOT a new persistence layer. They are a view over existing
ScheduledActivity rows grouped by metadata["chain_id"]. The existing
depends_on field handles dependency resolution; chain status is derived
from children.

Usage:
    from core.scheduler.chain import ChainManager

    mgr = ChainManager()
    chain = mgr.create_chain("Android Project", [
        ("Research Android SDK", "research"),
        ("Build APK", "build"),
        ("Email results", "email"),
    ])
    # chain.activities = ["act_abc...", "act_def...", "act_ghi..."]
    # chain.status = "pending"
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from core.scheduler.models import ScheduledActivity
from core.scheduler.store import SchedulerStore

logger = logging.getLogger(__name__)


class ActivityChain:
    """A group of activities that form a logical chain.

    Lightweight — no persistence of its own. All data derived from
    metadata["chain_id"] on ScheduledActivity rows.
    """

    def __init__(self, chain_id: str, name: str = "",
                 activities: list[ScheduledActivity] | None = None):
        self.chain_id = chain_id
        self.name = name or chain_id
        self._activities: dict[str, ScheduledActivity] = {}
        if activities:
            for a in activities:
                if a:
                    self._activities[a.activity_id] = a

    def add(self, activity: ScheduledActivity) -> None:
        self._activities[activity.activity_id] = activity

    @property
    def activities(self) -> list[ScheduledActivity]:
        """Return activities sorted by chain_order."""
        return sorted(
            self._activities.values(),
            key=lambda a: a.metadata.get("chain_order", 999),
        )

    @property
    def activity_ids(self) -> list[str]:
        return [a.activity_id for a in self.activities]

    @property
    def status(self) -> str:
        """Derive chain status from children.

        Order: failed > completed > running > paused > pending
        """
        acts = self.activities
        if not acts:
            return "empty"
        statuses = {a.status for a in acts}
        if "failed" in statuses:
            max_failed = max(a.metadata.get("chain_order", 0)
                             for a in acts if a.status == "failed")
            # If a later activity failed but earlier ones completed, it's failed
            if all(a.status in ("completed", "cancelled", "failed")
                   for a in acts
                   if a.metadata.get("chain_order", 0) < max_failed):
                return "failed"
            # Otherwise some deps may not have run yet — still running
            return "running"
        if all(a.status == "completed" for a in acts):
            return "completed"
        if "running" in statuses:
            return "running"
        if "paused" in statuses:
            return "paused"
        if all(a.status == "pending" for a in acts):
            return "pending"
        # Mixed pending/blocked
        if "blocked" in statuses:
            return "running"  # downstream activities blocked, upstream running
        return "pending"

    @property
    def is_complete(self) -> bool:
        return self.status == "completed"

    @property
    def is_failed(self) -> bool:
        return self.status == "failed"

    @property
    def current_step(self) -> int:
        """0-based index of the first non-completed activity, or last if all done."""
        acts = self.activities
        for i, a in enumerate(acts):
            if a.status not in ("completed", "cancelled"):
                return i
        return max(len(acts) - 1, 0)

    @property
    def progress(self) -> str:
        """Human-readable progress string, e.g. '2/5 steps complete'."""
        acts = self.activities
        done = sum(1 for a in acts if a.status == "completed")
        return f"{done}/{len(acts)} steps complete" if acts else "empty"


class ChainManager:
    """Creates and queries activity chains using the existing SchedulerStore.

    Chains are purely a metadata convention:
      - metadata["chain_id"]     — groups activities
      - metadata["chain_order"]  — ordering within chain (0, 1, 2...)
      - metadata["chain_name"]   — human-readable chain name
    """

    def __init__(self, store: SchedulerStore | None = None):
        self._store = store or SchedulerStore()

    def create_chain(
        self,
        name: str,
        steps: list[tuple[str, str]],
        priority: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> ActivityChain:
        """Create a chain of dependent activities.

        Args:
            name: Human-readable chain name (used as chain_id base).
            steps: List of (goal, node_type) tuples in execution order.
            priority: Chain-level priority (applied to all activities).
            metadata: Additional metadata merged into each activity.

        Returns:
            ActivityChain with all activities populated.
        """
        chain_id = f"chain_{uuid.uuid4().hex[:12]}"
        chain_meta = {
            "chain_id": chain_id,
            "chain_name": name,
            **(metadata or {}),
        }
        prev_id: str | None = None
        activities: list[ScheduledActivity] = []

        for i, (goal, node_type) in enumerate(steps):
            aid = f"act_{uuid.uuid4().hex[:12]}"
            deps = [prev_id] if prev_id else []
            step_meta = {
                **chain_meta,
                "chain_order": i,
                "chain_step": node_type,
            }
            act = ScheduledActivity(
                activity_id=aid,
                priority=priority,
                score=50,
                status="pending",
                goal=goal,
                node_type=node_type,
                depends_on=deps,
                metadata=step_meta,
            )
            self._store.add(act)
            activities.append(act)
            prev_id = aid
            logger.debug("Chain %s: step %d (%s) → %s", chain_id, i, node_type, aid)

        return ActivityChain(chain_id, name=name, activities=activities)

    def get_chain(self, chain_id: str) -> ActivityChain | None:
        """Load a chain by ID. Returns None if no activities match."""
        all_acts = self._store.list_all()
        members = [a for a in all_acts
                   if a.metadata.get("chain_id") == chain_id]
        if not members:
            return None
        # Reconstruct name from first activity metadata
        name = members[0].metadata.get("chain_name", chain_id)
        return ActivityChain(chain_id, name=name, activities=members)

    def list_chains(self) -> list[ActivityChain]:
        """List all unique chains from the store."""
        all_acts = self._store.list_all()
        chain_map: dict[str, list[ScheduledActivity]] = {}
        for a in all_acts:
            cid = a.metadata.get("chain_id")
            if cid:
                chain_map.setdefault(cid, []).append(a)
        chains: list[ActivityChain] = []
        for cid, members in chain_map.items():
            name = members[0].metadata.get("chain_name", cid)
            chains.append(ActivityChain(cid, name=name, activities=members))
        return chains

    def delete_chain(self, chain_id: str) -> bool:
        """Cancel all pending/blocked activities in a chain. Returns True if found."""
        chain = self.get_chain(chain_id)
        if not chain:
            return False
        for act in chain.activities:
            if act.status in ("pending", "blocked"):
                self._store.update_status(act.activity_id, "cancelled")
        return True
