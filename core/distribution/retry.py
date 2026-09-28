"""RetryPolicy — bounded retries with optional fallback."""
from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Any, Callable, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_SECONDS = 0.5


class RetryPolicy:
    """Runs an async callable with bounded retries and a fallback."""

    def __init__(self, max_retries: int = DEFAULT_MAX_RETRIES,
                 backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
                 retry_on: Tuple[type, ...] = (Exception,)) -> None:
        self.max_retries = max(1, int(max_retries))
        self.backoff_seconds = float(backoff_seconds)
        self.retry_on = retry_on or (Exception,)
        self.last_error: Optional[BaseException] = None
        self.attempts: int = 0

    async def execute(self, fn: Callable, *args: Any,
                      fallback: Optional[Callable] = None, **kwargs: Any) -> Any:
        """Call ``fn`` up to ``max_retries`` times, then ``fallback``.

        Raises the last error when every attempt failed and no fallback was
        supplied.
        """
        self.attempts = 0
        self.last_error = None
        for attempt in range(self.max_retries):
            self.attempts = attempt + 1
            try:
                result = fn(*args, **kwargs)
                if inspect.isawaitable(result):
                    result = await result
                return result
            except self.retry_on as exc:  # noqa: PERF203 — retry loop
                self.last_error = exc
                logger.debug("attempt %d/%d failed: %s",
                             attempt + 1, self.max_retries, exc)
                if attempt + 1 < self.max_retries and self.backoff_seconds:
                    await asyncio.sleep(self.backoff_seconds)

        if fallback is not None:
            result = fallback()
            if inspect.isawaitable(result):
                result = await result
            return result
        if self.last_error is not None:
            raise self.last_error
        raise RuntimeError("retry policy exhausted without an error")  # pragma: no cover


__all__ = ["RetryPolicy", "DEFAULT_MAX_RETRIES", "DEFAULT_BACKOFF_SECONDS"]
