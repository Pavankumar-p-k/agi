"""Policy optimization result contract."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PolicyOptimizationResult:
    optimized: bool = False
    changes: dict[str, Any] = field(default_factory=dict)
    rationale: str = ""

