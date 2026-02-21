"""Tests for the sliding-window rate limiter."""

import time

import pytest

from code_extract.ai.rate_limiter import RateLimiter, get_rate_limiter


class TestRateLimiter:
    def test_allows_under_limit(self):
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        for _ in range(5):
            allowed, _ = limiter.check("key1")
            assert allowed is True

    def test_blocks_over_limit(self):
        limiter = RateLimiter(max_requests=3, window_seconds=60)
        for _ in range(3):
            limiter.check("key1")
        allowed, retry_after = limiter.check("key1")
        assert allowed is False
        assert retry_after >= 0

    def test_retry_after_positive(self):
        limiter = RateLimiter(max_requests=1, window_seconds=10)
        limiter.check("key1")
        allowed, retry_after = limiter.check("key1")
        assert allowed is False
        assert retry_after > 0

    def test_remaining(self):
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        assert limiter.remaining("key1") == 5
        limiter.check("key1")
        assert limiter.remaining("key1") == 4
        limiter.check("key1")
        assert limiter.remaining("key1") == 3

    def test_window_expiry(self):
        limiter = RateLimiter(max_requests=2, window_seconds=0.1)
        limiter.check("key1")
        limiter.check("key1")
        # Should be blocked
        allowed, _ = limiter.check("key1")
        assert allowed is False
        # Wait for window to expire
        time.sleep(0.15)
        allowed, _ = limiter.check("key1")
        assert allowed is True

    def test_per_key_isolation(self):
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        allowed1, _ = limiter.check("key1")
        allowed2, _ = limiter.check("key2")
        assert allowed1 is True
        assert allowed2 is True
        # key1 is now exhausted
        allowed1, _ = limiter.check("key1")
        assert allowed1 is False
        # key2 is also exhausted independently
        allowed2, _ = limiter.check("key2")
        assert allowed2 is False


class TestGetRateLimiter:
    def test_returns_singleton(self):
        a = get_rate_limiter()
        b = get_rate_limiter()
        assert a is b

    def test_returns_rate_limiter_instance(self):
        assert isinstance(get_rate_limiter(), RateLimiter)
