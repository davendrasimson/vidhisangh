"""Storage backends (memory / local / S3 with a fake client) and the startup gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core import storage as storage_mod
from app.core.storage import (
    LocalStorage,
    MemoryStorage,
    S3Storage,
    assert_storage_ready,
    build_storage,
)


class FakeS3Client:
    """Just enough of boto3's S3 client for the backend, recording every call."""

    def __init__(self, *, exists: bool = True) -> None:
        self.objects: dict[tuple[str, str], dict] = {}
        self.calls: list[tuple[str, dict]] = []
        self.exists = exists

    def put_object(self, **kw):
        self.calls.append(("put_object", kw))
        self.objects[(kw["Bucket"], kw["Key"])] = kw
        return {}

    def get_object(self, **kw):
        self.calls.append(("get_object", kw))
        obj = self.objects.get((kw["Bucket"], kw["Key"]))
        if obj is None:
            exc = Exception("NoSuchKey")
            exc.response = {"Error": {"Code": "NoSuchKey"}}  # type: ignore[attr-defined]
            raise exc

        class _Body:
            def __init__(self, data: bytes) -> None:
                self._d = data

            def read(self) -> bytes:
                return self._d

        return {"Body": _Body(obj["Body"])}

    def delete_object(self, **kw):
        self.calls.append(("delete_object", kw))
        self.objects.pop((kw["Bucket"], kw["Key"]), None)
        return {}

    def head_bucket(self, **kw):
        self.calls.append(("head_bucket", kw))
        if not self.exists:
            raise Exception("404 Not Found")
        return {}


async def test_memory_roundtrip_and_delete() -> None:
    s = MemoryStorage()
    await s.put("t/d/1", b"abc", "text/plain")
    assert await s.get("t/d/1") == b"abc"
    await s.delete("t/d/1")
    with pytest.raises(FileNotFoundError):
        await s.get("t/d/1")
    await s.delete("t/d/1")  # idempotent


async def test_local_roundtrip_delete_and_no_escape(tmp_path: Path) -> None:
    s = LocalStorage(str(tmp_path / "docs"))
    await s.put("tenant/doc/v1", b"bytes", "application/pdf")
    assert (tmp_path / "docs" / "tenant" / "doc" / "v1").read_bytes() == b"bytes"
    assert await s.get("tenant/doc/v1") == b"bytes"
    await s.delete("tenant/doc/v1")
    assert not (tmp_path / "docs" / "tenant" / "doc" / "v1").exists()
    with pytest.raises(FileNotFoundError):
        await s.get("tenant/doc/v1")
    with pytest.raises(ValueError):
        await s.get("../../etc/passwd")


async def test_s3_uses_sse_s3_by_default_and_kms_when_configured() -> None:
    fake = FakeS3Client()
    s = S3Storage(bucket="b", client=fake)
    await s.put("k", b"data", "application/pdf")
    name, kw = fake.calls[-1]
    assert name == "put_object"
    assert kw["ServerSideEncryption"] == "AES256"
    assert kw["ContentType"] == "application/pdf"
    assert await s.get("k") == b"data"
    await s.delete("k")
    with pytest.raises(FileNotFoundError):
        await s.get("k")

    kms = S3Storage(bucket="b", client=FakeS3Client(), kms_key_id="arn:aws:kms:ap-south-1:1:key/x")
    await kms.put("k", b"data", "application/pdf")
    kw = kms._client.calls[-1][1]
    assert kw["ServerSideEncryption"] == "aws:kms"
    assert kw["SSEKMSKeyId"] == "arn:aws:kms:ap-south-1:1:key/x"


def test_s3_backend_is_built_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """build_storage() wires boto3 with the configured endpoint/region/creds."""
    captured: dict = {}

    class _Boto3:
        @staticmethod
        def client(service: str, **kw):
            captured["service"] = service
            captured.update(kw)
            return FakeS3Client()

    import sys
    import types

    botocore = types.ModuleType("botocore")
    botocore_config = types.ModuleType("botocore.config")

    class Config:
        def __init__(self, **kw) -> None:
            self.kw = kw

    botocore_config.Config = Config  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "boto3", _Boto3)
    monkeypatch.setitem(sys.modules, "botocore", botocore)
    monkeypatch.setitem(sys.modules, "botocore.config", botocore_config)

    monkeypatch.setenv("VS_STORAGE_BACKEND", "s3")
    monkeypatch.setattr(storage_mod.settings, "S3_ENDPOINT_URL", "http://minio:9000", raising=False)
    monkeypatch.setattr(storage_mod.settings, "S3_REGION", "ap-south-1", raising=False)
    monkeypatch.setattr(storage_mod.settings, "S3_BUCKET", "vidhisangh-documents", raising=False)
    monkeypatch.setattr(storage_mod.settings, "S3_ACCESS_KEY", "ak", raising=False)
    monkeypatch.setattr(storage_mod.settings, "S3_SECRET_KEY", "sk", raising=False)
    monkeypatch.setattr(storage_mod.settings, "S3_USE_SSL", False, raising=False)
    monkeypatch.delattr(storage_mod.settings, "STORAGE_BACKEND", raising=False)

    s = build_storage()
    assert isinstance(s, S3Storage)
    assert captured["service"] == "s3"
    assert captured["endpoint_url"] == "http://minio:9000"
    assert captured["region_name"] == "ap-south-1"
    assert captured["aws_access_key_id"] == "ak"
    assert captured["use_ssl"] is False
    assert s.bucket == "vidhisangh-documents"


def test_local_backend_requires_storage_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VS_STORAGE_BACKEND", "local")
    monkeypatch.delenv("VS_STORAGE_DIR", raising=False)
    monkeypatch.delattr(storage_mod.settings, "STORAGE_BACKEND", raising=False)
    monkeypatch.delattr(storage_mod.settings, "STORAGE_DIR", raising=False)
    with pytest.raises(RuntimeError, match="VS_STORAGE_DIR"):
        build_storage()
    with pytest.raises(RuntimeError, match="VS_STORAGE_DIR"):
        assert_storage_ready()


def test_unknown_backend_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VS_STORAGE_BACKEND", "gcs")
    monkeypatch.delattr(storage_mod.settings, "STORAGE_BACKEND", raising=False)
    with pytest.raises(RuntimeError, match="Unknown VS_STORAGE_BACKEND"):
        assert_storage_ready()


def test_production_gate_refuses_memory_and_missing_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(type(storage_mod.settings), "is_production", property(lambda self: True))
    monkeypatch.delattr(storage_mod.settings, "STORAGE_BACKEND", raising=False)
    monkeypatch.delattr(storage_mod.settings, "STORAGE_DIR", raising=False)

    monkeypatch.setenv("VS_STORAGE_BACKEND", "memory")
    with pytest.raises(RuntimeError, match="memory"):
        assert_storage_ready()

    monkeypatch.setenv("VS_STORAGE_BACKEND", "local")
    monkeypatch.setenv("VS_STORAGE_DIR", str(tmp_path / "missing"))
    with pytest.raises(RuntimeError, match="does not exist"):
        assert_storage_ready()

    monkeypatch.setenv("VS_STORAGE_DIR", str(tmp_path))
    assert_storage_ready()  # existing, writable directory passes


def test_production_gate_checks_s3_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(type(storage_mod.settings), "is_production", property(lambda self: True))
    monkeypatch.delattr(storage_mod.settings, "STORAGE_BACKEND", raising=False)
    monkeypatch.setenv("VS_STORAGE_BACKEND", "s3")
    storage_mod.set_storage(S3Storage(bucket="b", client=FakeS3Client(exists=False)))
    try:
        with pytest.raises(RuntimeError, match="not reachable"):
            assert_storage_ready()
        storage_mod.set_storage(S3Storage(bucket="b", client=FakeS3Client(exists=True)))
        assert_storage_ready()
    finally:
        storage_mod.set_storage(None)
