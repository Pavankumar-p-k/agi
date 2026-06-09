# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import annotations

import threading
import time
from collections import defaultdict


class SlidingWindowRateLimiter:
    """Per-{scope, client_ip} sliding-window rate limiter. Loopback exempt by default."""

    def __init__(self, max_requests: int = 60, window_seconds: float = 60.0, exempt_loopback: bool = True):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.exempt_loopback = exempt_loopback
        self._buckets: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def _key(self, scope: str, client_ip: str) -> str:
        return f"{scope}:{client_ip}"

    def check(self, scope: str, client_ip: str) -> bool:
        if self.exempt_loopback and client_ip in ("127.0.0.1", "::1", "localhost"):
            return True
        key = self._key(scope, client_ip)
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            bucket = self._buckets[key]
            bucket[:] = [t for t in bucket if t > cutoff]
            if len(bucket) >= self.max_requests:
                return False
            bucket.append(now)
        return True

    def remaining(self, scope: str, client_ip: str) -> int:
        if self.exempt_loopback and client_ip in ("127.0.0.1", "::1", "localhost"):
            return self.max_requests
        key = self._key(scope, client_ip)
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            bucket = self._buckets.get(key, [])
            bucket[:] = [t for t in bucket if t > cutoff]
            return max(0, self.max_requests - len(bucket))


class AuthRateLimiter(SlidingWindowRateLimiter):
    """Rate limiter scoped specifically to auth attempts. Lower threshold, longer window."""

    def __init__(self):
        super().__init__(max_requests=10, window_seconds=300.0, exempt_loopback=True)


auth_rate_limiter = AuthRateLimiter()
api_rate_limiter = SlidingWindowRateLimiter(max_requests=120, window_seconds=60.0)
