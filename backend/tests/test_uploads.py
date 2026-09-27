"""Upload guards (A-22): size cap, type allow-list, content sniffing, safe names,
RFC 6266 downloads, and byte deletion on document delete (A-13)."""

from __future__ import annotations

import io
import zipfile

import pytest
from httpx import AsyncClient

from app.core import uploads
from app.core.db_utils import contains, escape_like
from app.core.http_utils import content_disposition, sanitize_filename
from app.core.storage import get_storage
from app.main import app

API = "/api/v1"
PDF = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _docx() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("word/document.xml", "<w:document/>")
    return buf.getvalue()


async def _user(client: AsyncClient, pw: str) -> dict:
    resp = await client.post(
        f"{API}/auth/register",
        json={
            "organisation_name": "Upload LLP",
            "full_name": "Adv. Upload",
            "email": "upload@firm.co",
            "password": pw,
            "accept_terms": True,
        },
    )
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


# ─── Pure helpers ────────────────────────────────────────────────────
def test_escape_like_neutralises_wildcards() -> None:
    assert escape_like("100%") == "100\\%"
    assert escape_like("a_b") == "a\\_b"
    assert escape_like("back\\slash") == "back\\\\slash"
    assert contains("%_") == "%\\%\\_%"


def test_sanitize_filename_strips_dangerous_characters() -> None:
    assert sanitize_filename('a"b\\c;d/e\x00f\x1fg.pdf') == "abcdefg.pdf"
    assert sanitize_filename("  ../../etc/passwd ") == "etcpasswd"
    assert sanitize_filename("") == "untitled"
    assert sanitize_filename('"""') == "untitled"
    assert len(sanitize_filename("x" * 1000)) == 300
    assert sanitize_filename("वकालतनामा.pdf") == "वकालतनामा.pdf"


def test_content_disposition_is_rfc6266_and_injection_safe() -> None:
    cd = content_disposition('evil"; filename="x.exe')
    assert cd.startswith('attachment; filename="')
    # The quote and semicolon are gone from both parameters.
    assert '"; filename="x.exe' not in cd
    assert cd.count('"') == 2
    assert "filename*=UTF-8''" in cd
    dev = content_disposition("वकालतनामा.pdf")
    assert 'filename="' in dev and "filename*=UTF-8''%E0%A4" in dev
    assert content_disposition("x", inline=True).startswith("inline;")


def test_sniffer_accepts_matching_types_and_rejects_mismatches() -> None:
    assert uploads.sniff_type(PDF, "application/pdf") == "application/pdf"
    assert uploads.sniff_type(PNG, "image/png") == "image/png"
    assert uploads.sniff_type(b"plain words\nline two", "text/plain") == "text/plain"
    assert uploads.sniff_type(b"a,b\n1,2\n", "text/csv") == "text/csv"
    docx = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert uploads.sniff_type(_docx(), docx) == docx
    assert uploads.sniff_type(_docx(), "application/zip") == "application/zip"
    with pytest.raises(uploads.UnsupportedUploadTypeError):
        uploads.sniff_type(b"<html><script>alert(1)</script>", "application/pdf")
    with pytest.raises(uploads.UnsupportedUploadTypeError):
        uploads.sniff_type(b"<!doctype html><html>", "text/plain")
    with pytest.raises(uploads.UnsupportedUploadTypeError):
        uploads.sniff_type(b"MZ\x90\x00binary", "image/png")
    with pytest.raises(uploads.UnsupportedUploadTypeError):
        uploads.sniff_type(PDF, "image/jpeg")  # declared jpeg, really pdf


def test_allow_list_is_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(uploads.settings, "ALLOWED_UPLOAD_TYPES", raising=False)
    monkeypatch.setenv("VS_ALLOWED_UPLOAD_TYPES", "pdf, image/png")
    assert uploads.allowed_upload_types() == frozenset({"application/pdf", "image/png"})
    with pytest.raises(uploads.UnsupportedUploadTypeError, match="not accepted"):
        uploads.validate_upload(b"hello", "text/plain", "a.txt")
    monkeypatch.delenv("VS_ALLOWED_UPLOAD_TYPES")
    assert "text/plain" in uploads.allowed_upload_types()
    with pytest.raises(uploads.UnsupportedUploadTypeError, match="not accepted"):
        uploads.validate_upload(b"x", "application/x-msdownload", "a.exe")
    # Generic octet-stream falls back to the extension.
    assert (
        uploads.validate_upload(PDF, "application/octet-stream", "brief.pdf") == "application/pdf"
    )


async def test_read_limited_stops_at_the_cap() -> None:
    class _Stream:
        def __init__(self, data: bytes) -> None:
            self._b = io.BytesIO(data)

        async def read(self, size: int = -1) -> bytes:
            return self._b.read(size)

    assert await uploads.read_limited(_Stream(b"x" * 1000), 1000) == b"x" * 1000
    with pytest.raises(uploads.UploadTooLargeError):
        await uploads.read_limited(_Stream(b"x" * 1001), 1000)


# ─── HTTP path ───────────────────────────────────────────────────────
async def test_upload_rejects_oversize_with_413(
    client: AsyncClient, strong_password: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = await _user(client, strong_password)
    monkeypatch.delattr(uploads.settings, "MAX_UPLOAD_BYTES", raising=False)
    monkeypatch.setenv("VS_MAX_UPLOAD_BYTES", "64")
    big = PDF + b"0" * 100
    r = await client.post(
        f"{API}/documents", headers=h, files={"file": ("b.pdf", big, "application/pdf")}
    )
    assert r.status_code == 413, r.text
    assert "limit" in r.json()["detail"].lower()
    small = await client.post(
        f"{API}/documents", headers=h, files={"file": ("b.pdf", PDF, "application/pdf")}
    )
    assert small.status_code == 201, small.text


async def test_upload_rejects_disallowed_and_mismatched_types_with_415(
    client: AsyncClient, strong_password: str
) -> None:
    h = await _user(client, strong_password)
    exe = await client.post(
        f"{API}/documents",
        headers=h,
        files={"file": ("x.exe", b"MZ\x90", "application/x-msdownload")},
    )
    assert exe.status_code == 415, exe.text
    html_as_pdf = await client.post(
        f"{API}/documents",
        headers=h,
        files={"file": ("x.pdf", b"<html><script>1</script></html>", "application/pdf")},
    )
    assert html_as_pdf.status_code == 415, html_as_pdf.text
    # The stored type is the sniffed one, not whatever the client claimed.
    lie = await client.post(
        f"{API}/documents", headers=h, files={"file": ("x.bin", PDF, "application/octet-stream")}
    )
    assert lie.status_code == 415  # octet-stream with an unknown extension is not verifiable
    ok = await client.post(
        f"{API}/documents", headers=h, files={"file": ("x.pdf", PDF, "application/octet-stream")}
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["content_type"] == "application/pdf"


async def test_upload_name_is_sanitised_and_download_uses_rfc6266(
    client: AsyncClient, strong_password: str
) -> None:
    h = await _user(client, strong_password)
    r = await client.post(
        f"{API}/documents",
        headers=h,
        files={"file": ("brief.pdf", PDF, "application/pdf")},
        data={"name": 'evil"; filename="x.exe\r\nX-Injected: 1/../../वकालतनामा'},
    )
    assert r.status_code == 201, r.text
    doc = r.json()
    assert '"' not in doc["name"] and ";" not in doc["name"] and "/" not in doc["name"]
    assert "\r" not in doc["name"] and "\n" not in doc["name"]
    assert "वकालतनामा" in doc["name"]

    dl = await client.get(f"{API}/documents/{doc['id']}/download", headers=h)
    assert dl.status_code == 200
    cd = dl.headers["content-disposition"]
    assert cd.startswith('attachment; filename="') and "filename*=UTF-8''" in cd
    assert '"; filename="x.exe' not in cd and cd.count('"') == 2
    assert dl.headers["x-content-type-options"] == "nosniff"

    # A PATCH rename goes through the same cleaning.
    p = await client.patch(f"{API}/documents/{doc['id']}", headers=h, json={"name": 'a"b;c\\d'})
    assert p.status_code == 200, p.text
    assert p.json()["name"] == "abcd"
    bad = await client.patch(f"{API}/documents/{doc['id']}", headers=h, json={"name": '";\\'})
    assert bad.status_code == 422


async def test_delete_removes_every_versions_bytes(
    client: AsyncClient, strong_password: str
) -> None:
    h = await _user(client, strong_password)
    up = await client.post(
        f"{API}/documents", headers=h, files={"file": ("a.pdf", PDF, "application/pdf")}
    )
    doc_id = up.json()["id"]
    v2 = await client.post(
        f"{API}/documents/{doc_id}/versions",
        headers=h,
        files={"file": ("a.pdf", PDF + b"v2", "application/pdf")},
    )
    assert v2.status_code == 201, v2.text
    storage = app.dependency_overrides[get_storage]()
    keys_before = set(storage._store)
    assert len(keys_before) == 2

    d = await client.delete(f"{API}/documents/{doc_id}", headers=h)
    assert d.status_code == 204
    assert storage._store == {}
    assert (await client.get(f"{API}/documents/{doc_id}", headers=h)).status_code == 404
