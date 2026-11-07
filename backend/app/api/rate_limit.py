"""Per-user and overall request limits for POST /v1/chat, kept in memory.

Render's free plan runs one process, so a plain in-memory sliding window is enough. The counts reset
when the service restarts or wakes from sleep, which is acceptable for a cost guard. Nothing but the
Cognito user id and timestamps is stored, never message text.
"""
import math
import threading
import time
from collections import deque

from fastapi import Depends, Request

from app.api.errors import api_error
from app.api.identity import current_user
from app.config import settings

MINUTE = 60
DAY = 24 * 60 * 60
_PRUNE_ABOVE = 5000  # users tracked before idle ones are dropped


class RateLimiter:
    def __init__(self, per_minute: int, per_day: int, global_per_day: int, clock=time.monotonic):
        self._per_minute, self._per_day, self._global_per_day = per_minute, per_day, global_per_day
        self._clock = clock
        self._lock = threading.Lock()
        self._users: dict[str, deque[float]] = {}
        self._all: deque[float] = deque()

    @staticmethod
    def _drop_old(window: deque[float], now: float) -> None:
        while window and window[0] <= now - DAY:
            window.popleft()

    def check(self, user: str) -> tuple[str, int] | None:
        """Record one request. Returns None if allowed, else (reason, seconds to wait)."""
        with self._lock:
            now = self._clock()
            self._drop_old(self._all, now)
            if len(self._all) >= self._global_per_day:
                return "busy", math.ceil(self._all[0] + DAY - now)
            hits = self._users.setdefault(user, deque())
            self._drop_old(hits, now)
            if len(hits) >= self._per_day:
                return "day", math.ceil(hits[0] + DAY - now)
            recent = [t for t in hits if t > now - MINUTE]
            if len(recent) >= self._per_minute:
                return "minute", math.ceil(recent[0] + MINUTE - now)
            hits.append(now)
            self._all.append(now)
            if len(self._users) > _PRUNE_ABOVE:
                for key in [k for k, v in self._users.items() if not v or v[-1] <= now - DAY]:
                    del self._users[key]
            return None


def build_rate_limiter() -> RateLimiter:
    return RateLimiter(
        per_minute=settings.rate_limit_per_minute(),
        per_day=settings.rate_limit_per_day(),
        global_per_day=settings.rate_limit_global_per_day(),
    )


_MESSAGES = {
    "minute": "You are sending questions too quickly. Please wait a moment and try again.",
    "day": "You have reached today's question limit. Please try again tomorrow.",
    "busy": "VitalNest has reached its daily question limit. Please try again later.",
}


def limit_chat(request: Request, identity: dict = Depends(current_user)) -> None:
    """Dependency for the chat route. Runs after sign-in is verified, so anonymous calls cost nothing."""
    limiter: RateLimiter | None = getattr(request.app.state, "rate_limiter", None)
    if limiter is None:
        return
    blocked = limiter.check(identity["sub"])
    if blocked:
        reason, wait = blocked
        error = api_error(429, "rate_limited", _MESSAGES[reason])
        error.headers = {"Retry-After": str(max(wait, 1))}
        raise error
