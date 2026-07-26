"""Simple in-memory rate limiters for auth endpoints."""

from __future__ import annotations

import threading
import time
from collections import defaultdict


class ExchangeRateLimiter:
    """Per-IP limits for /api/auth/exchange: request window + failure backoff."""

    def __init__(
        self,
        *,
        max_attempts: int = 10,
        window_seconds: float = 60.0,
        max_failures: int = 5,
        failure_window_seconds: float = 300.0,
        failure_backoff_seconds: float = 60.0,
    ) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.max_failures = max_failures
        self.failure_window_seconds = failure_window_seconds
        self.failure_backoff_seconds = failure_backoff_seconds
        self._lock = threading.Lock()
        self._attempts: dict[str, list[float]] = defaultdict(list)
        self._failures: dict[str, list[float]] = defaultdict(list)
        self._blocked_until: dict[str, float] = {}

    def _prune(self, times: list[float], now: float, window: float) -> list[float]:
        cutoff = now - window
        return [t for t in times if t >= cutoff]

    def check(self, ip: str) -> str | None:
        """Return a rejection reason, or None if the request may proceed."""
        now = time.monotonic()
        with self._lock:
            blocked = self._blocked_until.get(ip, 0.0)
            if now < blocked:
                return "Too many failed sign-in attempts. Try again in a minute."

            attempts = self._prune(self._attempts[ip], now, self.window_seconds)
            if len(attempts) >= self.max_attempts:
                self._attempts[ip] = attempts
                return "Too many sign-in attempts. Slow down and try again."
            attempts.append(now)
            self._attempts[ip] = attempts
            return None

    def record_failure(self, ip: str) -> None:
        now = time.monotonic()
        with self._lock:
            failures = self._prune(
                self._failures[ip], now, self.failure_window_seconds
            )
            failures.append(now)
            self._failures[ip] = failures
            if len(failures) >= self.max_failures:
                self._blocked_until[ip] = now + self.failure_backoff_seconds

    def reset(self) -> None:
        with self._lock:
            self._attempts.clear()
            self._failures.clear()
            self._blocked_until.clear()


exchange_limiter = ExchangeRateLimiter()
