"""Content-aware reading: turns a selection into speakable segments.

Pure functions only; nothing here imports an engine. The rules were written
against the project's research notes, with normt2s 0.7.0 (MIT) read as a
reference implementation and its measured outputs kept as golden rows.

``prepare`` is the hotkey path's entry point. It works window by window so
the first segment is ready long before a long selection has been read:
each window is cut at a sentence end, chunked with ``chunk_text``, and each
chunk is rewritten into words and marked with pronunciations. With
``reading.enabled = false`` or a non-English voice it yields exactly
today's chunks.
"""

from __future__ import annotations

import functools
import re
from collections.abc import Callable, Iterator

from natural_tts.config import CHUNK_MAX_CHARS, FIRST_CHUNK_MIN_CHARS, Settings
from natural_tts.reading.lexicon import Lexicon, load_lexicon, packaged_lexicon
from natural_tts.reading.normalize import normalize_words
from natural_tts.segments import Segment
from natural_tts.text import chunk_text

# Text is prepared in windows of this many characters, cut at a sentence
# end, so a 1 MiB selection costs no more before the first word than a page.
WINDOW_CHARS = 8_000
_ENGLISH_LANG_CODES = frozenset("ab")
_SENTENCE_END = re.compile(r"[.!?]\s")


def windows(text: str, size: int = WINDOW_CHARS) -> Iterator[str]:
    """Yield the raw ``text`` in pieces of about ``size`` characters.

    A piece ends after the last sentence end inside the size limit, else at
    the last whitespace, else at the limit itself (one unbroken word). The
    caller cleans each piece; nothing here touches the whole text.
    """
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            ends = [m.end() for m in _SENTENCE_END.finditer(text, start, end)]
            cut = ends[-1] if ends else _last_space(text, start, end)
            if cut > start:
                end = cut
        yield text[start:end]
        start = end


def _last_space(text: str, start: int, end: int) -> int:
    for index in range(end - 1, start, -1):
        if text[index].isspace():
            return index
    return end


@functools.lru_cache(maxsize=1)
def _packaged() -> Lexicon:
    return packaged_lexicon()


def lexicon_for(settings: Settings) -> Lexicon:
    """The packaged lexicon with the user's file merged on top."""
    return _packaged().merged(load_lexicon(settings.paths.lexicon_file))


def prepare(
    text: str, settings: Settings, format: str | None = None
) -> Iterator[Segment]:
    """Turn a selection into segments, lazily.

    Args:
        text: The raw selection or message.
        settings: Decides whether to normalise (``reading.enabled`` and an
            English Kokoro voice), the date order and citation handling.
        format: ``None`` for plain text, else the message's MIME type.
    """
    reading, kokoro = settings.reading, settings.kokoro
    active = reading.enabled and kokoro.lang_code in _ENGLISH_LANG_CODES
    lexicon = lexicon_for(settings) if active else None
    for window in windows(text):
        chunks = chunk_text(window, FIRST_CHUNK_MIN_CHARS, CHUNK_MAX_CHARS)
        for chunk in chunks:
            if lexicon is None:
                yield Segment(chunk)
                continue
            words = normalize_words(
                lexicon.apply(chunk),
                british=kokoro.lang_code == "b",
                citations=reading.citations,
            )
            if words:
                yield Segment(words)


def chunker_for(
    settings: Settings,
) -> Callable[[str, str | None], Iterator[Segment]]:
    """The engine's chunker for these settings: ``prepare`` with them bound."""

    def chunker(text: str, format: str | None = None) -> Iterator[Segment]:
        return prepare(text, settings, format)

    return chunker
