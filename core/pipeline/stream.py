"""Pipeline streaming event contract."""
from dataclasses import dataclass


@dataclass(frozen=True)
class StreamEvent:
    event_type: str
    stage: str | None = None
    data: dict | None = None
    error: str | None = None
