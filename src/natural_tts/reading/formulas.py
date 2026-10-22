"""Formulas: MathML through the MathCAT helper, words otherwise.

A ``MATH`` block carries its source as written (LaTeX, a Unicode formula
run, or MathML) and a language naming which. ``Formulas`` converts the
source to MathML, asks the helper for speech, and says ``None`` when it
cannot, so the reader falls back to the word rules. One ``Formulas`` lives
as long as the daemon's chunker, so one helper process serves every read.
"""

from __future__ import annotations

import logging
import re

from natural_tts.config import Settings
from natural_tts.reading.math import (
    latex_to_mathml,
    nesting_depth,
    unicode_math_to_mathml,
)
from natural_tts.reading.mathcat import MathCat, MathCatUnavailable

LATEX = "latex"
UNICODE = "unicode"
MATHML = "mathml"
# Kokoro language letter -> MathCAT rules language; anything else is English.
LANGUAGES = {"a": "en", "b": "en", "e": "es", "f": "fr", "p": "pt", "z": "zh"}
STYLES = {"clearspeak": "ClearSpeak", "simplespeak": "SimpleSpeak"}
# Fractions inside roots, scripts on scripts: Verbose from this depth on.
VERBOSE_DEPTH = 2
_COMMAND = re.compile(r"\\([A-Za-z]+)")
_TAG = re.compile(r"<[^>]{1,200}>")
_SPACES = re.compile(r"\s+")

log = logging.getLogger(__name__)


def helper_language(lang_code: str) -> str:
    """The MathCAT language for a Kokoro language letter."""
    return LANGUAGES.get(lang_code, "en")


def to_mathml(text: str, language: str | None) -> str | None:
    """MathML for a formula's source, or None when it cannot be converted."""
    if language == LATEX:
        return latex_to_mathml(text)
    if language == UNICODE:
        return unicode_math_to_mathml(text)
    if language == MATHML:
        return " ".join(text.split())
    return None


def fallback_text(text: str, language: str | None) -> str:
    """The source as plain words for the 0.2.0 word rules."""
    if language == LATEX:
        text = _COMMAND.sub(r" \1 ", text).replace("{", " ").replace("}", " ")
    elif language == MATHML:
        text = _TAG.sub(" ", text)
    return _SPACES.sub(" ", text).strip()


def inline_words(pieces: list[tuple[float, str]]) -> str:
    """Join spoken pieces for an inline span: a break becomes a comma."""
    words = ""
    for pause, piece in pieces:
        if not words:
            words = piece
        elif pause > 0:
            words += ", " + piece
        else:
            words += " " + piece
    return words


class Formulas:
    """Speaks formulas through one helper process; None means fall back."""

    def __init__(self, mathcat: MathCat | None, *, style: str) -> None:
        """Keep the helper (None: not installed) and the ClearSpeak name."""
        self.mathcat = mathcat
        self._style = STYLES[style]
        self._warned = False

    def speak(
        self, text: str, language: str | None
    ) -> list[tuple[float, str]] | None:
        """The helper's pieces for a formula, or None to use the word rules."""
        if self.mathcat is None:
            return None
        try:
            mathml = to_mathml(text, language)
        except ImportError as exc:
            self._warn_once(f"LaTeX conversion unavailable: {exc}")
            return None
        if mathml is None:
            return None
        depth = nesting_depth(mathml)
        verbosity = "Verbose" if depth >= VERBOSE_DEPTH else "Medium"
        try:
            pieces = self.mathcat.speak(
                mathml, style=self._style, verbosity=verbosity
            )
        except MathCatUnavailable as exc:
            self._warn_once(f"math helper failed: {exc}")
            return None
        return pieces or None

    def _warn_once(self, reason: str) -> None:
        if not self._warned:
            log.warning("%s; formulas are read as words", reason)
            self._warned = True

    def close(self) -> None:
        """Stop the helper."""
        if self.mathcat is not None:
            self.mathcat.close()


def formulas_for(settings: Settings) -> Formulas:
    """The formulas reader for these settings; warns once when no helper."""
    helper = settings.paths.mathcat_helper
    mathcat: MathCat | None = None
    if helper.is_file():
        mathcat = MathCat(
            [str(helper)], language=helper_language(settings.kokoro.lang_code)
        )
    else:
        log.warning(
            "math helper %s not installed; formulas are read as words "
            "(run natural-tts setup)",
            helper,
        )
    return Formulas(mathcat, style=settings.reading.math_style)
