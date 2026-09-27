"""A tiny in-memory stand-in for the async Redis client.

Covers the commands the app uses (rate limiter, revocation denylist, WebSocket
tickets) so those paths are exercised hermetically instead of failing open when
no Redis is listening. Expiry is honoured against ``time.monotonic``.
"""

from __future__ import annotations

import time


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.expiry: dict[str, float] = {}

    def _alive(self, key: str) -> bool:
        exp = self.expiry.get(key)
        if exp is not None and exp <= time.monotonic():
            self.store.pop(key, None)
            self.expiry.pop(key, None)
            return False
        return key in self.store

    async def ping(self) -> bool:
        return True

    async def incr(self, key: str) -> int:
        current = int(self.store[key]) + 1 if self._alive(key) else 1
        self.store[key] = str(current)
        return current

    async def expire(self, key: str, seconds: int) -> bool:
        if key in self.store:
            self.expiry[key] = time.monotonic() + seconds
            return True
        return False

    async def ttl(self, key: str) -> int:
        if not self._alive(key):
            return -2
        exp = self.expiry.get(key)
        return -1 if exp is None else max(int(exp - time.monotonic()), 0)

    async def get(self, key: str) -> str | None:
        return self.store.get(key) if self._alive(key) else None

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.store[key] = str(value)
        if ex is not None:
            self.expiry[key] = time.monotonic() + ex
        else:
            self.expiry.pop(key, None)
        return True

    async def getdel(self, key: str) -> str | None:
        value = await self.get(key)
        self.store.pop(key, None)
        self.expiry.pop(key, None)
        return value

    async def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            if key in self.store:
                removed += 1
            self.store.pop(key, None)
            self.expiry.pop(key, None)
        return removed

    async def aclose(self) -> None:
        return None
