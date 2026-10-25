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
)
from natural_tts.reading.lexicon import Lexicon, load_lexicon, packaged_lexicon
from natural_tts.reading.math import find_math_spans
from natural_tts.reading.mathcat import MathCat, sentence
from natural_tts.reading.normalize import normalize_words
from natural_tts.reading.numbers import cardinal
from natural_tts.reading.protected import protect, unprotect
from natural_tts.reading.structure import blocks
from natural_tts.segments import Kind, Segment
from natural_tts.text import chunk_text

_ENGLISH_LANG_CODES = frozenset("ab")
# Pauses are the whole gap between two segments (the engine trims its own
# edge silence, as kokoro-onnx and Kokoro-FastAPI do). The gap is keyed on
# how the previous segment ended, the mechanism both of those pipelines use
# (kokoro-onnx: 0.10 s after ",;:", 0.25 s after ".!?"; Kokoro-FastAPI:
# 0.41 s scaled 0.8-1.0 by the final mark). The ladder clause < sentence <
# paragraph at about 1:2:4 follows the read-speech corpora (Doukhan 2012:
# medians 386 / 720 / 1127 ms; Farrús 2016: paragraph 1.6-2.8x sentence)
# and the finding that listeners notice the ordering, not the exact values
# (Owoicho 2024). No reader surveyed holds a heading constant; a heading is
# treated as a paragraph on both sides. Table rows take the 750 ms row-end
# pause measured by Spiliotopoulos et al. (research/reports/Reading tables
# aloud.md). The research is in research/reports/Segment pauses and
# formula breaks.md.
CLAUSE_PAUSE = 0.2
SENTENCE_PAUSE = 0.4
PARAGRAPH_PAUSE = 0.8
PAUSES: dict[Kind, float] = {
    Kind.PROSE: PARAGRAPH_PAUSE,
    Kind.HEADING: PARAGRAPH_PAUSE,
    Kind.LIST_ITEM: SENTENCE_PAUSE,
    Kind.QUOTE: PARAGRAPH_PAUSE,
    Kind.CODE: PARAGRAPH_PAUSE,
    Kind.MATH: PARAGRAPH_PAUSE,
    Kind.TABLE: PARAGRAPH_PAUSE,
}
TABLE_ROW_PAUSE = 0.75
RATES: dict[Kind, float] = {Kind.HEADING: 0.9, Kind.CODE: 0.9}
# Sentence-ending marks: NVDA's say-all regex ([.!?]) plus the ":" and
# ";" that the chunker and Kokoro-FastAPI's join_lines treat as ends.
_SENTENCE_END = (".", "!", "?", ";", ":")
# Kinds that can continue each other's sentence across a block boundary
# ("The Gaussian integral", a display formula, "follows from"). No reader
# surveyed detects this; every one splits at the block (research report).
_CONTINUABLE = frozenset({Kind.PROSE, Kind.MATH})
# Blocks that are complete units: a final full stop closes the voice's
# contour (Kokoro-FastAPI join_lines appends "." to unpunctuated lines).
_CLOSED = frozenset({Kind.HEADING, Kind.LIST_ITEM})
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
        self._last: Segment | None = None

    def segments(self, block: Block) -> Iterator[Segment]:
        """Turn one block into segments."""
        if block.kind is Kind.CODE:
            produced = self._code(block)
        elif block.kind is Kind.MATH:
            produced = self._math(block)
        elif block.kind is Kind.TABLE:
            produced = self._table(block)
        else:
            produced = self._prose(block)
        for segment in produced:
            self._last = segment
            yield segment

    def _block_pause(self, kind: Kind, text: str) -> float:
        """The gap before a block's first segment.

        A prose or math block that continues the previous segment's
        sentence gets a clause pause: the previous prose had no
        sentence-ending punctuation, or this prose starts in lower case
        after a formula ("The Gaussian integral", the formula, "follows").
        """
        last = self._last
        if last is None or kind not in _CONTINUABLE:
            return PAUSES[kind]
        if last.kind is Kind.PROSE and not last.text.rstrip().endswith(
            _SENTENCE_END
        ):
            return CLAUSE_PAUSE
        if last.kind is Kind.MATH and text[:1].islower():
            return CLAUSE_PAUSE
        return PAUSES[kind]

    def _segment(
        self, text: str, kind: Kind, pause: float, rate: float = 1.0
    ) -> Segment:
        return Segment(text, kind=kind, pause_before=pause, rate=rate)

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
            pieces = self._math_pieces(span.latex, LATEX)
            words = sentence(pieces)
            if words:
                out.append(protect(words))
            last = span.end
        out.append(text[last:])
        return "".join(out)

    def _math(self, block: Block) -> Iterator[Segment]:
        # One engine call per formula: the helper's breaks become
        # punctuation (see ``mathcat.sentence``).
        words = sentence(self._math_pieces(block.text, block.language))
        if words:
            yield self._segment(
                words, Kind.MATH, self._block_pause(Kind.MATH, words)
            )

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
        pause = self._block_pause(block.kind, text)
        chunks = chunk_text(text, FIRST_CHUNK_MIN_CHARS, CHUNK_MAX_CHARS)
        for index, chunk in enumerate(chunks):
            words = self._words(chunk)
            if not words:
                continue
            if (
                block.kind in _CLOSED
                and index == len(chunks) - 1
                and not words.endswith(_SENTENCE_END)
            ):
                words += "."
            yield self._segment(
                words, block.kind, pause, RATES.get(block.kind, 1.0)
            )
            pause = _chunk_pause(words)

    def _code(self, block: Block) -> Iterator[Segment]:
        lines = read_code(block.text, language=block.language, level=self.level)
        group: list[str] = []
        pause = PAUSES[Kind.CODE]
        for line in lines:
            if (
                group
                and sum(len(g) + 2 for g in group) + len(line) > CHUNK_MAX_CHARS
            ):
                yield self._segment(
                    ". ".join(group), Kind.CODE, pause, RATES[Kind.CODE]
                )
                group, pause = [], SENTENCE_PAUSE
            group.append(line)
        if group:
            yield self._segment(
                ". ".join(group), Kind.CODE, pause, RATES[Kind.CODE]
            )

    def _table(self, block: Block) -> Iterator[Segment]:
        # Caption, shape, the column names once, one sentence per cell with
        # its column name, the row heading bare, "blank" for an empty cell,
        # and an explicit end; rows get the long pause.
        pause = PAUSES[Kind.TABLE]
        if block.caption:
            yield self._segment(self._words(block.caption), Kind.TABLE, pause)
            pause = SENTENCE_PAUSE
        width = max(len(block.columns), *(len(r) for r in block.rows), 0)
        shape = "Table with {} and {}.".format(
            _count(len(block.rows), "row"), _count(width, "column")
        )
        yield self._segment(shape, Kind.TABLE, pause)
        columns = block.columns + ("",) * (width - len(block.columns))
        if block.columns:
            names = ", ".join(c for c in block.columns if c)
            yield self._segment(
                self._words(f"Columns: {names}."), Kind.TABLE, SENTENCE_PAUSE
            )
        for row in block.rows:
            yield self._segment(
                self._words(_row_sentences(columns, row, block.row_headers)),
                Kind.TABLE,
                TABLE_ROW_PAUSE,
            )
        yield self._segment("End of table.", Kind.TABLE, TABLE_ROW_PAUSE)


def _row_sentences(
    columns: tuple[str, ...], row: tuple[str, ...], row_headers: bool
) -> str:
    cells = list(row) + [""] * (len(columns) - len(row))
    parts: list[str] = []
    start = 0
    if row_headers:
        parts.append(f"{cells[0] or 'blank'}.")
        start = 1
    for name, cell in zip(columns[start:], cells[start:], strict=False):
        value = cell or "blank"
        parts.append(f"{name}: {value}." if name else f"{value}.")
    return " ".join(parts)


def _chunk_pause(previous: str) -> float:
    """The gap before the next chunk of the same block."""
    if previous.rstrip().endswith(_SENTENCE_END):
        return SENTENCE_PAUSE
    return CLAUSE_PAUSE


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}{'' if n == 1 else 's'}"


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
