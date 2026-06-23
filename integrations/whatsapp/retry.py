from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class AsyncRetry:
    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        backoff_factor: float = 2.0,
        jitter: bool = True,
        retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
    ):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.jitter = jitter
        self.retryable_exceptions = retryable_exceptions

    async def execute(
        self,
        fn: Callable[..., Awaitable[T]],
        *args: Any,
        on_retry: Callable[[int, Exception], None] | None = None,
        **kwargs: Any,
    ) -> tuple[T, int]:
        last_exc: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                result = await fn(*args, **kwargs)
                return result, attempt
            except self.retryable_exceptions as e:
                last_exc = e
                if attempt == self.max_attempts:
                    logger.error(f"All {self.max_attempts} attempts failed: {e}")
                    raise
                delay = self._backoff(attempt)
                if on_retry:
                    on_retry(attempt, e)
                logger.warning(f"Attempt {attempt}/{self.max_attempts} failed: {e}. Retrying in {delay:.1f}s")
                await asyncio.sleep(delay)
        raise last_exc  # type: ignore[misc]

    def _backoff(self, attempt: int) -> float:
        import random
        delay = min(self.base_delay * (self.backoff_factor ** (attempt - 1)), self.max_delay)
        if self.jitter:
            delay = delay * (0.5 + random.random() * 0.5)
        return delay
