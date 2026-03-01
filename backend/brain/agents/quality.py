from __future__ import annotations

import re

from brain.pool import ModelPool

SYSTEM = """Score reply quality from 0.0 to 1.0 and output only the decimal number."""


class QualityAgent:
    def __init__(self, pool: ModelPool) -> None:
        self.pool = pool

    async def score(self, user_input: str, reply: str, intent: str) -> float:
        if len(reply.strip()) < 5:
            return 0.0
        raw = await self.pool.generate(
            model="phi3:mini",
            prompt=(
                f'User: "{user_input[:220]}"\n'
                f'Reply: "{reply[:420]}"\n'
                f"Intent: {intent}\n"
                "Score 0.0-1.0:"
            ),
            system=SYSTEM,
            temperature=0.1,
            max_tokens=6,
        )
        if not raw:
            return 0.7
        match = re.search(r"(\d+\.?\d*)", raw)
        if not match:
            return 0.7
        try:
            value = float(match.group(1))
            return max(0.0, min(1.0, value))
        except ValueError:
            return 0.7
