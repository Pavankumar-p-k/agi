"""Request/Response message types (canonical pipeline)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Request:
    text: str
    transport: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    attachments: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    identity: Any = None


@dataclass
class Response:
    text: str = ""
    error: Optional[str] = None
    data: Any = None
    metadata: dict = field(default_factory=dict)


__all__ = ["Request", "Response"]
