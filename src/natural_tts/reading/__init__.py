"""Content-aware reading: turns a selection into speakable segments.

Pure functions only; nothing here imports an engine. The rules were written
against the project's research notes, with normt2s 0.7.0 (MIT) read as a
reference implementation and its measured outputs kept as golden rows.

``prepare`` is the hotkey path's entry point. A selection (plain text or
HTML) becomes blocks (``structure``), each block becomes one or more
segments: prose, headings, list items and quotes go through the lexicon
and the word rules, chunked as before; code blocks go through the code
reader; tables announce their shape, then their rows; formulas go through
the MathCAT helper, inline ones as protected words inside their sentence,
display ones as segments with the helper's pauses. With
``reading.enabled = false`` it yields exactly today's chunks; with a
non-English voice the structure stays and the English word rules do not.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator

from natural_tts.config import CHUNK_MAX_CHARS, FIRST_CHUNK_MIN_CHARS, Settings
from natural_tts.reading.blocks import Block
from natural_tts.reading.code import read_code
from natural_tts.reading.formulas import (
    LATEX,
    Formulas,
    fallback_text,
    formulas_for,
    inline_words,
)
from natural_tts.reading.lexicon import Lexicon, load_lexicon, packaged_lexicon
from natural_tts.reading.math import find_math_spans
from natural_tts.reading.mathcat import MathCat
from natural_tts.reading.normalize import normalize_words
from natural_tts.reading.numbers import cardinal
from natural_tts.reading.protected import protect, unprotect
from natural_tts.reading.structure import blocks
from natural_tts.segments import Kind, Segment
from natural_tts.text import chunk_text

_ENGLISH_LANG_CODES = frozenset("ab")
# Seconds of silence before a segment of each kind, and its speed factor.
PAUSES: dict[Kind, float] = {
    Kind.HEADING: 0.6,
    Kind.LIST_ITEM: 0.25,
    Kind.QUOTE: 0.25,
    Kind.CODE: 0.25,
    Kind.MATH: 0.25,
    Kind.TABLE: 0.25,
}
RATES: dict[Kind, float] = {Kind.HEADING: 0.9, Kind.CODE: 0.9}
_INLINE_CODE = re.compile(r"`([^`\n]{1,500}+)`")

Chunker = Callable[[str, str | None], Iterator[Segment]]


def plain_segments(text: str) -> Iterator[Segment]:
    """Today's reading: one prose segment per text chunk, no rewriting."""
    for chunk in chunk_text(text, FIRST_CHUNK_MIN_CHARS, CHUNK_MAX_CHARS):
        yield Segment(chunk)


def lexicon_for(settings: Settings) -> Lexicon:
    """The packaged lexicon with the user's file merged on top."""
    return _packaged().merged(load_lexicon(settings.paths.lexicon_file))


_PACKAGED: list[Lexicon] = []


def _packaged() -> Lexicon:
    if not _PACKAGED:
        _PACKAGED.append(packaged_lexicon())
    return _PACKAGED[0]


class _Reader:
    """Reads blocks for one settings object (voice, level, citations)."""

    def __init__(self, settings: Settings, formulas: Formulas) -> None:
        reading, kokoro = settings.reading, settings.kokoro
        self.english = kokoro.lang_code in _ENGLISH_LANG_CODES
        self.british = kokoro.lang_code == "b"
        self.citations = reading.citations
        self.level = reading.code_level
        self.lexicon = lexicon_for(settings) if self.english else None
        self.formulas = formulas

    def segments(self, block: Block) -> Iterator[Segment]:
        """Turn one block into segments."""
        if block.kind is Kind.CODE:
            yield from self._code(block)
        elif block.kind is Kind.MATH:
            yield from self._math(block)
        elif block.kind is Kind.TABLE:
            yield from self._table(block)
        else:
            yield from self._prose(block)

    def _words(self, text: str) -> str:
        if self.lexicon is not None:
            text = normalize_words(
                self.lexicon.apply(text),
                british=self.british,
                citations=self.citations,
            )
        return unprotect(text)

    def _inline_code(self, match: re.Match[str]) -> str:
        lines = read_code(match.group(1), language=None, level=self.level)
        return protect(" ".join(lines))

    def _math_pieces(
        self, text: str, language: str | None
    ) -> list[tuple[float, str]]:
        spoken = self.formulas.speak(text, language)
        if spoken is None:
            words = self._words(fallback_text(text, language))
            spoken = [(0.0, words)] if words else []
        return spoken

    def _inline_math(self, text: str) -> str:
        spans = find_math_spans(text)
        if not spans:
            return text
        out: list[str] = []
        last = 0
        for span in spans:
            out.append(text[last : span.start])
            words = inline_words(self._math_pieces(span.latex, LATEX))
            if words:
                out.append(protect(words))
            last = span.end
        out.append(text[last:])
        return "".join(out)

    def _math(self, block: Block) -> Iterator[Segment]:
        pause = PAUSES[Kind.MATH]
        for piece_pause, words in self._math_pieces(block.text, block.language):
            yield Segment(
                words, kind=Kind.MATH, pause_before=max(pause, piece_pause)
            )
            pause = 0.0

    def _prose(self, block: Block) -> Iterator[Segment]:
        # Inline code first: its words carry no "$", so a formula inside a
        # code span is never read twice.
        text = _INLINE_CODE.sub(self._inline_code, block.text)
        text = self._inline_math(text)
        if block.ordered_index is not None:
            number = (
                cardinal(block.ordered_index)
                if self.english
                else str(block.ordered_index)
            )
            text = f"{number}, {text}"
        pause = PAUSES.get(block.kind, 0.0)
        for chunk in chunk_text(text, FIRST_CHUNK_MIN_CHARS, CHUNK_MAX_CHARS):
            words = self._words(chunk)
            if words:
                yield Segment(
                    words,
                    kind=block.kind,
                    pause_before=pause,
                    rate=RATES.get(block.kind, 1.0),
                )
                pause = 0.0

    def _code(self, block: Block) -> Iterator[Segment]:
        lines = read_code(block.text, language=block.language, level=self.level)
        group: list[str] = []
        pause = PAUSES[Kind.CODE]
        for line in lines:
            if (
                group
                and sum(len(g) + 2 for g in group) + len(line) > CHUNK_MAX_CHARS
            ):
                yield Segment(
                    ". ".join(group),
                    kind=Kind.CODE,
                    pause_before=pause,
                    rate=RATES[Kind.CODE],
                )
                group, pause = [], 0.0
            group.append(line)
        if group:
            yield Segment(
                ". ".join(group),
                kind=Kind.CODE,
                pause_before=pause,
                rate=RATES[Kind.CODE],
            )

    def _table(self, block: Block) -> Iterator[Segment]:
        columns = len(block.columns) or max(
            (len(r) for r in block.rows), default=0
        )
        shape = "table, {}, {}".format(
            _count(columns, "column"), _count(len(block.rows), "row")
        )
        yield Segment(shape, kind=Kind.TABLE, pause_before=PAUSES[Kind.TABLE])
        for row in block.rows:
            cells = [
                f"{name}: {cell}" if name else cell
                for name, cell in zip(
                    block.columns + ("",) * len(row), row, strict=False
                )
            ]
            words = self._words(", ".join(c for c in cells if c))
            if words:
                yield Segment(
                    words, kind=Kind.TABLE, pause_before=PAUSES[Kind.TABLE]
                )


def _count(n: int, noun: str) -> str:
    return f"{cardinal(n)} {noun}{'' if n == 1 else 's'}"


def prepare(
    text: str,
    settings: Settings,
    format: str | None = None,
    formulas: Formulas | None = None,
) -> Iterator[Segment]:
    """Turn a selection into segments, lazily.

    Args:
        text: The raw selection or message.
        settings: Decides whether the front end runs (``reading.enabled``),
            which word rules apply (an English Kokoro voice), the date
            order, citation handling, the code verbosity level and the
            math style.
        format: ``None`` for plain text, else the message's MIME type.
        formulas: The formulas reader to share; None starts and stops one
            for this call.
    """
    if not settings.reading.enabled:
        yield from plain_segments(text)
        return
    own = formulas is None
    if formulas is None:
        formulas = formulas_for(settings)
    try:
        reader = _Reader(settings, formulas)
        for block in blocks(text, format):
            yield from reader.segments(block)
    finally:
        if own:
            formulas.close()


class BoundChunker:
    """``prepare`` with settings bound; owns the helper for its lifetime."""

    def __init__(self, settings: Settings) -> None:
        """Bind the settings; the helper starts on the first formula."""
        self._settings = settings
        self.formulas = formulas_for(settings)

    @property
    def mathcat(self) -> MathCat | None:
        """The helper client, or None when the helper is not installed."""
        return self.formulas.mathcat

    def __call__(
        self, text: str, format: str | None = None
    ) -> Iterator[Segment]:
        """Segments for one message."""
        return prepare(text, self._settings, format, self.formulas)

    def close(self) -> None:
        """Stop the helper."""
        self.formulas.close()

    def __enter__(self) -> BoundChunker:
        """Use as a context manager around the daemon's life."""
        return self

    def __exit__(self, *exc: object) -> None:
        """Stop the helper."""
        self.close()


def chunker_for(settings: Settings) -> BoundChunker:
    """The engine's chunker for these settings: ``prepare`` with them bound."""
    return BoundChunker(settings)
