"""Settings schemas for JARVIS."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class JarvisSettings:
    dev_mode: bool = False
    cors_origins: list[str] = field(default_factory=list)
    raw_config: dict[str, Any] = field(default_factory=dict)


@dataclass
class ServerSettings:
    host: str = "127.0.0.1"
    port: int = 8000
    dev_mode: bool = False
    cors_origins: list[str] = field(default_factory=list)
    allowed_origins: list[str] = field(default_factory=list)
