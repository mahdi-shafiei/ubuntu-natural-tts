"""Text clean-up and chunking for natural-sounding synthesis."""

from __future__ import annotations

import re
import textwrap

_HYPHEN_BREAK = re.compile(r"-\n(?=\w)")
_WHITESPACE = re.compile(r"\s+")
_BOUNDARY = re.compile(r"[.!?;:]\s+")
_COMMA = re.compile(r",\s+")
_BRACKETS = {"(": ")", "[": "]", "{": "}"}
_LEADING_PUNCTUATION = "([{\"'\u201c\u2018"
# English tokens whose trailing full stop does not end a sentence. Kept in
# the standard library on purpose: the daemon's tests enumerate every rule,
# and the one maintained splitter package evaluated (nupunkt, a statistical
# Punkt model) never splits at ";" or ":", which the chunker relies on, so
# it would replace only this list. Other languages get their own lists later.
_ABBREVIATIONS = frozenset(
    {
        "Dr",
        "Mr",
        "Mrs",
        "Ms",
        "Prof",
        "St",
        "Fig",
        "Figs",
        "Eq",
        "Eqs",
        "Ref",
        "Refs",
        "Sec",
        "Tab",
        "Vol",
        "No",
        "vs",
        "al",
        "e.g",
        "i.e",
        "cf",
        "ca",
    }
)


def decode_text(data: bytes) -> str:
    """Decode text from Speech Dispatcher or a pipe.

    UTF-8 is expected; anything that is not valid UTF-8 is decoded as
    ISO-8859-1, which is what Speech Dispatcher's generic module sends for
    languages not declared UTF-8. The result never contains surrogates.
    """
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def clean_text(text: str) -> str:
    """Normalise text copied from PDFs and web pages.

    Re-joins words hyphenated across line breaks and collapses hard line wraps
    and runs of whitespace into single spaces.
    """
    return _WHITESPACE.sub(" ", _HYPHEN_BREAK.sub("", text)).strip()


def _inside_matched_brackets(text: str) -> bytearray:
    """Flag each position that lies inside a matched pair of brackets.

    Unmatched brackets are ignored, so a stray ``(`` cannot suppress every
    later sentence boundary. Linear in the length of ``text``.
    """
    delta = [0] * (len(text) + 1)
    stack: list[tuple[int, str]] = []
    for index, char in enumerate(text):
        closer = _BRACKETS.get(char)
        if closer is not None:
            stack.append((index, closer))
        elif stack and char == stack[-1][1]:
            opened, _ = stack.pop()
            delta[opened] += 1
            delta[index + 1] -= 1
    inside = bytearray(len(text))
    depth = 0
    for index in range(len(text)):
        depth += delta[index]
        inside[index] = depth > 0
    return inside


def _ends_abbreviation(text: str, dot: int) -> bool:
    """Whether the full stop at ``dot`` follows an abbreviation or initial."""
    begin = dot
    while begin > 0 and not text[begin - 1].isspace():
        begin -= 1
    token = text[begin:dot].lstrip(_LEADING_PUNCTUATION)
    return token in _ABBREVIATIONS or (len(token) == 1 and token.isupper())


def split_sentences(text: str) -> list[str]:
    """Split cleaned text at sentence-ending punctuation.

    A boundary is one of ``. ! ? ; :`` followed by whitespace, except after
    an English abbreviation such as ``Dr.`` or ``Fig.`` or a single-letter
    initial, and except inside a matched pair of brackets, so
    ``(n = 3; p < 0.05)`` stays whole. The punctuation stays with the
    sentence before it and the whitespace is dropped, so the words of the
    result are exactly the words of ``text``.

    Args:
        text: Text already passed through :func:`clean_text`.
    """
    inside = _inside_matched_brackets(text)
    sentences: list[str] = []
    start = 0
    for match in _BOUNDARY.finditer(text):
        end = match.start()
        if inside[end] or (text[end] == "." and _ends_abbreviation(text, end)):
            continue
        sentences.append(text[start : end + 1])
        start = match.end()
    if start < len(text):
        sentences.append(text[start:])
    return sentences


def _sentences(text: str, max_len: int) -> list[str]:
    pieces = split_sentences(text)
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
