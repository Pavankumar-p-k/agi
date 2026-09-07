from __future__ import annotations

import asyncio


class RetryPolicy:
    def __init__(self, max_retries=1, backoff_seconds=0.0):
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds

    async def execute(self, fn, fallback=None):
        attempts = max(1, self.max_retries)
        for attempt in range(attempts):
            try:
                result = fn()
                return await result if asyncio.iscoroutine(result) else result
            except Exception:
                if attempt + 1 >= attempts:
                    if fallback is not None:
                        result = fallback()
                        return await result if asyncio.iscoroutine(result) else result
                    raise
                if self.backoff_seconds:
                    await asyncio.sleep(self.backoff_seconds)
