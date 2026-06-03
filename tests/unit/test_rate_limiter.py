import time
import pytest
from core.rate_limiter import SlidingWindowRateLimiter, AuthRateLimiter


class TestSlidingWindowRateLimiter:
    def test_allows_requests_under_limit(self):
        limiter = SlidingWindowRateLimiter(max_requests=5, window_seconds=60.0, exempt_loopback=False)
        for _ in range(5):
            assert limiter.check("test", "1.2.3.4") is True

    def test_blocks_requests_over_limit(self):
        limiter = SlidingWindowRateLimiter(max_requests=3, window_seconds=60.0, exempt_loopback=False)
        for _ in range(3):
            limiter.check("test", "1.2.3.4")
        assert limiter.check("test", "1.2.3.4") is False

    def test_different_scopes_independent(self):
        limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=60.0, exempt_loopback=False)
        limiter.check("scope_a", "1.2.3.4")
        limiter.check("scope_a", "1.2.3.4")
        assert limiter.check("scope_b", "1.2.3.4") is True

    def test_different_ips_independent(self):
        limiter = SlidingWindowRateLimiter(max_requests=1, window_seconds=60.0, exempt_loopback=False)
        limiter.check("test", "1.2.3.4")
        assert limiter.check("test", "5.6.7.8") is True

    def test_loopback_exempt_by_default(self):
        limiter = SlidingWindowRateLimiter(max_requests=0, window_seconds=60.0)
        assert limiter.check("test", "127.0.0.1") is True
        assert limiter.check("test", "::1") is True

    def test_loopback_exempt_disabled(self):
        limiter = SlidingWindowRateLimiter(max_requests=0, window_seconds=60.0, exempt_loopback=False)
        assert limiter.check("test", "127.0.0.1") is False

    def test_remaining_decreases(self):
        limiter = SlidingWindowRateLimiter(max_requests=5, window_seconds=60.0, exempt_loopback=False)
        assert limiter.remaining("test", "1.2.3.4") == 5
        limiter.check("test", "1.2.3.4")
        assert limiter.remaining("test", "1.2.3.4") == 4

    def test_window_expires(self):
        limiter = SlidingWindowRateLimiter(max_requests=1, window_seconds=0.1, exempt_loopback=False)
        limiter.check("test", "1.2.3.4")
        assert limiter.check("test", "1.2.3.4") is False
        time.sleep(0.15)
        assert limiter.check("test", "1.2.3.4") is True

    def test_remaining_loopback_exempt(self):
        limiter = SlidingWindowRateLimiter(max_requests=5, window_seconds=60.0)
        assert limiter.remaining("test", "127.0.0.1") == 5
        limiter.check("test", "127.0.0.1")
        assert limiter.remaining("test", "127.0.0.1") == 5

    def test_concurrent_safety(self):
        import threading
        limiter = SlidingWindowRateLimiter(max_requests=1000, window_seconds=60.0, exempt_loopback=False)
        errors = []
        def hammer():
            try:
                for _ in range(100):
                    limiter.check("test", "1.2.3.4")
            except Exception as e:
                errors.append(e)
        threads = [threading.Thread(target=hammer) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0


class TestAuthRateLimiter:
    def test_default_limits(self):
        limiter = AuthRateLimiter()
        assert limiter.max_requests == 10
        assert limiter.window_seconds == 300.0
        assert limiter.exempt_loopback is True
