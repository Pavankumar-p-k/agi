from dataclasses import dataclass, field


@dataclass
class Identity:
    name: str = "JARVIS"
    capabilities: list[str] = field(default_factory=lambda: [
        "desktop_control", "task_resume", "filesystem_operations",
        "window_management", "verified_execution",
    ])


class SystemIdentity:
    def __init__(self):
        self._identity = Identity()

    def get(self) -> Identity:
        return self._identity

    def can(self, capability: str) -> bool:
        return capability in {"autonomous_build", *self._identity.capabilities}

    def get_summary(self) -> str:
        return f"{self._identity.name}: {', '.join(self._identity.capabilities)}"


system_identity = SystemIdentity()
