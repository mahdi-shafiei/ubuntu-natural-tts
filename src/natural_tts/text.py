"""Text clean-up and chunking for natural-sounding synthesis."""

from __future__ import annotations

import re
import textwrap

_HYPHEN_BREAK = re.compile(r"-\n(?=\w)")
_WHITESPACE = re.compile(r"\s+")
_SENTENCE_END = re.compile(r"(?<=[.!?;:])\s+")
_COMMA = re.compile(r",\s+")


def clean_text(text: str) -> str:
    """Normalise text copied from PDFs and web pages.

    Re-joins words hyphenated across line breaks and collapses hard line wraps
    and runs of whitespace into single spaces.
    """
    return _WHITESPACE.sub(" ", _HYPHEN_BREAK.sub("", text)).strip()


def _sentences(text: str, max_len: int) -> list[str]:
    pieces = [s for s in _SENTENCE_END.split(text) if s]
    # Unpunctuated runs are wrapped at word boundaries; a single word longer
    # than max_len (e.g. a URL) is kept whole rather than cut in half.
    return [
        part
        for piece in pieces
        for part in textwrap.wrap(
            piece, max_len, break_long_words=False, break_on_hyphens=False
        )
    ]


def _split_opening(sentence: str, first_min: int) -> tuple[str, str] | None:
    """Split a long opening sentence at its first comma past first_min / 2."""
    if len(sentence) <= 2 * first_min:
        return None
    offset = first_min // 2
    match = _COMMA.search(sentence, offset)
    if match is None:
        return None
    return sentence[: match.start() + 1], sentence[match.end() :]


def chunk_text(text: str, first_min: int, max_len: int) -> list[str]:
    """Split text into chunks suited to neural TTS.

    The first chunk is kept short (at least ``first_min`` characters when the
    text allows) so speech starts quickly; later chunks group whole sentences
    up to ``max_len`` characters.

    Args:
        text: Raw text, e.g. a selection copied from a PDF.
        first_min: Minimum length the first chunk grows to.
        max_len: Maximum chunk length (exceeded only by a single word longer
            than ``max_len``).

    Returns:
        Non-empty, stripped chunks whose words are exactly those of
        ``clean_text(text)``.

    Raises:
        ValueError: if ``not 0 < first_min <= max_len``.
    """
    if not 0 < first_min <= max_len:
        raise ValueError("first_min must satisfy 0 < first_min <= max_len")
    sentences = _sentences(clean_text(text), max_len)
    chunks: list[str] = []
    if sentences:
        opening = _split_opening(sentences[0], first_min)
        if opening is not None:
            chunks.append(opening[0])
            sentences[0] = opening[1]
    current = ""
    for sentence in sentences:
        limit = max_len if chunks else first_min
        full = len(current) >= limit
        if current and (full or len(current) + 1 + len(sentence) > max_len):
            chunks.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}" if current else sentence
    if current:
        chunks.append(current)
    return chunks
