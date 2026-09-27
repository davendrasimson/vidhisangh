"""Upload guards shared by the document endpoints.

Three controls, in order:

1. **Size** — the multipart body is read in chunks and the byte count checked
   as it grows, so an oversize upload is refused with 413 the moment it passes
   the cap instead of being buffered whole in memory first.
2. **Type allow-list** — only the document, image and archive types a law
   practice exchanges are accepted (configurable via ``VS_ALLOWED_UPLOAD_TYPES``).
3. **Content sniffing** — the first bytes are matched against the signature of
   the declared type. A ``.pdf`` that is really an HTML page (a stored-XSS
   vector when served back), or an image that is really an executable, is
   refused with 415. The *sniffed* type is what gets stored and served, never
   the client's ``Content-Type``.
"""

from __future__ import annotations

import os
import re
import zipfile
from io import BytesIO
from typing import Any, Protocol

from app.core.config import settings

DEFAULT_MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MiB — keep nginx client_max_body_size in step
_CHUNK = 64 * 1024
_SNIFF_BYTES = 4096

# Canonical MIME per extension. Aliases browsers send (``application/x-pdf``,
# ``image/jpg``) are folded onto these before the allow-list is consulted.
EXTENSION_TYPES: dict[str, str] = {
    "pdf": "application/pdf",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xls": "application/vnd.ms-excel",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "txt": "text/plain",
    "csv": "text/csv",
    "rtf": "application/rtf",
    "odt": "application/vnd.oasis.opendocument.text",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
    "zip": "application/zip",
}
DEFAULT_ALLOWED_TYPES: frozenset[str] = frozenset(EXTENSION_TYPES.values())

_ALIASES: dict[str, str] = {
    "application/x-pdf": "application/pdf",
    "image/jpg": "image/jpeg",
    "image/pjpeg": "image/jpeg",
    "text/rtf": "application/rtf",
    "application/x-zip-compressed": "application/zip",
    "application/x-zip": "application/zip",
    "application/csv": "text/csv",
    "application/vnd.ms-excel.sheet.macroenabled.12": "application/vnd.ms-excel",
}

_OOXML_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "word/",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xl/",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "ppt/",
}
_ZIP_MAGIC = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
# Text that is really markup would be rendered by a browser if served inline.
_MARKUP_RE = re.compile(rb"^\s*(<!doctype\s+html|<html|<script|<svg|<\?xml)", re.I)
_TEXT_ALLOWED_CONTROL = {0x09, 0x0A, 0x0D, 0x0C, 0x1B}


class UploadTooLargeError(Exception):
    def __init__(self, limit: int) -> None:
        super().__init__(f"File exceeds the {limit // (1024 * 1024)} MiB upload limit.")
        self.limit = limit


class UnsupportedUploadTypeError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)


class _Readable(Protocol):
    async def read(self, size: int = -1) -> bytes: ...


def _setting(name: str, default: Any) -> Any:
    value = getattr(settings, name, None)
    if value is None:
        value = os.environ.get(f"VS_{name}")
    return default if value in (None, "") else value


def max_upload_bytes() -> int:
    return int(_setting("MAX_UPLOAD_BYTES", DEFAULT_MAX_UPLOAD_BYTES))


def allowed_upload_types() -> frozenset[str]:
    """Allow-list from ``VS_ALLOWED_UPLOAD_TYPES`` (comma-separated MIME types or
    extensions), defaulting to the built-in document/image/archive set."""
    raw = _setting("ALLOWED_UPLOAD_TYPES", None)
    if not raw:
        return DEFAULT_ALLOWED_TYPES
    items = raw if isinstance(raw, list | tuple | set | frozenset) else str(raw).split(",")
    out: set[str] = set()
    for item in items:
        token = str(item).strip().lower().lstrip(".")
        if not token:
            continue
        out.add(EXTENSION_TYPES.get(token, _ALIASES.get(token, token)))
    return frozenset(out) or DEFAULT_ALLOWED_TYPES


async def read_limited(file: _Readable, limit: int | None = None) -> bytes:
    """Read an upload in chunks, refusing it as soon as it exceeds ``limit``."""
    cap = limit if limit is not None else max_upload_bytes()
    buf = BytesIO()
    total = 0
    while True:
        chunk = await file.read(_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > cap:
            raise UploadTooLargeError(cap)
        buf.write(chunk)
    return buf.getvalue()


def normalize_type(content_type: str | None, filename: str | None) -> str:
    """Canonical declared type: the header when it is specific, else by extension."""
    declared = (content_type or "").split(";")[0].strip().lower()
    declared = _ALIASES.get(declared, declared)
    if declared in ("", "application/octet-stream", "binary/octet-stream") and filename:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        declared = EXTENSION_TYPES.get(ext, declared)
    return declared or "application/octet-stream"


def _looks_like_text(head: bytes) -> bool:
    if b"\x00" in head:
        return False
    if _MARKUP_RE.match(head):
        return False
    binary = sum(1 for b in head if b < 0x20 and b not in _TEXT_ALLOWED_CONTROL)
    return binary <= max(2, len(head) // 200)


def _zip_kind(data: bytes) -> str | None:
    """Distinguish OOXML / ODT containers from a plain zip by their entries."""
    try:
        with zipfile.ZipFile(BytesIO(data)) as zf:
            names = zf.namelist()[:64]
            if "mimetype" in names:
                try:
                    with zf.open("mimetype") as fh:
                        return fh.read(200).decode("ascii", "ignore").strip() or None
                except (KeyError, RuntimeError, zipfile.BadZipFile):
                    return None
            if any(n == "[Content_Types].xml" for n in names):
                for mime, prefix in _OOXML_TYPES.items():
                    if any(n.startswith(prefix) for n in names):
                        return mime
                return "application/zip"
            return "application/zip"
    except (zipfile.BadZipFile, ValueError, OSError):
        # Truncated central directory etc. — magic says zip, accept as zip.
        return "application/zip"


def sniff_type(data: bytes, declared: str) -> str:
    """Return the type the bytes really are, or raise if they contradict ``declared``.

    Detection covers every allow-listed format. Text types (``text/plain``,
    ``text/csv``) are accepted when the head is printable text that is not HTML/
    SVG/XML markup. Unknown declared types are rejected here regardless of the
    allow-list, because a type we cannot verify is a type we cannot safely serve.
    """
    head = data[:_SNIFF_BYTES]
    detected: str | None = None
    if head.startswith(b"%PDF-"):
        detected = "application/pdf"
    elif head.startswith(b"\x89PNG\r\n\x1a\n"):
        detected = "image/png"
    elif head.startswith(b"\xff\xd8\xff"):
        detected = "image/jpeg"
    elif head[:6] in (b"GIF87a", b"GIF89a"):
        detected = "image/gif"
    elif head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        detected = "image/webp"
    elif head.startswith(b"{\\rtf"):
        detected = "application/rtf"
    elif head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        # OLE2 compound file: legacy .doc / .xls (also .ppt/.msg — narrowed by declaration).
        legacy_office = ("application/msword", "application/vnd.ms-excel")
        detected = declared if declared in legacy_office else "application/msword"
    elif head[:4] in _ZIP_MAGIC:
        detected = _zip_kind(data)
    elif declared in ("text/plain", "text/csv") and _looks_like_text(head):
        detected = declared

    if detected is None:
        raise UnsupportedUploadTypeError(
            "The file's contents do not match a supported document type."
        )
    if detected != declared:
        # A zip container declared as a generic zip is fine; anything else that
        # disagrees with the declaration is refused rather than "fixed".
        if not (declared == "application/zip" and detected in _OOXML_TYPES):
            raise UnsupportedUploadTypeError(
                f"The file's contents ({detected}) do not match its declared type ({declared})."
            )
        detected = declared
    return detected


def validate_upload(data: bytes, content_type: str | None, filename: str | None) -> str:
    """Allow-list + sniff. Returns the verified content type to store."""
    declared = normalize_type(content_type, filename)
    if declared not in allowed_upload_types():
        raise UnsupportedUploadTypeError(f"Files of type {declared} are not accepted.")
    return sniff_type(data, declared)
