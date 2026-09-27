"""Pluggable object storage for documents.

An abstraction over where document bytes live, so the app is storage-agnostic:

- ``memory``  — in-process dict; used by the test suite (hermetic, no I/O).
- ``local``   — local filesystem; the dev default.
- ``s3``      — S3-compatible object storage (MinIO / AWS) for production; wired
                 when ``boto3`` is configured (documented follow-up).

Backend + location come from ``VS_STORAGE_BACKEND`` / ``VS_STORAGE_DIR`` env vars.
``get_storage`` is a FastAPI dependency so tests can override it.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class Storage(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...
    async def get(self, key: str) -> bytes: ...
    async def delete(self, key: str) -> None: ...


class MemoryStorage:
    """Hermetic in-process store (tests)."""

    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        self._store[key] = data

    async def get(self, key: str) -> bytes:
        if key not in self._store:
            raise FileNotFoundError(key)
        return self._store[key]

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)


class LocalStorage:
    """Filesystem-backed store (dev). Small-file synchronous I/O — production
    should use the S3 backend."""

    def __init__(self, base: str) -> None:
        self.base = Path(base)
        self.base.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        target = self.base / key
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        self._path(key).write_bytes(data)

    async def get(self, key: str) -> bytes:
        path = self._path(key)
        if not path.exists():
            raise FileNotFoundError(key)
        return path.read_bytes()

    async def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()


_storage: Storage | None = None


def get_storage() -> Storage:
    """Return the process-wide storage backend selected by configuration."""
    global _storage
    if _storage is None:
        backend = os.environ.get("VS_STORAGE_BACKEND", "local").lower()
        if backend == "memory":
            _storage = MemoryStorage()
        else:  # "local" default (an "s3" backend is a documented follow-up)
            base = os.environ.get("VS_STORAGE_DIR") or str(
                Path(tempfile.gettempdir()) / "vidhisangh-documents"
            )
            _storage = LocalStorage(base)
    return _storage
