"""ProseMirror document -> .docx, built from the structure (not from HTML).

The editor's JSON is the source of truth, so the exporter walks it node by
node and emits real Word constructs: headings as Word heading styles, lists
with nesting, tables with merged cells, images, page breaks, and run-level
formatting (font, size, colour, highlight, bold/italic/underline/strike,
sub/superscript, links). Page size, orientation and margins come from the
draft's page settings. What Word opens is what the editor showed.

Supported nodes: doc, paragraph, heading, bulletList, orderedList, listItem,
taskList, taskItem, blockquote, codeBlock, horizontalRule, hardBreak, table,
tableRow, tableCell, tableHeader, image, pageBreak.
Supported marks: bold, italic, underline, strike, subscript, superscript,
code, link, highlight, textStyle{color,fontFamily,fontSize,backgroundColor}.
"""

from __future__ import annotations

import base64
import io
import re
from typing import Any

from docx import Document as DocxDocument
from docx.enum.section import WD_ORIENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor

_PAGE_SIZES_MM = {"A4": (210, 297), "Letter": (215.9, 279.4), "Legal": (215.9, 355.6)}
_ALIGN = {
    "left": WD_ALIGN_PARAGRAPH.LEFT,
    "center": WD_ALIGN_PARAGRAPH.CENTER,
    "right": WD_ALIGN_PARAGRAPH.RIGHT,
    "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
}
_DEFAULT_FONT = "Times New Roman"
_DEFAULT_SIZE_PT = 12


def _hex(color: str | None) -> RGBColor | None:
    if not color:
        return None
    m = re.match(r"^#?([0-9a-fA-F]{6})$", color.strip())
    if m:
        return RGBColor.from_string(m.group(1).upper())
    m = re.match(r"^rgba?\((\d+),\s*(\d+),\s*(\d+)", color)
    if m:
        return RGBColor(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def _shade(run, color: str) -> None:  # noqa: ANN001
    """Arbitrary background colour on a run (Word's highlight palette is 16 colours)."""
    rgb = _hex(color)
    if rgb is None:
        return
    rpr = run._r.get_or_add_rPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), str(rgb))
    rpr.append(shd)


def _pt(size: str | None) -> float | None:
    """'14px' / '12pt' / '1.2em' -> points."""
    if not size:
        return None
    m = re.match(r"^\s*([\d.]+)\s*(px|pt|em|rem)?\s*$", str(size))
    if not m:
        return None
    n, unit = float(m.group(1)), (m.group(2) or "px")
    return {"px": n * 0.75, "pt": n, "em": n * _DEFAULT_SIZE_PT, "rem": n * _DEFAULT_SIZE_PT}[unit]


class _Exporter:
    def __init__(self, page: dict | None) -> None:
        self.doc = DocxDocument()
        self._page_setup(page or {})
        style = self.doc.styles["Normal"]
        style.font.name = _DEFAULT_FONT
        style.font.size = Pt(_DEFAULT_SIZE_PT)
        # East-Asian font slot too, or Word substitutes for Indic/Devanagari text.
        style.element.rPr.rFonts.set(qn("w:eastAsia"), _DEFAULT_FONT)

    def _page_setup(self, page: dict) -> None:
        section = self.doc.sections[0]
        w, h = _PAGE_SIZES_MM.get(page.get("size", "A4"), _PAGE_SIZES_MM["A4"])
        if page.get("orientation") == "landscape":
            section.orientation = WD_ORIENT.LANDSCAPE
            w, h = h, w
        section.page_width, section.page_height = Mm(w), Mm(h)
        m = page.get("margins") or {}
        section.top_margin = Mm(float(m.get("top", 25.4)))
        section.right_margin = Mm(float(m.get("right", 25.4)))
        section.bottom_margin = Mm(float(m.get("bottom", 25.4)))
        section.left_margin = Mm(float(m.get("left", 25.4)))

    # ── Blocks ─────────────────────────────────────────────────────
    def blocks(self, nodes: list[dict], container=None, *, list_style: str | None = None, level: int = 0) -> None:  # noqa: ANN001
        container = container or self.doc
        for node in nodes or []:
            self.block(node, container, list_style=list_style, level=level)

    def block(self, node: dict, container, *, list_style: str | None = None, level: int = 0) -> None:  # noqa: ANN001
        t = node.get("type")
        attrs = node.get("attrs") or {}
        if t == "paragraph":
            p = container.add_paragraph(style=list_style) if list_style else container.add_paragraph()
            self._paragraph_format(p, attrs, level)
            self.inlines(node.get("content") or [], p)
        elif t == "heading":
            lvl = max(1, min(int(attrs.get("level", 1)), 6))
            p = container.add_paragraph(style=f"Heading {lvl}")
            self._paragraph_format(p, attrs, level)
            self.inlines(node.get("content") or [], p)
        elif t in ("bulletList", "orderedList"):
            style = "List Bullet" if t == "bulletList" else "List Number"
            if level:
                style += f" {min(level + 1, 3)}"
            for item in node.get("content") or []:
                self.list_item(item, container, style, level)
        elif t == "taskList":
            for item in node.get("content") or []:
                checked = bool((item.get("attrs") or {}).get("checked"))
                content = item.get("content") or []
                if content and content[0].get("type") == "paragraph":
                    p = container.add_paragraph()
                    p.paragraph_format.left_indent = Mm(6 * (level + 1))
                    p.add_run("☑ " if checked else "☐ ")
                    self.inlines(content[0].get("content") or [], p)
                    self.blocks(content[1:], container, level=level + 1)
        elif t == "blockquote":
            for child in node.get("content") or []:
                before = len(container.paragraphs) if hasattr(container, "paragraphs") else 0
                self.block(child, container, level=level)
                for p in (container.paragraphs[before:] if hasattr(container, "paragraphs") else []):
                    p.paragraph_format.left_indent = Mm(12)
                    for r in p.runs:
                        r.italic = True
        elif t == "codeBlock":
            p = container.add_paragraph()
            run = p.add_run(_text_of(node))
            run.font.name = "Courier New"
            run.font.size = Pt(10)
        elif t == "horizontalRule":
            p = container.add_paragraph()
            ppr = p._p.get_or_add_pPr()
            pbdr = OxmlElement("w:pBdr")
            bottom = OxmlElement("w:bottom")
            for k, v in (("w:val", "single"), ("w:sz", "6"), ("w:space", "1"), ("w:color", "999999")):
                bottom.set(qn(k), v)
            pbdr.append(bottom)
            ppr.append(pbdr)
        elif t == "pageBreak":
            container.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
        elif t == "table":
            self.table(node, container)
        elif t == "image":
            self.image(attrs, container.add_paragraph())
        elif t == "hardBreak":
            container.add_paragraph()
        else:  # unknown block: keep its text rather than lose it
            text = _text_of(node)
            if text:
                container.add_paragraph(text)

    def list_item(self, item: dict, container, style: str, level: int) -> None:  # noqa: ANN001
        content = item.get("content") or []
        first = True
        for child in content:
            if child.get("type") == "paragraph" and first:
                p = container.add_paragraph(style=style)
                self._paragraph_format(p, child.get("attrs") or {}, 0)
                self.inlines(child.get("content") or [], p)
                first = False
            elif child.get("type") in ("bulletList", "orderedList"):
                self.block(child, container, level=level + 1)
            else:
                self.block(child, container, list_style=style, level=level)

    def _paragraph_format(self, p, attrs: dict, level: int) -> None:  # noqa: ANN001
        align = _ALIGN.get(attrs.get("textAlign") or "")
        if align is not None:
            p.alignment = align
        indent = attrs.get("indent")
        if indent:
            p.paragraph_format.left_indent = Mm(10 * int(indent))
        lh = attrs.get("lineHeight")
        if lh:
            try:
                p.paragraph_format.line_spacing = float(lh)
            except ValueError:
                pass

    # ── Tables ─────────────────────────────────────────────────────
    def table(self, node: dict, container) -> None:  # noqa: ANN001
        rows = [r for r in node.get("content") or [] if r.get("type") == "tableRow"]
        if not rows:
            return
        ncols = max(
            sum(int((c.get("attrs") or {}).get("colspan", 1)) for c in r.get("content") or []) for r in rows
        )
        table = container.add_table(rows=len(rows), cols=ncols)
        table.style = "Table Grid"
        occupied: set[tuple[int, int]] = set()
        for ri, row in enumerate(rows):
            ci = 0
            for cell in row.get("content") or []:
                while (ri, ci) in occupied:
                    ci += 1
                a = cell.get("attrs") or {}
                colspan, rowspan = int(a.get("colspan", 1)), int(a.get("rowspan", 1))
                target = table.cell(ri, ci)
                if colspan > 1 or rowspan > 1:
                    target = target.merge(table.cell(ri + rowspan - 1, ci + colspan - 1))
                    for rr in range(ri, ri + rowspan):
                        for cc in range(ci, ci + colspan):
                            occupied.add((rr, cc))
                # A fresh cell has one empty paragraph; write into it.
                target.paragraphs[0].text = ""
                blocks = cell.get("content") or []
                first = True
                for b in blocks:
                    if b.get("type") in ("paragraph", "heading") and first:
                        p = target.paragraphs[0]
                        self._paragraph_format(p, b.get("attrs") or {}, 0)
                        self.inlines(b.get("content") or [], p)
                        first = False
                    else:
                        self.block(b, target)
                if cell.get("type") == "tableHeader":
                    for p in target.paragraphs:
                        for r in p.runs:
                            r.bold = True
                ci += colspan
        container.add_paragraph()

    # ── Images ─────────────────────────────────────────────────────
    def image(self, attrs: dict, p) -> None:  # noqa: ANN001
        src = attrs.get("src") or ""
        m = re.match(r"^data:image/[\w+.-]+;base64,(.+)$", src, re.S)
        if not m:
            p.add_run(f"[image: {attrs.get('alt') or src[:80]}]")
            return
        data = base64.b64decode(m.group(1))
        width = attrs.get("width")
        try:
            run = p.add_run()
            if width:
                run.add_picture(io.BytesIO(data), width=Mm(min(float(width) * 0.2646, 160)))
            else:
                run.add_picture(io.BytesIO(data), width=Mm(120))
        except Exception:  # noqa: BLE001 — unreadable image must not break export
            p.add_run("[image]")

    # ── Inline runs ────────────────────────────────────────────────
    def inlines(self, nodes: list[dict], p) -> None:  # noqa: ANN001
        for node in nodes:
            t = node.get("type")
            if t == "text":
                self.run(node, p)
            elif t == "hardBreak":
                p.add_run().add_break(WD_BREAK.LINE)
            elif t == "image":
                self.image(node.get("attrs") or {}, p)
            else:
                text = _text_of(node)
                if text:
                    p.add_run(text)

    def run(self, node: dict, p) -> None:  # noqa: ANN001
        run = p.add_run(node.get("text", ""))
        for mark in node.get("marks") or []:
            mt, a = mark.get("type"), mark.get("attrs") or {}
            if mt == "bold":
                run.bold = True
            elif mt == "italic":
                run.italic = True
            elif mt == "underline":
                run.underline = True
            elif mt == "strike":
                run.font.strike = True
            elif mt == "subscript":
                run.font.subscript = True
            elif mt == "superscript":
                run.font.superscript = True
            elif mt == "code":
                run.font.name = "Courier New"
            elif mt == "highlight":
                _shade(run, a.get("color") or "#FFF176")
            elif mt == "link":
                run.underline = True
                run.font.color.rgb = RGBColor(0x1A, 0x56, 0xDB)
            elif mt == "textStyle":
                rgb = _hex(a.get("color"))
                if rgb is not None:
                    run.font.color.rgb = rgb
                if a.get("fontFamily"):
                    family = str(a["fontFamily"]).split(",")[0].strip("'\" ")
                    run.font.name = family
                    run._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), family)
                pt = _pt(a.get("fontSize"))
                if pt:
                    run.font.size = Pt(pt)
                if a.get("backgroundColor"):
                    _shade(run, a["backgroundColor"])


_INLINE = {"text", "hardBreak", "image"}


def _text_of(node: dict) -> str:
    """Plain text of a node. Inline children run together; block children
    (paragraphs, cells, list items) are separated, so "DELHI" + "The" stays
    two words for counting."""
    if node.get("type") == "text":
        return node.get("text", "")
    if node.get("type") == "hardBreak":
        return "\n"
    children = node.get("content") or []
    sep = "" if all(c.get("type") in _INLINE for c in children) else "\n"
    return sep.join(_text_of(c) for c in children)


def export_docx(content_json: dict, page: dict | None = None, *, title: str | None = None) -> bytes:
    """Render a ProseMirror document to .docx bytes."""
    ex = _Exporter(page)
    if title:
        ex.doc.core_properties.title = title
    ex.blocks((content_json or {}).get("content") or [])
    buf = io.BytesIO()
    ex.doc.save(buf)
    return buf.getvalue()


def word_count(content_json: dict) -> int:
    return len(re.findall(r"\S+", _text_of(content_json or {})))
