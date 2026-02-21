"""Sliding-window rate limiter for AI API endpoints."""

from __future__ import annotations

import threading
import time
from collections import defaultdict

_instance = None
_lock = threading.Lock()


class RateLimiter:
    """Per-key sliding window rate limiter.

    Args:
        max_requests: Maximum requests allowed within the window.
        window_seconds: Size of the sliding window in seconds.
    """

    def __init__(self, max_requests: int = 30, window_seconds: float = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._timestamps: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def check(self, key: str) -> tuple[bool, float]:
        """Check if a request is allowed for the given key.

        Returns:
            ``(allowed, retry_after)`` — if not allowed, ``retry_after``
            is the number of seconds until the next slot opens.
        """
        now = time.monotonic()
        with self._lock:
            ts = self._timestamps[key]
            # Prune expired timestamps
            cutoff = now - self.window_seconds
            self._timestamps[key] = ts = [t for t in ts if t > cutoff]

            if len(ts) < self.max_requests:
                ts.append(now)
                return True, 0.0

            # Oldest timestamp determines when next slot opens
            retry_after = ts[0] - cutoff
            return False, max(0.0, retry_after)

    def remaining(self, key: str) -> int:
        """Return how many requests remain in the current window."""
        now = time.monotonic()
        with self._lock:
            cutoff = now - self.window_seconds
            ts = [t for t in self._timestamps[key] if t > cutoff]
            return max(0, self.max_requests - len(ts))


def get_rate_limiter() -> RateLimiter:
    """Module-level singleton."""
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = RateLimiter()
    return _instance
