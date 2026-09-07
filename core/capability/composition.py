"""
Module: core.capability.composition
Composition engine for building multi-capability plans.
"""
from __future__ import annotations
from typing import Any
from dataclasses import dataclass, field
from hashlib import sha256
import logging

logger = logging.getLogger(__name__)


@dataclass
class CompositionStep:
    capability_id: str = ""
    provider_id: str = ""
    permission: dict[str, Any] = field(default_factory=dict)
    action: str = ""
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "provider_id": self.provider_id,
            "permission": self.permission,
            "action": self.action,
            "params": self.params,
        }


@dataclass
class CompositionPlan:
    steps: tuple[CompositionStep, ...] = ()
    blocked: bool = False
    subgraph_fingerprint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "steps": [s.to_dict() for s in self.steps],
            "blocked": self.blocked,
            "subgraph_fingerprint": self.subgraph_fingerprint,
        }


_TASK_CAPABILITY_MAP: dict[str, list[str]] = {
    "build app": ["coding", "filesystem"],
    "browse web": ["browser", "network"],
    "write code": ["coding", "filesystem"],
    "read file": ["filesystem"],
    "send email": ["network"],
    "search web": ["browser", "network"],
    "manage desktop": ["desktop"],
    "take screenshot": ["desktop"],
}

_TASK_CAPABILITY_PLAN: dict[str, list[dict[str, Any]]] = {
    "build app": [
        {"capability_id": "coding", "action": "compile"},
        {"capability_id": "filesystem", "action": "write_file"},
    ],
    "browse web": [
        {"capability_id": "browser", "action": "navigate"},
        {"capability_id": "network", "action": "http_request"},
    ],
    "write code": [
        {"capability_id": "coding", "action": "edit"},
        {"capability_id": "filesystem", "action": "write_file"},
    ],
    "read file": [
        {"capability_id": "filesystem", "action": "read_file"},
    ],
    "send email": [
        {"capability_id": "network", "action": "smtp_send"},
    ],
    "search web": [
        {"capability_id": "browser", "action": "search"},
        {"capability_id": "network", "action": "http_request"},
    ],
}


class CompositionEngine:
    def compose(self, task: str) -> CompositionPlan:
        task_lower = task.lower().strip()
        plan_steps = _TASK_CAPABILITY_PLAN.get(task_lower)
        if plan_steps is None:
            cap_ids = _TASK_CAPABILITY_MAP.get(task_lower, [])
            plan_steps = [{"capability_id": c, "action": "execute"} for c in cap_ids]

        if not plan_steps:
            return CompositionPlan(steps=(), blocked=False, subgraph_fingerprint="")

        steps = []
        has_deny = False
        for s in plan_steps:
            cap_id = s["capability_id"]
            from core.permission.manager import PermissionManager
            mgr = PermissionManager()
            result = mgr.resolve(cap_id)
            perm_dict = result.to_dict()
            if result.denied:
                has_deny = True
            steps.append(CompositionStep(
                capability_id=cap_id,
                provider_id="" if result.denied else cap_id,
                permission=perm_dict,
                action=s.get("action", "execute"),
            ))

        fp = sha256(task.encode()).hexdigest()[:16]
        return CompositionPlan(
            steps=tuple(steps),
            blocked=has_deny,
            subgraph_fingerprint=fp,
        )


composition_engine = CompositionEngine()
