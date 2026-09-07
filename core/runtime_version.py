"""JARVIS Runtime version."""
RUNTIME_VERSION = "0.1.0"

class RuntimeVersion:
    MAJOR = 0
    MINOR = 1
    PATCH = 0
    STRING = RUNTIME_VERSION

    def __init__(self, version_str: str = RUNTIME_VERSION):
        self.version_str = version_str

    def __str__(self) -> str:
        return self.version_str
