"""HTTP helpers shared by the download endpoints."""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import quote

# Characters that must never reach a Content-Disposition parameter or a stored
# file name: quotes and backslashes (parameter injection), semicolons (a new
# parameter), path separators (directory traversal on the client's disk) and
# control characters (header splitting, terminal escapes).
_FORBIDDEN = re.compile(r'["\\;/\x00-\x1f\x7f]')
MAX_FILENAME_LENGTH = 300


def sanitize_filename(name: str, *, max_length: int = MAX_FILENAME_LENGTH) -> str:
    """Strip characters that are unsafe in a file name and cap its length.

    Returns ``"untitled"`` when nothing usable is left, so callers never store
    or send an empty name.
    """
    cleaned = unicodedata.normalize("NFC", name or "")
    cleaned = _FORBIDDEN.sub("", cleaned).strip().strip(".")
    cleaned = re.sub(r"\s+", " ", cleaned)
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length].rstrip()
    return cleaned or "untitled"


def content_disposition(name: str, *, inline: bool = False) -> str:
    """RFC 6266 ``Content-Disposition`` value with an ASCII fallback.

    ``filename`` carries a pure-ASCII, quote-free approximation for legacy
    clients; ``filename*`` carries the UTF-8 percent-encoded original so
    Devanagari or accented names round-trip in every modern browser. Neither
    parameter can break out of the header: the fallback is stripped of
    everything but ``[A-Za-z0-9._ -]`` and the extended form is percent-encoded.
    """
    safe = sanitize_filename(name)
    ascii_fallback = re.sub(r"[^A-Za-z0-9._ -]", "_", safe.encode("ascii", "ignore").decode())
    ascii_fallback = ascii_fallback.strip(" ._") or "download"
    disposition = "inline" if inline else "attachment"
    return (
        f'{disposition}; filename="{ascii_fallback}"; '
        f"filename*=UTF-8''{quote(safe, safe='')}"
    )
