"""Images attached to feed posts: type check, size, dimensions and metadata strip.

Only real JPEG and PNG files are accepted (checked by their bytes, not their
name). Phone photos carry EXIF with the GPS position where they were taken, so
JPEG APP1 (EXIF/XMP), APP13 (IPTC) and comments, and PNG text/EXIF/time chunks,
are removed before anything is stored. The app also re-draws photos as JPEG of
at most 2000 px before uploading; this is the server-side guarantee.
"""

from __future__ import annotations

import struct

from app.core.exceptions import ValidationError

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGES_PER_POST = 4
_MAX_SIDE = 12000
_JPEG_DROP = {0xE1, 0xED, 0xFE}  # APP1 EXIF/XMP, APP13 IPTC/Photoshop, COM
_PNG_DROP = {b"eXIf", b"tEXt", b"iTXt", b"zTXt", b"tIME"}
_PNG_SIG = b"\x89PNG\r\n\x1a\n"


class ImageRejected(ValidationError):
    message = "Upload a JPEG or PNG photo (up to 5 MB)."


def _jpeg(data: bytes) -> tuple[bytes, int, int]:
    if not data.startswith(b"\xff\xd8"):
        raise ImageRejected()
    out = bytearray(b"\xff\xd8")
    width = height = 0
    i = 2
    while i < len(data):
        if data[i] != 0xFF:
            raise ImageRejected("This JPEG file is damaged.")
        marker = data[i + 1] if i + 1 < len(data) else 0
        if marker == 0xFF:  # fill byte
            i += 1
            continue
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:  # no length
            out += data[i:i + 2]
            i += 2
            continue
        if marker == 0xD9:
            out += data[i:i + 2]
            break
        if i + 4 > len(data):
            raise ImageRejected("This JPEG file is damaged.")
        length = struct.unpack(">H", data[i + 2:i + 4])[0]
        segment = data[i:i + 2 + length]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3) and length >= 7:
            height, width = struct.unpack(">HH", data[i + 5:i + 9])
        if marker == 0xDA:  # start of scan: the rest is image data
            out += data[i:]
            break
        if marker not in _JPEG_DROP:
            out += segment
        i += 2 + length
    return bytes(out), width, height


def _png(data: bytes) -> tuple[bytes, int, int]:
    out = bytearray(_PNG_SIG)
    width = height = 0
    i = len(_PNG_SIG)
    while i + 8 <= len(data):
        length = struct.unpack(">I", data[i:i + 4])[0]
        kind = data[i + 4:i + 8]
        chunk = data[i:i + 12 + length]
        if len(chunk) < 12 + length:
            raise ImageRejected("This PNG file is damaged.")
        if kind == b"IHDR":
            width, height = struct.unpack(">II", data[i + 8:i + 16])
        if kind not in _PNG_DROP:
            out += chunk
        i += 12 + length
        if kind == b"IEND":
            break
    return bytes(out), width, height


def prepare_post_image(data: bytes) -> tuple[bytes, str, int, int]:
    """(cleaned bytes, content type, width, height), or ImageRejected."""
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ImageRejected()
    if data.startswith(b"\xff\xd8\xff"):
        cleaned, width, height = _jpeg(data)
        kind = "image/jpeg"
    elif data.startswith(_PNG_SIG):
        cleaned, width, height = _png(data)
        kind = "image/png"
    else:
        raise ImageRejected()
    if not (0 < width <= _MAX_SIDE and 0 < height <= _MAX_SIDE):
        raise ImageRejected("This image's size could not be read.")
    return cleaned, kind, width, height
