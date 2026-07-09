from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from core.distribution.contracts import WorkerResponse

logger = logging.getLogger(__name__)


@dataclass
class RetryPolicy:
    """Configurable retry behaviour for remote worker dispatch."""

    max_retries: int = 3
    backoff_seconds: float = 1.0
    backoff_multiplier: float = 2.0

    async def execute(
        self,
        fn: Callable[[], Any],
        fallback: Callable[[], Any] | None = None,
    ) -> Any:
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                return await fn()
            except Exception as exc:
                last_error = exc
                logger.warning("Remote execution attempt %d/%d failed: %s",
                                attempt, self.max_retries, exc)
                if attempt < self.max_retries:
                    wait = self.backoff_seconds * (self.backoff_multiplier ** (attempt - 1))
                    await asyncio.sleep(wait)

        if fallback is not None:
            logger.info("All remote attempts failed, falling back to local")
            return await fallback()

        raise last_error or RuntimeError("All retry attempts exhausted")
