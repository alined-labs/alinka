"""Text sanitizers: Unicode controls, emails and chats.

- Unicode format characters (category Cf: zero-width, bidi controls, soft hyphen...)
  and tag characters U+E0000..U+E007F are stripped and flagged. Tag characters are
  decoded too, since they can spell a hidden ASCII message.
- An email is read from its text/plain part. The HTML part's visible text is
  compared with it, and elements hidden by style are flagged.
- A chat is a plain-text export, read as is.
Code renders the clean text into PDF pages, so emails and chats get page images and
boxes like any PDF. Attached PDFs and images are sanitized with their own readers.
"""

from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from collections import Counter
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from html.parser import HTMLParser

import pymupdf

from alinka.ingest.base import Ingested, PageData, clip, find_instructions
from alinka.types import Channel

TAG_START, TAG_END = 0xE0000, 0xE007F
LINES_PER_PAGE = 60
PAGE_W, PAGE_H = 595, 842
_HIDDEN_STYLE = re.compile(
    r"display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0(?![.\d]*[1-9])|"
    r"opacity\s*:\s*0(?![.\d]*[1-9])|max-height\s*:\s*0(?![.\d]*[1-9])|"
    r"color\s*:\s*transparent",
    re.IGNORECASE,
)
_WHITE_TEXT = re.compile(r"(?<![-\w])color\s*:\s*(#fff\b|#ffffff\b|white\b)", re.IGNORECASE)
_BACKGROUND = re.compile(r"background(-color)?\s*:\s*([^;]+)", re.IGNORECASE)
_WHITE_BACKGROUND = re.compile(r"^\s*(#fff|#ffffff|white|transparent|none)\s*$", re.IGNORECASE)


# --- Unicode controls -----------------------------------------------------------------


def strip_controls(text: str) -> tuple[str, list[str]]:
    """Remove format and tag characters; return the clean text and one flag per kind."""
    if text.startswith("﻿"):
        text = text[1:]
    counts: Counter[str] = Counter()
    tags: list[str] = []
    kept: list[str] = []
    for ch in text:
        code = ord(ch)
        if TAG_START <= code <= TAG_END:
            if 0xE0020 <= code <= 0xE007E:
                tags.append(chr(code - TAG_START))
            continue
        if unicodedata.category(ch) == "Cf":
            counts[f"U+{code:04X} {unicodedata.name(ch, 'FORMAT CHARACTER')}"] += 1
            continue
        kept.append(ch)
    flags = [f"{name} ×{n}" for name, n in counts.items()]
    if tags:
        flags.append(f"tag characters spelling '{clip(''.join(tags))}'")
    return "".join(kept), flags


def hidden_tag_text(text: str) -> str:
    """The ASCII message smuggled in tag characters, if any."""
    return "".join(chr(ord(c) - TAG_START) for c in text if 0xE0020 <= ord(c) <= 0xE007E)


# --- Chats --------------------------------------------------------------------------


def ingest_chat(data: bytes) -> Ingested:
    out = Ingested(channel=Channel.CHAT, doc_sha256=hashlib.sha256(data).hexdigest())
    raw = data.decode("utf-8", errors="replace")
    _add_text(out, raw, "chat")
    return out


# --- Emails -------------------------------------------------------------------------


def ingest_email(data: bytes) -> Ingested:
    from alinka.ingest.image import ingest_image
    from alinka.ingest.pdf import ingest_pdf

    out = Ingested(channel=Channel.EMAIL, doc_sha256=hashlib.sha256(data).hexdigest())
    msg = BytesParser(policy=policy.default).parsebytes(data)
    assert isinstance(msg, EmailMessage)
    plain_part = msg.get_body(preferencelist=("plain",))
    html_part = msg.get_body(preferencelist=("html",))
    plain = plain_part.get_content() if plain_part is not None else None
    html_visible, html_hidden = (None, [])
    if html_part is not None:
        html_visible, html_hidden = html_text(html_part.get_content())

    headers = "\n".join(
        f"{name}: {msg[name]}" for name in ("From", "To", "Subject", "Date") if msg[name]
    )
    body = plain if plain is not None else (html_visible or "")
    for hidden in html_hidden:
        out.hidden_content.append(f"email HTML: hidden element: '{clip(hidden)}'")
        for snippet in find_instructions(hidden):
            out.instructions.append(f"email HTML hidden: {snippet}")
    if plain is not None and html_visible is not None and texts_differ(plain, html_visible):
        out.html_text_mismatch = True
        for snippet in find_instructions(html_visible):
            out.instructions.append(f"email HTML: {snippet}")
    _add_text(out, f"{headers}\n\n{body}", "email")

    for part in msg.iter_attachments():
        content_type = part.get_content_type()
        payload = part.get_payload(decode=True) or b""
        if content_type == "application/pdf":
            inner = ingest_pdf(payload)
        elif content_type.startswith("image/"):
            inner = ingest_image(payload)
        else:
            out.hidden_content.append(f"email attachment not read: {content_type}")
            continue
        _merge(out, inner, part.get_filename() or content_type)
    return out


class _VisibleHTML(HTMLParser):
    """Collect the text a person sees, and separately the text hidden by style."""

    SKIP = {"script", "style", "head", "title", "template", "noscript"}
    VOID = {"br", "hr", "img", "meta", "link", "input", "wbr", "col", "area", "base", "source"}
    BLOCK = {"p", "div", "tr", "li", "table", "h1", "h2", "h3", "h4", "h5", "h6", "br", "hr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.visible: list[str] = []
        self.hidden: list[str] = []
        self._stack: list[tuple[str, bool, bool, bool, bool]] = []
        # tag, skip, hidden by style, white text, dark background

    def _state(self) -> tuple[bool, bool]:
        skip = any(entry[1] for entry in self._stack)
        hidden = any(entry[2] for entry in self._stack)
        # White text is hidden unless it sits on a coloured background at or above it.
        for _, _, _, white, dark in reversed(self._stack):
            if dark:
                break
            if white:
                hidden = True
                break
        return skip, hidden

    def handle_starttag(self, tag, attrs):
        if tag in self.BLOCK:
            self.visible.append("\n")
        if tag in self.VOID:
            return
        style = " ".join(v or "" for k, v in attrs if k == "style")
        hidden = bool(_HIDDEN_STYLE.search(style)) or any(k == "hidden" for k, _ in attrs)
        background = _BACKGROUND.search(style)
        dark = bool(background) and not _WHITE_BACKGROUND.match(background.group(2))
        dark = dark or any(
            k == "bgcolor" and not _WHITE_BACKGROUND.match(v or "") for k, v in attrs
        )
        white = bool(_WHITE_TEXT.search(style))
        self._stack.append((tag, tag in self.SKIP, hidden, white, dark))

    def handle_endtag(self, tag):
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i][0] == tag:
                del self._stack[i:]
                break
        if tag in self.BLOCK or tag in {"td", "th"}:
            self.visible.append("\n" if tag in self.BLOCK else " ")

    def handle_data(self, data):
        skip, hidden = self._state()
        if skip:
            return
        if hidden:
            if data.strip():
                self.hidden.append(data.strip())
        else:
            self.visible.append(data)


def html_text(markup: str) -> tuple[str, list[str]]:
    """Visible text of an HTML body, and the texts its styles hide."""
    parser = _VisibleHTML()
    parser.feed(markup)
    parser.close()
    lines = [" ".join(line.split()) for line in "".join(parser.visible).splitlines()]
    return "\n".join(line for line in lines if line), parser.hidden


_TOKEN = re.compile(r"\w+", re.UNICODE)


def texts_differ(plain: str, visible_html: str) -> bool:
    """True when the HTML shows numbers or words the plain text does not have."""
    a = Counter(t.lower() for t in _TOKEN.findall(html.unescape(plain)))
    b = Counter(t.lower() for t in _TOKEN.findall(visible_html))
    numbers_a = {t for t in a if any(c.isdigit() for c in t)}
    numbers_b = {t for t in b if any(c.isdigit() for c in t)}
    if numbers_a != numbers_b:
        return True
    extra = sum((b - a).values())
    return extra > max(3, 0.05 * sum(b.values()))


# --- Shared -------------------------------------------------------------------------


def _add_text(out: Ingested, raw: str, label: str) -> None:
    clean, flags = strip_controls(raw)
    out.unicode_controls.extend(flags)
    tagged = hidden_tag_text(raw)
    for snippet in find_instructions(tagged):
        out.instructions.append(f"{label} tag characters: {snippet}")
    for snippet in find_instructions(clean):
        out.instructions.append(f"{label}: {snippet}")
    rendered = render_text_pdf(clean)
    doc = pymupdf.open(stream=rendered, filetype="pdf")
    try:
        lines = clean.splitlines()
        for i, page in enumerate(doc):
            pix = page.get_pixmap(dpi=150, alpha=False)
            chunk = lines[i * LINES_PER_PAGE : (i + 1) * LINES_PER_PAGE]
            out.pages.append(
                PageData(
                    number=i + 1,
                    width=page.rect.width,
                    height=page.rect.height,
                    png=pix.tobytes("png"),
                    text="\n".join(chunk).strip(),
                    source_pdf=rendered,
                    source_page=i,
                )
            )
    finally:
        doc.close()


def render_text_pdf(text: str) -> bytes:
    """Lay clean text out on A4 pages, LINES_PER_PAGE source lines per page."""
    doc = pymupdf.open()
    lines = text.splitlines() or [""]
    css = "* {font-family: sans-serif; font-size: 10pt; white-space: pre-wrap;}"
    for start in range(0, len(lines), LINES_PER_PAGE):
        page = doc.new_page(width=PAGE_W, height=PAGE_H)
        chunk = "\n".join(lines[start : start + LINES_PER_PAGE])
        page.insert_htmlbox(
            pymupdf.Rect(40, 40, PAGE_W - 40, PAGE_H - 40),
            f"<div>{html.escape(chunk)}</div>",
            css=css,
            scale_low=0,
        )
    data = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    return data


def _merge(out: Ingested, inner: Ingested, name: str) -> None:
    offset = len(out.pages)
    for page in inner.pages:
        page.number += offset
        for i, span in enumerate(page.spans):
            page.spans[i] = type(span)(
                text=span.text, box=span.box.model_copy(update={"page": page.number})
            )
        out.pages.append(page)
    prefix = f"attachment {name}: "
    out.hidden_content.extend(prefix + f for f in inner.hidden_content)
    out.unicode_controls.extend(prefix + f for f in inner.unicode_controls)
    out.instructions.extend(prefix + f for f in inner.instructions)
    out.html_text_mismatch = out.html_text_mismatch or inner.html_text_mismatch
