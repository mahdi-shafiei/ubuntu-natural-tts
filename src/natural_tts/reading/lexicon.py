"""Pronunciations the engines cannot derive, rendered as Kokoro markup.

The packaged table ships with the package; a user file with the same
schema (``~/.config/natural-tts/lexicon.toml``) is merged on top. Kokoro's
phonemizer reads ``[head](/phonemes/)`` as a pronunciation instruction, so
the renderer keeps punctuation outside the brackets, never nests markup
and leaves a space between adjacent entries.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from natural_tts.reading.protected import protect, split_protected
from natural_tts.reading.tables import MISAKI_ALPHABET

PACKAGED_LEXICON = Path(__file__).parent / "data" / "lexicon.toml"
MATCH_MODES = ("ci", "exact")
# Our own markup only: the target is misaki phonemes, so a Markdown link
# such as [docs](/docs/) is not mistaken for it.
MARKUP = re.compile(
    r"\[[^\]\n]+\]\(/[" + re.escape("".join(sorted(MISAKI_ALPHABET))) + r"]+/\)"
)
_ENTRY_KEYS = {"head", "misaki", "match", "words"}


class LexiconError(ValueError):
    """Raised when a lexicon file or entry is invalid."""


@dataclass(frozen=True)
class Entry:
    """One pronunciation.

    Attributes:
        head: The written form, one or more words.
        misaki: Phonemes in misaki's alphabet; empty when ``words`` is set.
        match: ``"ci"`` (case-insensitive) or ``"exact"``.
        words: Plain-text replacement instead of phoneme markup.
    """

    head: str
    misaki: str
    match: str = "ci"
    words: str = ""

    def __post_init__(self) -> None:
        """Validate the entry."""
        if not self.head.strip():
            raise LexiconError("head must not be blank")
        if self.match not in MATCH_MODES:
            raise LexiconError(f"match must be one of {MATCH_MODES}")
        if not self.words and not self.misaki:
            raise LexiconError(f"{self.head!r}: misaki or words is required")
        if ")" in self.misaki or "(" in self.misaki:
            raise LexiconError(
                f"{self.head!r}: misaki must not contain brackets"
            )
        unknown = set(self.misaki) - MISAKI_ALPHABET
        if unknown:
            raise LexiconError(
                f"{self.head!r}: {''.join(sorted(unknown))!r} "
                "not in misaki's alphabet"
            )

    def spoken(self, written: str) -> str:
        """The replacement for one occurrence of the head."""
        return self.words or f"[{written}](/{self.misaki}/)"


@dataclass(frozen=True)
class Lexicon:
    """An ordered set of entries; longer heads are matched first."""

    entries: tuple[Entry, ...]
    _pattern: re.Pattern[str] = field(init=False, repr=False, compare=False)

    def __init__(self, entries: Iterable[Entry] = ()) -> None:
        """Keep the entries, longest head first, later duplicates winning."""
        by_head: dict[str, Entry] = {}
        for entry in entries:
            by_head[entry.head] = entry
        ordered = sorted(by_head.values(), key=lambda e: -len(e.head))
        object.__setattr__(self, "entries", tuple(ordered))
        object.__setattr__(self, "_pattern", _compile(ordered))

    def merged(self, other: Lexicon) -> Lexicon:
        """A lexicon where ``other``'s entries override this one's."""
        return Lexicon((*self.entries, *other.entries))

    def apply(self, text: str) -> str:
        """Mark each entry outside existing markup and protected spans."""
        if not self.entries:
            return text
        pattern = self._pattern
        pieces: list[str] = []
        for piece, is_protected in split_protected(text):
            if is_protected:
                pieces.append(protect(piece))
                continue
            last = 0
            for markup in MARKUP.finditer(piece):
                gap = piece[last : markup.start()]
                pieces.append(self._apply_gap(pattern, gap))
                pieces.append(markup.group(0))
                last = markup.end()
            pieces.append(self._apply_gap(pattern, piece[last:]))
        return "".join(pieces)

    def _apply_gap(self, pattern: re.Pattern[str], text: str) -> str:
        def replace(match: re.Match[str]) -> str:
            entry = self.entries[int((match.lastgroup or "e0")[1:])]
            return entry.spoken(match.group(0))

        return pattern.sub(replace, text)


def _word_pattern(word: str, case_insensitive: bool) -> str:
    if not case_insensitive:
        return re.escape(word)
    return "".join(
        f"[{c.upper()}{c.lower()}]" if c.isalpha() else re.escape(c)
        for c in word
    )


def _compile(entries: Sequence[Entry]) -> re.Pattern[str]:
    if not entries:
        return re.compile(r"(?!)")
    parts = []
    for index, entry in enumerate(entries):
        words = [
            _word_pattern(word, entry.match == "ci")
            for word in entry.head.split()
        ]
        head = r"\s+".join(words)
        parts.append(rf"(?P<e{index}>(?<![\w\[]){head}(?!\w))")
    return re.compile("|".join(parts))


def load_lexicon(path: Path) -> Lexicon:
    """Load a lexicon file; a missing file is an empty lexicon.

    Raises:
        LexiconError: if the file is not valid TOML or an entry is invalid.
    """
    if not path.exists():
        return Lexicon()
    try:
        data = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as exc:
        raise LexiconError(f"invalid TOML in {path}: {exc}") from exc
    entries = []
    for raw in data.get("entry", []):
        unknown = set(raw) - _ENTRY_KEYS
        if unknown:
            raise LexiconError(
                f"{path}: unknown key {sorted(unknown)[0]!r} in entry"
            )
        entries.append(
            Entry(
                head=str(raw.get("head", "")),
                misaki=str(raw.get("misaki", "")),
                match=str(raw.get("match", "ci")),
                words=str(raw.get("words", "")),
            )
        )
    return Lexicon(entries)


def packaged_lexicon() -> Lexicon:
    """The lexicon shipped with natural-tts."""
    return load_lexicon(PACKAGED_LEXICON)
