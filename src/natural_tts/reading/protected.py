"""Protected spans: text already spoken that later passes must not touch.

A reader wraps words it has produced (an inline code span read aloud, for
example) in private-use sentinels; the lexicon and the normaliser skip
those spans, and ``unprotect`` strips the sentinels at the end. Spaces
inside a span are stored as a third sentinel so the chunker treats the
span as one word and never cuts it.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

OPEN = ""
CLOSE = ""
SPACE = ""
_SPAN = re.compile(f"{OPEN}[^{CLOSE}]*{CLOSE}")


def protect(words: str) -> str:
    """Wrap already-spoken ``words`` so no later pass rewrites them."""
    return OPEN + words.replace(" ", SPACE) + CLOSE


def split_protected(text: str) -> Iterator[tuple[str, bool]]:
    """Yield ``(piece, is_protected)`` in order; protected pieces unwrapped."""
    last = 0
    for match in _SPAN.finditer(text):
        if match.start() > last:
            yield text[last : match.start()], False
        yield match.group(0)[1:-1].replace(SPACE, " "), True
        last = match.end()
    if last < len(text):
        yield text[last:], False


def unprotect(text: str) -> str:
    """Strip the sentinels, restoring the spaces inside spans."""
    return "".join(piece for piece, _ in split_protected(text))
