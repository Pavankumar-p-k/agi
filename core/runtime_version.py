"""JARVIS Runtime version (freeze marker, ADR-008)."""


class RuntimeVersion:
    MAJOR = 0
    MINOR = 1
    PATCH = 0
    STRING = "0.1.0"

    # Component versions advertised by workers / trace snapshots.
    pipeline: str = "0.1.0"
    snapshot: str = "0.1.0"

    def __init__(self, version_str: str = "0.1.0"):
        self.version_str = version_str
        self.pipeline = version_str
        self.snapshot = version_str

    def to_dict(self) -> dict:
        return {"pipeline": self.pipeline, "snapshot": self.snapshot}

    def __str__(self) -> str:
        return self.version_str

    def __repr__(self) -> str:
        return f"RuntimeVersion({self.version_str!r})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, RuntimeVersion):
            return self.version_str == other.version_str
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.version_str)


# RUNTIME_VERSION is the frozen RuntimeVersion object (trace snapshots call
# RUNTIME_VERSION.to_dict() and read .pipeline/.snapshot attributes).
RUNTIME_VERSION = RuntimeVersion()
