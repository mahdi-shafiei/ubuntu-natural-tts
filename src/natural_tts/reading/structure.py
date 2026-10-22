"""Blocks: the structure of a selection before it is read.

HTML is parsed as a stream with the standard library's ``html.parser``;
plain text is cut into fence-safe windows and each window is parsed with
``markdown-it-py``'s block rules when it looks like Markdown, else scanned
for the other code-block carriers (``carriers.py``) and read as prose.
Nothing here fetches anything or imports an engine.
"""

from __future__ import annotations

import html
import re
from collections.abc import Iterator
from dataclasses import replace
from html.parser import HTMLParser
from typing import Any

from natural_tts.reading import carriers
from natural_tts.reading.blocks import Block
from natural_tts.reading.formulas import LATEX, MATHML, UNICODE
from natural_tts.reading.math import find_math_spans, looks_like_math
from natural_tts.segments import Kind

HTML_FORMAT = "text/html"
WINDOW_CHARS = 8_000
_HTML_PIECE = 8_000
_SKIPPED_ELEMENTS = frozenset({"script", "style", "noscript", "template"})
_BLOCK_ELEMENTS = frozenset(
    {"p", "div", "section", "article", "main", "header", "footer", "figure"}
)
_HEADINGS = {f"h{n}": n for n in range(1, 7)}  # h1 to h6
_WHITESPACE = re.compile(r"[ \t\r\f\v]+")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_MARKER_PATTERNS = {
    "heading": re.compile(r"^ {0,3}#{1,6} \S"),
    "bullet": re.compile(r"^ {0,3}[-*+] \S"),
    "ordered": re.compile(r"^ {0,3}\d{1,3}[.)] \S"),
    "quote": re.compile(r"^ {0,3}> ?\S"),
    "table": re.compile(r"^ {0,3}\|.*\|\s*$"),
    "setext": re.compile(r"^ {0,3}(=+|-{3,})\s*$"),
}
_EMPHASIS_STRONG = re.compile(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1")
_EMPHASIS = re.compile(r"(?<![\w*])[*_](?=\S)([^*_\n]+?)(?<=\S)[*_](?![\w*])")
_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_TAGS = re.compile(r"<[^>]{1,200}>")
_CITATION_SUP = re.compile(r"^[\d,\s\-\u2013]+$")
_PARAGRAPH_BREAK = re.compile(r"\n[ \t]*\n")
_TEX_ANNOTATION = "application/x-tex"
_TEX_SCRIPT = "math/tex"
_SPLIT_KINDS = frozenset({Kind.PROSE, Kind.QUOTE, Kind.LIST_ITEM})


def blocks(text: str, format: str | None) -> Iterator[Block]:
    r"""Yield the blocks of ``text`` lazily, HTML or plain text.

    Display formulas (``$$…$$``, ``\\[…\\]``, equation environments) and
    paragraphs that are one Unicode formula become MATH blocks of their
    own; inline formulas stay in their paragraph for the prose reader.
    """
    for block in _raw_blocks(text, format):
        if block.kind in _SPLIT_KINDS:
            yield from _split_math(block)
        else:
            yield block


def _split_math(block: Block) -> Iterator[Block]:
    first = True
    for piece, language in _math_pieces(block.text):
        if language is None:
            index = block.ordered_index if first else None
            yield replace(block, text=piece, ordered_index=index)
        else:
            yield Block(Kind.MATH, piece, language=language)
        first = False


def _math_pieces(text: str) -> Iterator[tuple[str, str | None]]:
    """``(text, language)`` pieces: language None for prose."""
    spans = [s for s in find_math_spans(text) if s.display]
    if not spans and _is_formula_paragraph(text):
        yield text.strip(), UNICODE
        return
    last = 0
    for span in spans:
        yield from _prose_pieces(text[last : span.start])
        yield span.latex.strip(), LATEX
        last = span.end
    yield from _prose_pieces(text[last:])


def _prose_pieces(text: str) -> Iterator[tuple[str, str | None]]:
    prose: list[str] = []
    for paragraph in _PARAGRAPH_BREAK.split(text):
        if _is_formula_paragraph(paragraph):
            if "".join(prose).strip():
                yield "\n\n".join(prose).strip(), None
            prose = []
            yield paragraph.strip(), UNICODE
        else:
            prose.append(paragraph)
    if "".join(prose).strip():
        yield "\n\n".join(prose).strip(), None


def _is_formula_paragraph(text: str) -> bool:
    # LaTeX markup without delimiters stays with the word rules.
    if "\n" in text.strip() or any(c in text for c in "\\^_$"):
        return False
    return looks_like_math(text)


def _raw_blocks(text: str, format: str | None) -> Iterator[Block]:
    if format == HTML_FORMAT:
        yield from _html_blocks(text)
        return
    for window in structured_windows(text):
        # Carriers (rST, LaTeX, Org, AsciiDoc, prompts, diffs) claim their
        # spans first; what remains is Markdown or prose.
        for block in carriers.scan(window):
            if block.kind is Kind.PROSE and looks_like_markdown(block.text):
                yield from _markdown_blocks(block.text)
            elif block.kind is Kind.PROSE:
                yield Block(Kind.PROSE, inline_text(block.text))
            else:
                yield block


# -- windows -------------------------------------------------------------------


def structured_windows(text: str, size: int = WINDOW_CHARS) -> Iterator[str]:
    """Cut ``text`` at blank lines outside fences, about ``size`` chars each.

    The pieces concatenate back to ``text``. A fence longer than ``size``
    stays whole. A single line longer than ``size`` (hard-wrapped prose
    pasted as one line) is cut at sentence ends, else at spaces, so the
    first piece never waits for the whole selection.
    """
    buffer: list[str] = []
    length = 0
    fence: str | None = None
    for line in text.splitlines(keepends=True):
        match = _FENCE.match(line)
        if match:
            marker = match.group(1)
            if fence is None:
                # A fence starts its own window when a blank line precedes it.
                if buffer and not buffer[-1].strip():
                    yield "".join(buffer)
                    buffer, length = [], 0
                fence = marker
            elif marker[0] == fence[0] and len(marker) >= len(fence):
                fence = None
        if fence is None and len(line) > size:
            if buffer:
                yield "".join(buffer)
                buffer, length = [], 0
            yield from _split_long_line(line, size)
            continue
        if length >= size and fence is None and not line.strip():
            buffer.append(line)
            yield "".join(buffer)
            buffer, length = [], 0
            continue
        buffer.append(line)
        length += len(line)
    if buffer:
        yield "".join(buffer)


_SENTENCE_END_IN_LINE = re.compile(r"[.!?]\s")


def _split_long_line(line: str, size: int) -> Iterator[str]:
    start = 0
    while start < len(line):
        end = min(len(line), start + size)
        if end < len(line):
            ends = [
                m.end()
                for m in _SENTENCE_END_IN_LINE.finditer(line, start, end)
            ]
            cut = ends[-1] if ends else line.rfind(" ", start, end) + 1
            if cut > start:
                end = cut
        yield line[start:end]
        start = end


def looks_like_markdown(window: str) -> bool:
    """Whether a plain-text window carries Markdown structure markers."""
    counts = dict.fromkeys(_MARKER_PATTERNS, 0)
    fences = indented_blocks = indented_run = 0
    previous = ""
    for line in window.splitlines():
        if _FENCE.match(line):
            fences += 1
        for name, pattern in _MARKER_PATTERNS.items():
            if pattern.match(line):
                if name == "setext" and not previous.strip():
                    continue
                counts[name] += 1
        # Two or more lines indented by four after a blank line: code.
        if line.startswith(("    ", "\t")) and (
            indented_run or not previous.strip()
        ):
            indented_run += 1
            if indented_run == 2:
                indented_blocks += 1
        else:
            indented_run = 0
        previous = line
    return bool(
        fences
        or indented_blocks
        or counts["heading"]
        or counts["table"] >= 2
        or counts["setext"]
        or counts["bullet"] >= 2
        or counts["ordered"] >= 2
        or counts["quote"]
    )


# -- Markdown ------------------------------------------------------------------


def _parser() -> Any:
    from markdown_it import MarkdownIt

    return MarkdownIt("zero").enable(
        [
            "heading",
            "lheading",
            "list",
            "fence",
            "code",
            "blockquote",
            "table",
            "paragraph",
            "hr",
            "html_block",
        ]
    )


def inline_text(raw: str) -> str:
    """Drop emphasis markers and images from raw inline Markdown."""
    text = _IMAGE.sub(r"\1", raw)
    text = _EMPHASIS_STRONG.sub(r"\2", text)
    return _EMPHASIS.sub(r"\1", text)


def _markdown_blocks(window: str) -> Iterator[Block]:
    heading_level = 0
    quote_depth = 0
    counters: list[int | None] = []  # next index per open list (None: bullets)
    items: list[int | None] = []  # index of each open list item
    table: dict[str, Any] | None = None
    for token in _parser().parse(window):
        kind = token.type
        if kind == "heading_open":
            heading_level = int(token.tag[1])
        elif kind == "blockquote_open":
            quote_depth += 1
        elif kind == "blockquote_close":
            quote_depth -= 1
        elif kind == "bullet_list_open":
            counters.append(None)
        elif kind == "ordered_list_open":
            counters.append(int(token.attrGet("start") or 1))
        elif kind in {"bullet_list_close", "ordered_list_close"}:
            counters.pop()
        elif kind == "list_item_open":
            index = counters[-1] if counters else None
            items.append(index)
            if index is not None:
                counters[-1] = index + 1
        elif kind == "list_item_close":
            items.pop()
        elif kind == "fence":
            info = token.info.strip()
            language = info.split()[0].lower() if info else None
            yield Block(
                Kind.CODE, token.content.rstrip("\n"), language=language
            )
        elif kind == "code_block":
            yield Block(Kind.CODE, token.content.rstrip("\n"))
        elif kind == "html_block":
            text = _WHITESPACE.sub(" ", _TAGS.sub(" ", token.content)).strip()
            if text:
                yield Block(Kind.PROSE, text)
        elif kind == "table_open":
            table = {"columns": [], "rows": [], "current": [], "header": True}
        elif kind == "thead_close" and table is not None:
            table["header"] = False
        elif kind == "tr_open" and table is not None:
            table["current"] = []
        elif kind == "tr_close" and table is not None:
            if table["header"]:
                table["columns"] = table["current"]
            else:
                table["rows"].append(tuple(table["current"]))
        elif kind == "table_close" and table is not None:
            yield Block(
                Kind.TABLE,
                "",
                columns=tuple(table["columns"]),
                rows=tuple(table["rows"]),
            )
            table = None
        elif kind == "inline":
            text = inline_text(token.content).strip()
            if table is not None:
                table["current"].append(text)
            elif heading_level:
                yield Block(Kind.HEADING, text, level=heading_level)
                heading_level = 0
            elif items:
                yield Block(Kind.LIST_ITEM, text, ordered_index=items[-1])
            elif quote_depth:
                yield Block(Kind.QUOTE, text)
            elif text:
                yield Block(Kind.PROSE, text)


# -- HTML ----------------------------------------------------------------------


class _HtmlBlocks(HTMLParser):
    """Collects blocks as their closing tags arrive."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ready: list[Block] = []
        self._text: list[str] = []
        self._skip = 0
        self._pre = 0
        self._code = 0
        self._sup = 0
        self._quote = 0
        self._heading = 0
        self._lists: list[int | None] = []
        self._item_index: int | None = None
        self._language: str | None = None
        self._table: dict[str, Any] | None = None
        self._math: dict[str, Any] | None = None
        self._tex_script: list[str] | None = None

    # -- helpers
    def _flush(self, kind: Kind | None = None) -> None:
        raw = "".join(self._text)
        self._text = []
        if self._pre and kind is Kind.CODE:
            text = raw.strip("\n")
        else:
            text = (
                "\n".join(
                    _WHITESPACE.sub(" ", line).strip()
                    for line in raw.split("\n")
                )
                .strip("\n")
                .strip()
            )
        if not text:
            return
        if kind is None:
            kind = Kind.QUOTE if self._quote else Kind.PROSE
        if kind is Kind.HEADING:
            self.ready.append(Block(kind, text, level=self._heading))
        elif kind is Kind.LIST_ITEM:
            self.ready.append(Block(kind, text, ordered_index=self._item_index))
        elif kind is Kind.CODE:
            self.ready.append(Block(kind, text, language=self._language))
        else:
            self.ready.append(Block(kind, text))

    # -- parser callbacks
    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        attributes = dict(attrs)
        if self._math is not None:
            self._math["raw"].append(self.get_starttag_text() or "")
            if (
                tag == "annotation"
                and attributes.get("encoding") == _TEX_ANNOTATION
            ):
                self._math["tex"] = []
            return
        if tag == "script" and (attributes.get("type") or "").startswith(
            _TEX_SCRIPT
        ):
            self._flush()
            self._tex_script = []
            return
        if tag in _SKIPPED_ELEMENTS:
            self._skip += 1
            return
        if self._skip:
            return
        if tag == "math":
            self._flush()
            self._math = {
                "raw": [self.get_starttag_text() or ""],
                "alt": attributes.get("alttext"),
                "tex": None,
            }
        elif tag in _HEADINGS:
            self._flush()
            self._heading = _HEADINGS[tag]
        elif tag in _BLOCK_ELEMENTS:
            self._flush()
        elif tag == "br":
            self._text.append("\n")
        elif tag == "blockquote":
            self._flush()
            self._quote += 1
        elif tag in {"ul", "ol"}:
            self._flush()
            self._lists.append(1 if tag == "ol" else None)
        elif tag == "li":
            self._flush()
            counter = self._lists[-1] if self._lists else None
            self._item_index = counter
            if counter is not None:
                self._lists[-1] = counter + 1
        elif tag == "pre":
            self._flush()
            self._pre += 1
        elif tag == "code":
            self._code += 1
            if self._pre:
                self._language = _language_class(attributes.get("class"))
            else:
                self._text.append("`")
        elif tag == "sup":
            self._sup += 1
            self._text.append("\x00SUP")
        elif tag == "table":
            self._flush()
            self._table = {
                "columns": [],
                "rows": [],
                "cells": [],
                "header": False,
            }
        elif tag == "tr" and self._table is not None:
            self._table["cells"] = []
            self._table["header"] = False
        elif tag in {"th", "td"} and self._table is not None:
            self._text = []
            if tag == "th":
                self._table["header"] = True

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if self._math is not None:
            self._math["raw"].append(self.get_starttag_text() or "")
            return
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if self._math is not None:
            if tag == "math":
                self._close_math()
            else:
                self._math["raw"].append(f"</{tag}>")
                if tag == "annotation" and self._math["tex"] is not None:
                    self._math["alt"] = "".join(self._math["tex"])
                    self._math["tex"] = None
            return
        if tag == "script" and self._tex_script is not None:
            latex = "".join(self._tex_script).strip()
            self._tex_script = None
            if latex:
                self.ready.append(Block(Kind.MATH, latex, language=LATEX))
            return
        if tag in _SKIPPED_ELEMENTS:
            self._skip = max(0, self._skip - 1)
            return
        if self._skip:
            return
        if tag in _HEADINGS:
            self._flush(Kind.HEADING)
            self._heading = 0
        elif tag in _BLOCK_ELEMENTS:
            self._flush()
        elif tag == "blockquote":
            self._flush()
            self._quote = max(0, self._quote - 1)
        elif tag == "li":
            self._flush(Kind.LIST_ITEM)
            self._item_index = None
        elif tag in {"ul", "ol"}:
            self._flush()
            if self._lists:
                self._lists.pop()
        elif tag == "pre":
            self._flush(Kind.CODE)
            self._pre = max(0, self._pre - 1)
            self._language = None
        elif tag == "code":
            self._code = max(0, self._code - 1)
            if not self._pre:
                self._text.append("`")
        elif tag == "sup":
            self._sup = max(0, self._sup - 1)
            self._close_sup()
        elif tag in {"th", "td"} and self._table is not None:
            raw = "".join(self._text)
            self._text = []
            self._table["cells"].append(_WHITESPACE.sub(" ", raw).strip())
        elif tag == "tr" and self._table is not None:
            if self._table["header"] and not self._table["columns"]:
                self._table["columns"] = self._table["cells"]
            else:
                self._table["rows"].append(tuple(self._table["cells"]))
        elif tag == "table" and self._table is not None:
            table = self._table
            self._table = None
            self.ready.append(
                Block(
                    Kind.TABLE,
                    "",
                    columns=tuple(table["columns"]),
                    rows=tuple(table["rows"]),
                )
            )

    def handle_data(self, data: str) -> None:
        if self._math is not None:
            self._math["raw"].append(html.escape(data, quote=False))
            if self._math["tex"] is not None:
                self._math["tex"].append(data)
            return
        if self._tex_script is not None:
            self._tex_script.append(data)
            return
        if self._skip:
            return
        self._text.append(data)

    def _close_math(self) -> None:
        math = self._math
        self._math = None
        if math is None:
            return
        # The TeX annotation first (annotation wins over alttext), then the
        # alttext, then the MathML itself.
        math["raw"].append("</math>")
        latex = (math["alt"] or "").strip()
        if latex:
            self.ready.append(Block(Kind.MATH, latex, language=LATEX))
        else:
            self.ready.append(
                Block(Kind.MATH, "".join(math["raw"]), language=MATHML)
            )

    def _close_sup(self) -> None:
        # A superscript holding only numbers is a citation mark: "[1]".
        joined = "".join(self._text)
        head, sep, body = joined.rpartition("\x00SUP")
        if not sep:
            return
        marker = body.strip()
        if marker and _CITATION_SUP.match(marker):
            body = f" [{marker}]"
        self._text = [head + body]

    def close(self) -> None:
        """Finish parsing and flush whatever is still open."""
        super().close()
        self._flush()


def _language_class(value: str | None) -> str | None:
    for name in (value or "").split():
        for prefix in ("language-", "lang-"):
            if name.startswith(prefix) and len(name) > len(prefix):
                return name[len(prefix) :].lower()
    return None


def _html_blocks(html: str) -> Iterator[Block]:
    parser = _HtmlBlocks()
    for start in range(0, len(html), _HTML_PIECE):
        parser.feed(html[start : start + _HTML_PIECE])
        if parser.ready:
            yield from parser.ready
            parser.ready = []
    parser.close()
    yield from parser.ready
