from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class Message:
    text: str
    user_id: str = "pavan"
    image_b64: str = ""
    platform: str = "chat"
    session: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class BrainResult:
    reply: str
    model_used: str
    intent: str
    emotion: str
    confidence: float
    latency_ms: int
    retried: bool = False
    cached: bool = False
