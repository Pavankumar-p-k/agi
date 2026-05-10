from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Protocol


@dataclass(slots=True)
class ModelRequest:
    prompt: str
    task: str = "chat"
    model: str = ""
    system: str = ""
    options: dict[str, Any] = field(default_factory=dict)


class ModelProvider(Protocol):
    name: str

    def route(self, task: str) -> str:
        ...

    def status(self) -> dict[str, Any]:
        ...

    def generate(self, request: ModelRequest) -> dict[str, Any]:
        ...

    def stream(self, request: ModelRequest) -> Iterable[dict[str, Any]]:
        ...
