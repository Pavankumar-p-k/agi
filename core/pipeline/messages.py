"""Pipeline request/response message models."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Request:
    text: str = ""
    transport: str = ""
    user_id: str | None = None
    session_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, Any] = field(default_factory=dict)
    payload: Any = None
    raw_input: Any = None

    def __post_init__(self) -> None:
        self.metadata = dict(self.metadata or {})
        self.headers = dict(self.headers or {})


@dataclass
class Response:
    payload: Any = None
    status: int = 200
    headers: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.headers = dict(self.headers or {})
        self.metadata = dict(self.metadata or {})
