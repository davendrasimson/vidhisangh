"""Pluggable object storage for documents.

An abstraction over where document bytes live, so the app is storage-agnostic:

- ``memory``  — in-process dict; used by the test suite (hermetic, no I/O).
                 Refused in production by :func:`assert_storage_ready`.
- ``local``   — local filesystem under ``VS_STORAGE_DIR`` (must be set; there
                 is deliberately no temp-dir default — a temp dir is world
                 readable on shared hosts and is wiped on reboot).
- ``s3``      — S3-compatible object storage (AWS S3 / MinIO) with server-side
                 encryption: SSE-KMS when ``VS_S3_KMS_KEY_ID`` is set, else
                 SSE-S3 (AES256). This is the production backend.

Backend + location come from ``settings.STORAGE_BACKEND`` / ``settings.STORAGE_DIR``
(``VS_STORAGE_BACKEND`` / ``VS_STORAGE_DIR`` in the environment). ``get_storage``
is a FastAPI dependency so tests can override it; :func:`set_storage` is the
test hook for code paths that do not go through the dependency.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from app.core.config import settings

log = logging.getLogger(__name__)

VALID_BACKENDS = ("local", "s3", "memory")


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
    """Filesystem-backed store (dev / single-host). Small-file synchronous I/O
    offloaded to a thread; production should prefer the S3 backend."""

    def __init__(self, base: str) -> None:
        self.base = Path(base).resolve()
        self.base.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        target = (self.base / key).resolve()
        # Keys are built server-side (uuid/uuid/hex) but never trust a key to
        # stay inside the store — a stray ".." must not reach the filesystem.
        if self.base not in target.parents and target != self.base:
            raise ValueError("Storage key escapes the storage directory.")
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        await asyncio.to_thread(self._path(key).write_bytes, data)

    async def get(self, key: str) -> bytes:
        path = self._path(key)
        if not path.exists():
            raise FileNotFoundError(key)
        return await asyncio.to_thread(path.read_bytes)

    async def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            await asyncio.to_thread(path.unlink)


class S3Storage:
    """S3-compatible store (AWS S3, MinIO) with server-side encryption.

    boto3 is synchronous, so every call is offloaded to a worker thread. The
    client is created once; credentials fall back to the standard AWS chain
    (instance role, env, profile) when ``VS_S3_ACCESS_KEY`` is unset.
    """

    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str | None = None,
        region: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        use_ssl: bool = True,
        kms_key_id: str | None = None,
        client: Any | None = None,
    ) -> None:
        if not bucket:
            raise RuntimeError("VS_S3_BUCKET must be set for the s3 storage backend.")
        self.bucket = bucket
        self.kms_key_id = kms_key_id or None
        if client is None:
            try:
                import boto3
                from botocore.config import Config
            except ImportError as exc:  # pragma: no cover - depends on extras
                raise RuntimeError(
                    "The s3 storage backend needs boto3: pip install 'vidhisangh-backend[storage]'."
                ) from exc
            client = boto3.client(
                "s3",
                endpoint_url=endpoint_url or None,
                region_name=region or None,
                aws_access_key_id=access_key or None,
                aws_secret_access_key=secret_key or None,
                use_ssl=use_ssl,
                config=Config(
                    signature_version="s3v4",
                    retries={"max_attempts": 3, "mode": "standard"},
                    connect_timeout=5,
                    read_timeout=30,
                ),
            )
        self._client = client

    def _sse(self) -> dict[str, str]:
        if self.kms_key_id:
            return {"ServerSideEncryption": "aws:kms", "SSEKMSKeyId": self.kms_key_id}
        return {"ServerSideEncryption": "AES256"}

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            **self._sse(),
        )

    async def get(self, key: str) -> bytes:
        try:
            obj = await asyncio.to_thread(self._client.get_object, Bucket=self.bucket, Key=key)
        except Exception as exc:
            code = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
            if code in ("NoSuchKey", "404", "NotFound"):
                raise FileNotFoundError(key) from exc
            raise
        body = obj["Body"]
        return await asyncio.to_thread(body.read)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._client.delete_object, Bucket=self.bucket, Key=key)

    def check(self) -> None:
        """Verify the bucket is reachable (startup gate). Raises on failure."""
        self._client.head_bucket(Bucket=self.bucket)


def _setting(name: str, default: Any) -> Any:
    """Typed setting with an environment fallback for settings not yet declared
    in ``Settings`` (the config module is owned elsewhere)."""
    value = getattr(settings, name, None)
    if value is None:
        value = os.environ.get(f"VS_{name}")
    return default if value in (None, "") else value


def storage_backend_name() -> str:
    return str(_setting("STORAGE_BACKEND", "local")).lower()


def build_storage() -> Storage:
    """Construct the storage backend selected by configuration (no caching)."""
    backend = storage_backend_name()
    if backend == "memory":
        return MemoryStorage()
    if backend == "local":
        base = _setting("STORAGE_DIR", None)
        if not base:
            raise RuntimeError(
                "VS_STORAGE_DIR must be set when VS_STORAGE_BACKEND=local "
                "(there is no temp-dir default; documents would be world-readable "
                "and lost on reboot)."
            )
        return LocalStorage(str(base))
    if backend == "s3":
        return S3Storage(
            bucket=str(_setting("S3_BUCKET", "")),
            endpoint_url=_setting("S3_ENDPOINT_URL", None),
            region=_setting("S3_REGION", None),
            access_key=_setting("S3_ACCESS_KEY", None),
            secret_key=_setting("S3_SECRET_KEY", None),
            use_ssl=str(_setting("S3_USE_SSL", True)).lower() not in ("0", "false", "no"),
            kms_key_id=_setting("S3_KMS_KEY_ID", None),
        )
    raise RuntimeError(
        f"Unknown VS_STORAGE_BACKEND={backend!r}; expected one of {', '.join(VALID_BACKENDS)}."
    )


_storage: Storage | None = None


def get_storage() -> Storage:
    """Return the process-wide storage backend selected by configuration."""
    global _storage
    if _storage is None:
        _storage = build_storage()
    return _storage


def set_storage(storage: Storage | None) -> None:
    """Test hook: inject a storage instance (``None`` resets to configuration)."""
    global _storage
    _storage = storage


def assert_storage_ready() -> None:
    """Startup gate: refuse a configuration that would lose or expose documents.

    Called from the application lifespan. In production the ``memory`` backend
    is refused outright (bytes vanish on restart), ``local`` needs an existing,
    writable ``VS_STORAGE_DIR``, and ``s3`` must be able to reach its bucket.
    Outside production it only validates the selection so a misconfigured dev
    box fails on the first upload, not at boot.
    """
    backend = storage_backend_name()
    if backend not in VALID_BACKENDS:
        raise RuntimeError(
            f"Unknown VS_STORAGE_BACKEND={backend!r}; expected one of {', '.join(VALID_BACKENDS)}."
        )
    if backend == "local" and not _setting("STORAGE_DIR", None):
        raise RuntimeError(
            "VS_STORAGE_DIR must be set when VS_STORAGE_BACKEND=local "
            "(there is no temp-dir default; documents would be world-readable "
            "and lost on reboot)."
        )
    if not settings.is_production:
        return
    if backend == "memory":
        raise RuntimeError(
            "VS_STORAGE_BACKEND=memory is not allowed in production: "
            "uploaded documents would be lost on restart."
        )
    if backend == "local":
        path = Path(str(_setting("STORAGE_DIR", "")))
        if not path.is_dir():
            raise RuntimeError(f"VS_STORAGE_DIR={path} does not exist or is not a directory.")
        if not os.access(path, os.W_OK):
            raise RuntimeError(f"VS_STORAGE_DIR={path} is not writable by the service user.")
        log.warning(
            "storage: local filesystem backend in production — bytes are not encrypted "
            "at rest by the application; use disk encryption and back up VS_STORAGE_DIR."
        )
        return
    storage = get_storage()
    if isinstance(storage, S3Storage):
        try:
            storage.check()
        except Exception as exc:
            raise RuntimeError(f"S3 bucket {storage.bucket!r} is not reachable: {exc}") from exc
