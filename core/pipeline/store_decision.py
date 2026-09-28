"""StoreDecision — what the Memory stage decided to persist (contract)."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StoreAction(str, Enum):
    STORE = "store"
    SKIP = "skip"
    UPDATE = "update"
    MERGE = "merge"
    DELETE = "delete"
    IGNORE = "ignore"


@dataclass
class StoreDecision:
    action: StoreAction = StoreAction.SKIP
    store_type: str = ""
    reason: str = ""
    confidence: float = 0.0
    payload: Any = None
    metadata: dict = field(default_factory=dict)


__all__ = ["StoreAction", "StoreDecision"]
