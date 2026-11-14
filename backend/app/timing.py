"""Monotonic stage timer and deadline helper (plan §17.2). Server times are ``time.monotonic()`` based."""
from __future__ import annotations

import time


def now_ms() -> float:
    """Monotonic clock in milliseconds."""
    return time.monotonic() * 1000.0


class StageTimer:
    """Records named marks relative to a start instant (default: construction time)."""

    def __init__(self, start_ms: float | None = None) -> None:
        self.start_ms = now_ms() if start_ms is None else start_ms
        self.marks: dict[str, float] = {}

    def mark(self, name: str) -> float:
        """Record and return the elapsed ms since start for ``name`` (last write wins)."""
        elapsed = now_ms() - self.start_ms
        self.marks[name] = elapsed
        return elapsed

    def elapsed_ms(self) -> float:
        return now_ms() - self.start_ms


class Deadline:
    """A deadline ``budget_ms`` after ``start_ms`` (both in monotonic ms)."""

    def __init__(self, budget_ms: float, start_ms: float | None = None) -> None:
        self.start_ms = now_ms() if start_ms is None else start_ms
        self.budget_ms = budget_ms

    def remaining_ms(self) -> float:
        return self.start_ms + self.budget_ms - now_ms()

    def exceeded(self) -> bool:
        return self.remaining_ms() <= 0.0
