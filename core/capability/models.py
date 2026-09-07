"""
Module: core.capability.models
Capability domain model with built-in capability registry.
"""
from __future__ import annotations
from typing import Any
from dataclasses import dataclass, field
import uuid
import logging

logger = logging.getLogger(__name__)


@dataclass
class Capability:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    version: str = "1.0.0"
    permissions: tuple[str, ...] = ()
    required_permissions: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "permissions": self.permissions,
            "required_permissions": self.required_permissions,
            "metadata": self.metadata,
        }

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Capability):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)


_BUILTIN_CAPABILITIES: dict[str, Capability] = {
    "desktop": Capability(
        id="desktop",
        name="Desktop Control",
        description="Desktop automation: mouse, keyboard, screen, window management",
        permissions=(
            "desktop.mouse.move",
            "desktop.mouse.click",
            "desktop.mouse.double_click",
            "desktop.mouse.drag",
            "desktop.keyboard.type",
            "desktop.keyboard.hotkey",
            "desktop.screen.capture",
            "desktop.screen.record",
            "desktop.window.read",
            "desktop.window.move",
            "desktop.replay.record",
            "desktop.replay.execute",
        ),
    ),
    "filesystem": Capability(
        id="filesystem",
        name="Filesystem",
        description="File system read/write operations",
        permissions=("filesystem.read", "filesystem.write", "filesystem.delete"),
    ),
    "network": Capability(
        id="network",
        name="Network",
        description="Network access",
        permissions=("network.http", "network.smtp", "network.websocket"),
    ),
    "browser": Capability(
        id="browser",
        name="Browser",
        description="Browser automation",
        permissions=("browser.tabs.read", "browser.tabs.control"),
    ),
    "coding": Capability(
        id="coding",
        name="Coding",
        description="Code editing and execution",
        permissions=("filesystem.read", "filesystem.write"),
    ),
    "system": Capability(
        id="system",
        name="System",
        description="System-level operations",
        permissions=("system.environment", "system.shell"),
    ),
    "process": Capability(
        id="process",
        name="Process",
        description="Process management",
        permissions=("process.list", "process.control"),
    ),
    "clipboard": Capability(
        id="clipboard",
        name="Clipboard",
        description="Clipboard access",
        permissions=("clipboard.read", "clipboard.write"),
    ),
}
