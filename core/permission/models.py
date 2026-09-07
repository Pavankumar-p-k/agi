"""
Module: core.permission.models
Permission domain models for access control, risk assessment, and audit.
"""
from __future__ import annotations
from enum import Enum
from typing import Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
import uuid
import logging

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PermissionCategory(Enum):
    DESKTOP = "desktop"
    DESKTOP_CONTROL = "desktop_control"
    SCREEN_CAPTURE = "screen_capture"
    KEYBOARD_INPUT = "keyboard_input"
    MOUSE_INPUT = "mouse_input"
    FILE_ACCESS = "file_access"
    FILESYSTEM = "filesystem"
    NETWORK = "network"
    SYSTEM = "system"
    REPLAY = "replay"
    BROWSER = "browser"
    ADMIN = "admin"


class Decision(Enum):
    ALLOW = "allow"
    DENY = "deny"
    ESCALATE = "escalate"
    CONDITIONAL = "conditional"
    NEED_CONFIRM = "need_confirm"


@dataclass
class Permission:
    name_or_id: str = ""
    name: str = ""
    id: str = ""
    category: PermissionCategory = PermissionCategory.SYSTEM
    risk_level: RiskLevel = RiskLevel.MEDIUM
    risk: RiskLevel = RiskLevel.MEDIUM
    description: str = ""
    required_capabilities: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.name and not self.name_or_id:
            self.name_or_id = self.name
        if self.name_or_id and not self.name:
            self.name = self.name_or_id
        if self.id and not self.name_or_id:
            self.name_or_id = self.id
        if self.name_or_id and not self.id:
            self.id = self.name_or_id
        self.risk = self.risk_level

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "name_or_id": self.name_or_id,
            "category": self.category.value,
            "risk_level": self.risk_level.value,
            "risk": self.risk_level.value,
            "description": self.description,
            "required_capabilities": self.required_capabilities,
            "metadata": self.metadata,
        }


ALL_PERMISSIONS: dict[str, str] = {
    "filesystem.read": "filesystem.read",
    "filesystem.write": "filesystem.write",
    "filesystem.delete": "filesystem.delete",
    "network.http": "network.http",
    "network.smtp": "network.smtp",
    "network.websocket": "network.websocket",
    "clipboard.read": "clipboard.read",
    "clipboard.write": "clipboard.write",
    "desktop.window.read": "desktop.window.read",
    "desktop.window.move": "desktop.window.move",
    "desktop.mouse.move": "desktop.mouse.move",
    "desktop.mouse.click": "desktop.mouse.click",
    "desktop.mouse.double_click": "desktop.mouse.double_click",
    "desktop.mouse.drag": "desktop.mouse.drag",
    "desktop.keyboard.type": "desktop.keyboard.type",
    "desktop.keyboard.hotkey": "desktop.keyboard.hotkey",
    "desktop.screen.capture": "desktop.screen.capture",
    "desktop.screen.record": "desktop.screen.record",
    "desktop.replay.record": "desktop.replay.record",
    "desktop.replay.execute": "desktop.replay.execute",
    "process.list": "process.list",
    "process.control": "process.control",
    "browser.tabs.read": "browser.tabs.read",
    "browser.tabs.control": "browser.tabs.control",
    "system.environment": "system.environment",
    "system.shell": "system.shell",
    "os.cmd": "os.cmd",
    "os.powershell": "os.powershell",
    "os.regedit": "os.regedit",
    "os.task_manager": "os.task_manager",
    "os.file_delete": "os.file_delete",
    "os.file_write": "os.file_write",
    "os.process_kill": "os.process_kill",
}

ALL_PERMISSIONS_SENTINEL = ALL_PERMISSIONS


@dataclass
class AuditEntry:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=lambda: __import__("time").time())
    capability_id: str = ""
    permission_id: str = ""
    permission_name: str = ""
    decision: Decision = Decision.DENY
    policy: str = ""
    requester: str = ""
    resource: str = ""
    risk_level: RiskLevel = RiskLevel.MEDIUM
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    violation: bool = False

    def __post_init__(self):
        if self.permission_name and not self.permission_id:
            self.permission_id = self.permission_name
        if self.permission_id and not self.permission_name:
            self.permission_name = self.permission_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "capability_id": self.capability_id,
            "permission_id": self.permission_id,
            "permission_name": self.permission_name,
            "decision": self.decision.value,
            "policy": self.policy,
            "requester": self.requester,
            "resource": self.resource,
            "risk_level": self.risk_level.value,
            "reason": self.reason,
            "metadata": self.metadata,
            "violation": self.violation,
        }
