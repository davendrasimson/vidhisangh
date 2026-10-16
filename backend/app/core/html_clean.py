"""Allow-list HTML cleaning for member-written rich text (feed posts).

Posts are shown to other members, so their HTML is rebuilt from a small
allow-list instead of trusted: paragraphs, line breaks, bold/italic/underline/
strike, two heading levels, lists, quotes and links (http, https, mailto only;
always opened in a new tab with ``rel="noopener noreferrer nofollow"``). Every
other tag is dropped but its text kept; scripts, styles, frames and similar are
dropped with their content; no attributes survive except a link's ``href``.
Standard library only (``html.parser``).
"""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser

_ALIASES = {"b": "strong", "i": "em", "strike": "s", "del": "s", "h1": "h2", "h4": "h3", "h5": "h3", "h6": "h3"}
_ALLOWED = {"p", "br", "strong", "em", "u", "s", "ul", "ol", "li", "h2", "h3", "blockquote", "a"}
_VOID = {"br"}
_DROP_WITH_CONTENT = {"script", "style", "iframe", "object", "embed", "svg", "math", "template", "noscript", "head", "title", "textarea", "select"}
_BLOCK = {"p", "h2", "h3", "li", "blockquote", "ul", "ol"}
_SAFE_HREF = re.compile(r"^(https?://|mailto:)", re.IGNORECASE)


class _Cleaner(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.stack: list[str] = []
        self.skip = 0  # depth inside a dropped-with-content element

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in _DROP_WITH_CONTENT:
            self.skip += 1
            return
        if self.skip:
            return
        tag = _ALIASES.get(tag, tag)
        if tag not in _ALLOWED:
            return
        if tag == "a":
            href = next((v for k, v in attrs if k.lower() == "href" and v), "").strip()
            if not _SAFE_HREF.match(href):
                return  # a link we will not render: keep its text only
            self.out.append(f'<a href="{html.escape(href, quote=True)}" target="_blank" rel="noopener noreferrer nofollow">')
        else:
            if tag in ("li", "p") and self.stack and self.stack[-1] == tag:
                self.handle_endtag(tag)  # "<li>one<li>two": the first one ends here
            self.out.append(f"<{tag}>")
        if tag not in _VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if _ALIASES.get(tag.lower(), tag.lower()) not in _VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _DROP_WITH_CONTENT:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        tag = _ALIASES.get(tag, tag)
        if tag not in self.stack:
            return
        while self.stack:  # close anything left open inside it
            top = self.stack.pop()
            self.out.append(f"</{top}>")
            if top == tag:
                break

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.out.append(html.escape(data, quote=False))

    def result(self) -> str:
        while self.stack:
            self.out.append(f"</{self.stack.pop()}>")
        return "".join(self.out)


def clean_html(value: str) -> str:
    """The allow-listed version of ``value``; empty paragraphs at the ends removed."""
    cleaner = _Cleaner()
    cleaner.feed(value)
    cleaner.close()
    out = cleaner.result()
    return re.sub(r"^(?:<p>(?:\s|<br>)*</p>)+|(?:<p>(?:\s|<br>)*</p>)+$", "", out).strip()


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "br":
            self.parts.append("\n")
        elif tag == "li":
            self.parts.append("\n• ")
        elif tag in _BLOCK:
            self.parts.append("\n\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _BLOCK:
            self.parts.append("\n\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def html_to_text(value: str) -> str:
    """Plain text of cleaned HTML: for search, notifications, shares and old apps."""
    parser = _Text()
    parser.feed(value)
    parser.close()
    text = "".join(parser.parts)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()
