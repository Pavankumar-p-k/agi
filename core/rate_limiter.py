"""core.rate_limiter — sliding-window API rate limiting.

Rebuilt from the committed contracts:

- tests/unit/test_rate_limiter.py — SlidingWindowRateLimiter
    limiter = SlidingWindowRateLimiter(max_requests=5, window_seconds=60.0,
                                       exempt_loopback=False)
    limiter.check(scope, ip) -> bool       (True = allowed; records the hit)
    limiter.remaining(scope, ip) -> int    (5 -> 4 after one check)
    loopback (127.0.0.1 / ::1) is exempt by default: check() is always True
    and remaining() stays at max_requests.
  AuthRateLimiter defaults: max_requests=10, window_seconds=300.0,
    exempt_loopback=True.
- tests/integration/test_api_auth.py::TestRateLimiter — middleware patches
    ``core.rate_limiter.api_rate_limiter.check`` returning False -> 429.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Deque, Dict, Tuple

_LOOPBACK = {"127.0.0.1", "::1", "localhost"}


class SlidingWindowRateLimiter:
    """Thread-safe per-(scope, ip) sliding-window counter."""

    def __init__(self, max_requests: int = 60, window_seconds: float = 60.0,
                 exempt_loopback: bool = True) -> None:
        self.max_requests = int(max_requests)
        self.window_seconds = float(window_seconds)
        self.exempt_loopback = bool(exempt_loopback)
        self._hits: Dict[Tuple[str, str], Deque[float]] = {}
        self._lock = threading.Lock()

    def _exempt(self, ip: str) -> bool:
        return self.exempt_loopback and ip in _LOOPBACK

    def _prune(self, key: Tuple[str, str], now: float) -> Deque[float]:
        hits = self._hits.setdefault(key, deque())
        cutoff = now - self.window_seconds
        while hits and hits[0] <= cutoff:
            hits.popleft()
        return hits

    def check(self, scope: str, ip: str) -> bool:
        """True when the request is allowed (and recorded)."""
        if self._exempt(ip):
            return True
        now = time.monotonic()
        with self._lock:
            hits = self._prune((scope, ip), now)
            if len(hits) >= self.max_requests:
                return False
            hits.append(now)
            return True

    def remaining(self, scope: str, ip: str) -> int:
        if self._exempt(ip):
            return self.max_requests
        now = time.monotonic()
        with self._lock:
            hits = self._prune((scope, ip), now)
            return max(0, self.max_requests - len(hits))


class AuthRateLimiter(SlidingWindowRateLimiter):
    """Conservative limits for auth-sensitive endpoints."""

    def __init__(self, max_requests: int = 10, window_seconds: float = 300.0,
                 exempt_loopback: bool = True) -> None:
        super().__init__(max_requests=max_requests,
                         window_seconds=window_seconds,
                         exempt_loopback=exempt_loopback)


# Used by core.main.rate_limit_middleware ("api" scope per client IP).
api_rate_limiter = SlidingWindowRateLimiter(max_requests=600, window_seconds=60.0)

__all__ = ["SlidingWindowRateLimiter", "AuthRateLimiter", "api_rate_limiter"]
