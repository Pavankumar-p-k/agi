from __future__ import annotations

from typing import Any


class BrainAdapter:
    """
    Bridges external callers to the canonical brain execution interface.
    """

    def __init__(self, authority_stack: Any) -> None:
        self.authority_stack = authority_stack

    async def evaluate(self, context: Any) -> dict[str, Any]:
        return await self.authority_stack.evaluate(context)
