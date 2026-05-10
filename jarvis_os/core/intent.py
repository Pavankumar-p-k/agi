from __future__ import annotations

from typing import Any


class IntentEngine:
    def __init__(self, registry: Any) -> None:
        self.registry = registry

    def parse(self, prompt: str) -> dict[str, Any]:
        return {"goal": prompt, "type": "auto"}
