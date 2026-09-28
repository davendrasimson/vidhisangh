"""Safe DOCX template import into the editor's ProseMirror document model."""

from __future__ import annotations

import re
import zipfile
from copy import deepcopy
from io import BytesIO
from typing import Any

from docx import Document as DocxDocument
from docx.enum.section import WD_ORIENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.core.exceptions import ValidationError
from app.modules.drafting.models import DEFAULT_PAGE

MAX_DOCX_ENTRIES = 5_000
MAX_DOCX_EXPANDED_BYTES = 80 * 1024 * 1024
MAX_DOCX_PART_BYTES = 20 * 1024 * 1024
_TOKEN = re.compile(r"\{\{\s*([^{}]{1,80}?)\s*\}\}|\[\[\s*([^\[\]]{1,80}?)\s*\]\]")
_ALIGN = {
    WD_ALIGN_PARAGRAPH.CENTER: "center",
    WD_ALIGN_PARAGRAPH.RIGHT: "right",
    WD_ALIGN_PARAGRAPH.JUSTIFY: "justify",
}


def _validate_container(data: bytes) -> None:
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_DOCX_ENTRIES:
                raise ValidationError("The Word template contains too many internal files.")
            if any(item.file_size > MAX_DOCX_PART_BYTES for item in entries):
                raise ValidationError(
                    "The Word template contains an unusually large internal file."
                )
            if sum(item.file_size for item in entries) > MAX_DOCX_EXPANDED_BYTES:
                raise ValidationError("The expanded Word template is too large.")
    except zipfile.BadZipFile as exc:
        raise ValidationError("The uploaded file is not a valid Word document.") from exc


def _marks(run: Any) -> list[dict[str, Any]]:
    marks: list[dict[str, Any]] = []
    if run.bold:
        marks.append({"type": "bold"})
    if run.italic:
        marks.append({"type": "italic"})
    if run.underline:
        marks.append({"type": "underline"})
    if run.font.strike:
        marks.append({"type": "strike"})
    attrs: dict[str, str] = {}
    if run.font.name:
        attrs["fontFamily"] = run.font.name
    if run.font.size:
        attrs["fontSize"] = f"{run.font.size.pt:g}pt"
    if run.font.color and run.font.color.rgb:
        attrs["color"] = f"#{run.font.color.rgb}"
    if attrs:
        marks.append({"type": "textStyle", "attrs": attrs})
    return marks


def _paragraph(paragraph: Paragraph) -> dict[str, Any]:
    alignment = _ALIGN.get(paragraph.alignment) if paragraph.alignment is not None else None
    attrs: dict[str, Any] = {"textAlign": alignment or "left"}
    style_name = paragraph.style.name if paragraph.style else ""
    heading = re.match(r"Heading\s+([1-6])", style_name, re.I)
    node: dict[str, Any] = {
        "type": "heading" if heading else "paragraph",
        "attrs": {**attrs, **({"level": int(heading.group(1))} if heading else {})},
    }
    text = "".join(run.text for run in paragraph.runs)
    # Word often splits one placeholder across runs. Keep the whole paragraph
    # together when it contains a token so form replacement is reliable.
    if text and _TOKEN.search(text):
        node["content"] = [{"type": "text", "text": text}]
        return node
    content = []
    for run in paragraph.runs:
        if not run.text:
            continue
        item: dict[str, Any] = {"type": "text", "text": run.text}
        marks = _marks(run)
        if marks:
            item["marks"] = marks
        content.append(item)
    if content:
        node["content"] = content
    return node


def _table(table: Table) -> dict[str, Any]:
    rows = []
    for row_index, row in enumerate(table.rows):
        cells = []
        for cell in row.cells:
            cells.append(
                {
                    "type": "tableHeader" if row_index == 0 else "tableCell",
                    "content": [_paragraph(paragraph) for paragraph in cell.paragraphs]
                    or [{"type": "paragraph"}],
                }
            )
        rows.append({"type": "tableRow", "content": cells})
    return {"type": "table", "content": rows}


def _blocks(parent: Any) -> list[dict[str, Any]]:
    container = parent.element.body if hasattr(parent, "element") else parent._tc
    blocks = []
    for child in container.iterchildren():
        if child.tag.endswith("}p"):
            blocks.append(_paragraph(Paragraph(child, parent)))
        elif child.tag.endswith("}tbl"):
            blocks.append(_table(Table(child, parent)))
    return blocks


def _field_key(label: str, used: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", label.casefold()).strip("_") or "field"
    base = base[:60]
    key = base
    suffix = 2
    while key in used:
        key = f"{base}_{suffix}"
        suffix += 1
    used.add(key)
    return key


def template_fields(document: dict[str, Any]) -> list[dict[str, Any]]:
    """Infer a form schema from placeholders in an editor document."""
    text_parts: list[str] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("type") == "text":
                text_parts.append(str(value.get("text", "")))
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(document)
    seen_tokens: set[str] = set()
    used_keys: set[str] = set()
    out = []
    for match in _TOKEN.finditer("\n".join(text_parts)):
        label = (match.group(1) or match.group(2) or "").strip()
        token = match.group(0)
        if token in seen_tokens:
            continue
        seen_tokens.add(token)
        out.append(
            {
                "key": _field_key(label, used_keys),
                "label": label,
                "token": token,
                "type": "multiline"
                if any(
                    word in label.casefold()
                    for word in ("facts", "ground", "prayer", "relief", "term", "detail")
                )
                else "text",
                "required": False,
            }
        )
    return out


def _page(document: Any) -> dict[str, Any]:
    if not document.sections:
        return deepcopy(DEFAULT_PAGE)
    section = document.sections[0]
    width = section.page_width.mm
    height = section.page_height.mm
    size = (
        "Legal"
        if max(width, height) > 320
        else "Letter"
        if abs(min(width, height) - 215.9) < 3
        else "A4"
    )
    return {
        "size": size,
        "orientation": "landscape" if section.orientation == WD_ORIENT.LANDSCAPE else "portrait",
        "margins": {
            "top": round(section.top_margin.mm, 1),
            "right": round(section.right_margin.mm, 1),
            "bottom": round(section.bottom_margin.mm, 1),
            "left": round(section.left_margin.mm, 1),
        },
    }


def import_docx_template(
    data: bytes,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    """Return editor JSON, inferred form fields and page settings."""
    _validate_container(data)
    try:
        word = DocxDocument(BytesIO(data))
    except (ValueError, KeyError, TypeError, zipfile.BadZipFile) as exc:
        raise ValidationError("The uploaded Word document could not be read.") from exc
    content = _blocks(word)
    document = {"type": "doc", "content": content or [{"type": "paragraph"}]}
    return document, template_fields(document), _page(word)


def fill_template(
    document: dict[str, Any], fields: list[dict[str, Any]], values: dict[str, str]
) -> dict[str, Any]:
    """Replace declared placeholders while keeping all editor formatting."""
    output = deepcopy(document)
    replacements = {
        str(field.get("token", "")): str(values.get(str(field.get("key", "")), ""))
        for field in fields
        if field.get("token")
    }

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("type") == "text":
                text = str(value.get("text", ""))
                for token, replacement in replacements.items():
                    text = text.replace(token, replacement or token)
                value["text"] = text
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(output)
    return output
