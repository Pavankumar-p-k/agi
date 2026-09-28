"""Capability domain models (capability-addressed execution layer)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple

from core.permission.models import ALL_PERMISSIONS


@dataclass
class Capability:
    """A capability: what the system can do, addressed by id + version."""
    id: str
    version: int = 1
    description: str = ""
    tags: Tuple[str, ...] = ()
    permissions: Tuple[str, ...] = ()
    metadata: dict = field(default_factory=dict)


def _cap(cid: str, description: str, permissions: Tuple[str, ...] = (),
         tags: Tuple[str, ...] = ()) -> Capability:
    # Only declare permissions that the permission model knows about.
    safe = tuple(p for p in permissions if p in ALL_PERMISSIONS)
    return Capability(id=cid, description=description,
                      permissions=safe, tags=tags)


# Built-in capabilities every deployment exposes, keyed by capability id.
_BUILTIN_CAPABILITIES: dict = {
    "chat": _cap("chat", "Conversational interaction with the user"),
    "coding": _cap("coding", "Read, write and refactor code in the workspace",
                   ("filesystem.read", "filesystem.write"),
                   ("code", "filesystem")),
    "research": _cap("research", "Search and gather information from the web",
                     ("network.http",), ("web", "network")),
    "testing": _cap("testing", "Run and report on test suites",
                    ("filesystem.read",), ("test",)),
    "deployment": _cap("deployment", "Build, release and deploy artifacts",
                       ("system.shell",), ("deploy", "shell")),
    "documentation": _cap("documentation", "Generate and maintain documentation",
                          ("filesystem.read",), ("docs",)),
    "review": _cap("review", "Review code and provide findings",
                   ("filesystem.read",), ("review",)),
    "security": _cap("security", "Security analysis and hardening",
                     ("filesystem.read",), ("security",)),
    "desktop": _cap("desktop", "Control the desktop: mouse, keyboard, screen, windows",
                    ("desktop.mouse.move", "desktop.mouse.click",
                     "desktop.keyboard.type", "desktop.screen.capture",
                     "desktop.window.focus"),
                    ("desktop", "gui")),
    "browser": _cap("browser", "Automated web browsing and interaction",
                    ("network.http",), ("browser", "web")),
}

# Convenience: builtin capability ids in declaration order.
BUILTIN_CAPABILITY_IDS: Tuple[str, ...] = tuple(_BUILTIN_CAPABILITIES.keys())


@dataclass
class CapabilityNode:
    """A node in the capability graph referencing a capability."""
    capability_id: str
    version: int = 1
    metadata: dict = field(default_factory=dict)


@dataclass
class Subgraph:
    """Resolved goal -> nodes + deterministic fingerprint."""
    nodes: list = field(default_factory=list)
    fingerprint: str = ""

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Subgraph):
            return self.fingerprint == other.fingerprint
        return NotImplemented


__all__ = ["Capability", "CapabilityNode", "Subgraph",
           "_BUILTIN_CAPABILITIES", "BUILTIN_CAPABILITY_IDS"]
