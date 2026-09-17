"""Per-client rate limits for the endpoints that hash passwords.

Every sign-in, sign-up and invite redemption costs a 600,000-iteration PBKDF2
hash, so an unthrottled client could guess passwords and tie up the API's CPU
at the same time. Attempts are counted per client address in a sliding
window, in this process's memory (the API runs as one process; render.yaml).
"""
import threading
import time
from collections import deque

from fastapi import HTTPException, Request

from core import config


class SlidingWindow:
    """At most `limit` attempts per key in any `window` seconds."""

    def __init__(self, limit: int, window: float, max_keys: int = 50_000):
        self.limit = limit
        self.window = window
        self.max_keys = max_keys
        self._hits: dict[str, deque] = {}
        self._lock = threading.Lock()

    def retry_after(self, key: str) -> int:
        """Count an attempt for `key`. Returns 0 when it is allowed, else the
        seconds until the oldest attempt in the window expires."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] >= self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return max(1, int(self.window - (now - hits[0])) + 1)
            hits.append(now)
            if len(self._hits) > self.max_keys:
                self._forget_idle(now)
            return 0

    def _forget_idle(self, now: float) -> None:
        for key in [k for k, hits in self._hits.items() if not hits or now - hits[-1] >= self.window]:
            del self._hits[key]

    def clear(self) -> None:
        with self._lock:
            self._hits.clear()


def client_address(request: Request) -> str:
    """The caller's address. Behind a proxy (Render), the last
    LUMEN_TRUSTED_PROXY_HOPS entries of X-Forwarded-For were written by
    proxies we trust, so the entry just before them is the client; anything
    further left is whatever the client chose to send."""
    hops = config.TRUSTED_PROXY_HOPS
    if hops > 0:
        forwarded = [part.strip() for part in request.headers.get("x-forwarded-for", "").split(",") if part.strip()]
        if len(forwarded) >= hops:
            return forwarded[-hops]
    return request.client.host if request.client else "unknown"


def enforce(limiter: SlidingWindow, request: Request) -> None:
    """429 with Retry-After once the caller is over `limiter`'s limit."""
    wait = limiter.retry_after(client_address(request))
    if wait:
        minutes = max(1, round(wait / 60))
        raise HTTPException(
            429,
            f"Too many attempts from your network. Try again in {minutes} minute{'' if minutes == 1 else 's'}.",
            headers={"Retry-After": str(wait)},
        )
