"""DOCX export resource bounds (A-31): image size, spans, nesting depth."""

from __future__ import annotations

import base64

import pytest

from app.core.exceptions import ValidationError
from app.modules.drafting import docx_export
from app.modules.drafting.docx_export import export_docx, word_count
from app.modules.drafting.schemas import DraftUpdate


def _para(text: str) -> dict:
    return {"type": "paragraph", "content": [{"type": "text", "text": text}]}


def test_oversize_image_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(docx_export, "MAX_IMAGE_BYTES", 1024)
    monkeypatch.setattr(docx_export, "MAX_TOTAL_IMAGE_BYTES", 2048)
    big = base64.b64encode(b"\x89PNG" + b"\x00" * 2000).decode()
    doc = {
        "type": "doc",
        "content": [{"type": "image", "attrs": {"src": f"data:image/png;base64,{big}"}}],
    }
    with pytest.raises(ValidationError, match="embedded image exceeds"):
        export_docx(doc)

    small = base64.b64encode(b"\x89PNG" + b"\x00" * 600).decode()
    many = {
        "type": "doc",
        "content": [
            {"type": "image", "attrs": {"src": f"data:image/png;base64,{small}"}} for _ in range(4)
        ],
    }
    with pytest.raises(ValidationError, match="in total"):
        export_docx(many)


def test_spans_and_columns_are_clamped() -> None:
    cell = {
        "type": "tableCell",
        "attrs": {"colspan": 100000, "rowspan": 100000},
        "content": [_para("x")],
    }
    wide = {
        "type": "tableRow",
        "content": [
            {"type": "tableCell", "attrs": {"colspan": 1}, "content": [_para("c")]}
            for _ in range(500)
        ],
    }
    table = {"type": "table", "content": [{"type": "tableRow", "content": [cell]}, wide]}
    doc = {"type": "doc", "content": [table]}
    blob = export_docx(doc)  # must not raise or allocate a 100000x100000 grid
    assert blob[:2] == b"PK"
    assert docx_export._span({"attrs": {"colspan": "7"}}, "colspan") == 7
    assert docx_export._span({"attrs": {"colspan": "nope"}}, "colspan") == 1
    assert docx_export._span({"attrs": {"colspan": -5}}, "colspan") == 1
    assert docx_export._span({"attrs": {"colspan": 10**9}}, "colspan") == docx_export.MAX_SPAN


def test_excessive_nesting_fails_with_a_clear_error() -> None:
    node: dict = _para("deep")
    for _ in range(docx_export.MAX_DEPTH + 5):
        node = {"type": "blockquote", "content": [node]}
    doc = {"type": "doc", "content": [node]}
    with pytest.raises(ValidationError, match="nesting exceeds"):
        export_docx(doc)
    # Word counting is bounded too (it runs on every autosave).
    node = _para("x")
    for _ in range(docx_export.MAX_DEPTH * 2 + 5):
        node = {"type": "blockquote", "content": [node]}
    with pytest.raises(ValidationError, match="nesting exceeds"):
        word_count({"type": "doc", "content": [node]})
    # Sane depth still exports.
    node = _para("ok")
    for _ in range(10):
        node = {"type": "blockquote", "content": [node]}
    assert export_docx({"type": "doc", "content": [node]})[:2] == b"PK"


def test_content_html_is_capped_at_8mb() -> None:
    from pydantic import ValidationError as PydanticValidationError

    with pytest.raises(PydanticValidationError, match="too large"):
        DraftUpdate(content_html="<p>" + "x" * (9 * 1024 * 1024) + "</p>")
    DraftUpdate(content_html="<p>fine</p>")
