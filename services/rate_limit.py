"""Лёгкий антиспам с ограниченным потреблением памяти."""

from __future__ import annotations

import math
import time
from collections import OrderedDict, deque
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RateDecision:
    allowed: bool
    retry_after: int = 0


class RateLimiter:
    def __init__(
        self,
        *,
        window_seconds: int,
        max_messages: int,
        min_interval_seconds: float,
        max_tracked_users: int,
        warning_cooldown_seconds: int,
    ) -> None:
        self._window = max(1, window_seconds)
        self._max_messages = max(1, max_messages)
        self._min_interval = max(0.0, min_interval_seconds)
        self._max_users = max(1, max_tracked_users)
        self._warning_cooldown = max(1, warning_cooldown_seconds)
        self._history: OrderedDict[int, deque[float]] = OrderedDict()
        self._last_warning: OrderedDict[int, float] = OrderedDict()

    def allow(self, user_id: int, *, is_album: bool = False) -> RateDecision:
        now = time.monotonic()
        times = self._history.get(user_id)
        if times is None:
            if len(self._history) >= self._max_users:
                self._history.popitem(last=False)
            times = deque()
            self._history[user_id] = times
        else:
            self._history.move_to_end(user_id)

        cutoff = now - self._window
        while times and times[0] <= cutoff:
            times.popleft()

        if len(times) >= self._max_messages:
            retry_after = max(1, math.ceil(times[0] + self._window - now))
            return RateDecision(False, retry_after)

        if not is_album and self._min_interval > 0 and times:
            elapsed = now - times[-1]
            if elapsed < self._min_interval:
                retry_after = max(1, math.ceil(self._min_interval - elapsed))
                return RateDecision(False, retry_after)

        times.append(now)
        return RateDecision(True)

    def warning_due(self, user_id: int) -> bool:
        now = time.monotonic()
        last = self._last_warning.get(user_id)
        if last is not None and now - last < self._warning_cooldown:
            return False
        if len(self._last_warning) >= self._max_users:
            self._last_warning.popitem(last=False)
        self._last_warning[user_id] = now
        self._last_warning.move_to_end(user_id)
        return True


class NoticeThrottle:
    """Не даёт заблокированному пользователю заваливать чат уведомлениями."""

    def __init__(self, cooldown_seconds: int = 60, max_users: int = 10_000) -> None:
        self._cooldown = max(1, cooldown_seconds)
        self._max_users = max(1, max_users)
        self._last: OrderedDict[int, float] = OrderedDict()

    def allow(self, user_id: int) -> bool:
        now = time.monotonic()
        last = self._last.get(user_id)
        if last is not None and now - last < self._cooldown:
            return False
        if len(self._last) >= self._max_users:
            self._last.popitem(last=False)
        self._last[user_id] = now
        self._last.move_to_end(user_id)
        return True
