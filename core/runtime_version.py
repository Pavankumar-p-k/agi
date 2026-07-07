from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RuntimeVersion:
    pipeline: str = "1.0"
    runtime_spec: str = "1.0"
    architecture: str = "1.0"
    snapshot: str = "1.0"

    def to_dict(self) -> dict[str, str]:
        return {
            "pipeline": self.pipeline,
            "runtime_spec": self.runtime_spec,
            "architecture": self.architecture,
            "snapshot": self.snapshot,
        }


RUNTIME_VERSION = RuntimeVersion()
