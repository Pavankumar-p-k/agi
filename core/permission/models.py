"""Permission domain models."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Decision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    NEED_CONFIRM = "need_confirm"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PermissionCategory(str, Enum):
    FILESYSTEM = "filesystem"
    NETWORK = "network"
    DESKTOP = "desktop"
    SHELL = "shell"
    SYSTEM = "system"


@dataclass
class Permission:
    permission_id: str
    category: PermissionCategory = PermissionCategory.SYSTEM
    risk: RiskLevel = RiskLevel.LOW
    description: str = ""


@dataclass
class AuditEntry:
    capability_id: str
    permission_id: str
    decision: Decision
    policy: str
    reason: str
    timestamp: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)


ALL_PERMISSIONS: frozenset = frozenset({
    "filesystem.read", "filesystem.write",
    "network.http",
    "desktop.mouse.click", "desktop.mouse.move", "desktop.keyboard.type",
    "desktop.screen.capture", "desktop.window.focus",
    "system.shell",
})


__all__ = ["Decision", "RiskLevel", "PermissionCategory", "Permission",
           "AuditEntry", "ALL_PERMISSIONS"]
