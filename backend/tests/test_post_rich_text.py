"""Feed posts with formatted text and photos (migration 0066)."""

from __future__ import annotations

import struct
import zlib

import pytest
from httpx import AsyncClient

from app.core.html_clean import clean_html, html_to_text
from app.modules.network.media import ImageRejected, prepare_post_image

pytestmark = pytest.mark.asyncio
API = "/api/v1/network"


def _jpeg_with_gps() -> bytes:
    """A minimal JPEG: SOI, APP0 (JFIF), APP1 (Exif with a fake GPS string), SOF0 640x480, SOS, EOI."""
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    exif_body = b"Exif\x00\x00GPS 28.6139N 77.2090E"
    app1 = b"\xff\xe1" + struct.pack(">H", len(exif_body) + 2) + exif_body
    sof = b"\xff\xc0" + struct.pack(">HBHHB", 11, 8, 480, 640, 1) + b"\x01\x11\x00"
    sos = b"\xff\xda" + struct.pack(">H", 8) + b"\x01\x01\x00\x00\x3f\x00" + b"\x12\x34\x56"
    return b"\xff\xd8" + app0 + app1 + sof + sos + b"\xff\xd9"


def _png() -> bytes:
    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
    ihdr = struct.pack(">IIBBBBB", 2, 3, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"tEXt", b"Location\x00Delhi")
            + chunk(b"IDAT", zlib.compress(b"\x00" * 21)) + chunk(b"IEND", b""))


def test_clean_html_keeps_formatting_and_drops_everything_else() -> None:
    dirty = (
        '<h1 onclick="x()">Title</h1><p style="color:red">Hello <b>bold</b> <i>it</i> '
        '<a href="javascript:alert(1)">bad</a> <a href="https://vidhisangh.com/acts">good</a></p>'
        "<script>alert(1)</script><img src=x onerror=alert(1)><ul><li>one<li>two</ul><p></p>"
    )
    out = clean_html(dirty)
    assert out == (
        "<h2>Title</h2><p>Hello <strong>bold</strong> <em>it</em> bad "
        '<a href="https://vidhisangh.com/acts" target="_blank" rel="noopener noreferrer nofollow">good</a></p>'
        "<ul><li>one</li><li>two</li></ul>"
    )
    assert "script" not in out and "onerror" not in out and "style" not in out
    assert html_to_text(out).startswith("Title\n\nHello bold it bad good")
    assert "• one" in html_to_text(out)


def test_images_lose_location_metadata_and_bad_files_are_refused() -> None:
    cleaned, kind, w, h = prepare_post_image(_jpeg_with_gps())
    assert (kind, w, h) == ("image/jpeg", 640, 480)
    assert b"GPS" not in cleaned and b"Exif" not in cleaned and b"JFIF" in cleaned
    cleaned, kind, w, h = prepare_post_image(_png())
    assert (kind, w, h) == ("image/png", 2, 3) and b"Location" not in cleaned
    for bad in (b"", b"GIF89a....", b"<svg onload=alert(1)>", b"\xff\xd8\xff" + b"\x00" * 10):
        with pytest.raises(ImageRejected):
            prepare_post_image(bad)


async def _member(client: AsyncClient, email: str, pw: str) -> dict:
    resp = await client.post("/api/v1/auth/register", json={
        "organisation_name": email.split("@")[0], "full_name": "Adv. " + email.split("@")[0].title(),
        "email": email, "password": pw, "accept_terms": True,
    })
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def test_post_with_formatted_text_and_photos(client: AsyncClient, strong_password: str) -> None:
    me = await _member(client, "writer@firm.co", strong_password)
    other = await _member(client, "reader@firm.co", strong_password)

    up = await client.post(f"{API}/post-images", headers=me, files={"file": ("p.jpg", _jpeg_with_gps(), "image/jpeg")})
    assert up.status_code == 201, up.text
    image = up.json()
    assert (image["width"], image["height"]) == (640, 480)
    bad = await client.post(f"{API}/post-images", headers=me, files={"file": ("x.svg", b"<svg/>", "image/svg+xml")})
    assert bad.status_code == 422

    # Not served until a live post uses it; another member cannot attach it.
    assert (await client.get(f"{API}/post-images/{image['id']}")).status_code == 404
    stolen = await client.post(f"{API}/posts", headers=other, json={"content": "mine", "image_ids": [image["id"]]})
    assert stolen.status_code == 422

    created = await client.post(f"{API}/posts", headers=me, json={
        "content_html": "<h2>New criminal laws</h2><p>BNS <strong>Section 103</strong></p><script>x</script>",
        "image_ids": [image["id"]], "hashtags": ["BNS"],
    })
    assert created.status_code == 201, created.text
    post = created.json()
    assert post["content_html"] == "<h2>New criminal laws</h2><p>BNS <strong>Section 103</strong></p>"
    assert post["content"] == "New criminal laws\n\nBNS Section 103"
    assert [i["id"] for i in post["images"]] == [image["id"]]

    served = await client.get(f"{API}/post-images/{image['id']}")
    assert served.status_code == 200 and served.headers["content-type"] == "image/jpeg"
    assert b"GPS" not in served.content and "immutable" in served.headers["cache-control"]

    feed = (await client.get(f"{API}/feed", headers=me)).json()
    item = next(p for p in feed if p["id"] == post["id"])
    assert item["images"][0]["width"] == 640 and item["content_html"].startswith("<h2>")

    # A photo is used once; an empty post is refused; plain-text posts still work.
    again = await client.post(f"{API}/posts", headers=me, json={"content": "again", "image_ids": [image["id"]]})
    assert again.status_code == 422
    assert (await client.post(f"{API}/posts", headers=me, json={"content": " "})).status_code == 422
    plain = await client.post(f"{API}/posts", headers=me, json={"content": "Plain text still works"})
    assert plain.status_code == 201 and plain.json()["content_html"] is None and plain.json()["images"] == []

    # Deleting the post takes the photo offline.
    assert (await client.delete(f"{API}/posts/{post['id']}", headers=me)).status_code == 204
    assert (await client.get(f"{API}/post-images/{image['id']}")).status_code == 404
