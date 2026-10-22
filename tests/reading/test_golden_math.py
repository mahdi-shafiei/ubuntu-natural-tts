"""Golden math rows recorded from the real helper.

Each row of ``golden_math.tsv`` is ``source, language, style, expected``:
the words the inline reader produces (breaks as commas) for ClearSpeak or
SimpleSpeak Medium, Verbose from nesting depth 2. ``fallback`` as the
expected text means the formula is left to the word rules. The helper is
looked for in ``NATURAL_TTS_MATHCAT``, then in the repository's release
build; without it the rows are skipped with their count.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from natural_tts.reading.formulas import Formulas, inline_words
from natural_tts.reading.mathcat import MathCat

GOLDEN = Path(__file__).with_name("golden_math.tsv")
REPO_BUILD = (
    Path(__file__).resolve().parents[2]
    / "helper/mathcat/target/release/natural-tts-mathcat"
)
FALLBACK = "fallback"


def golden_rows() -> Iterator[tuple[str, str, str, str]]:
    """Yield ``(source, language, style, expected)`` rows."""
    for line in GOLDEN.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        source, language, style, expected = line.split("\t")
        yield source, language, style, expected


ROWS = list(golden_rows())


def helper_path() -> Path | None:
    """The real helper binary, or None when none is available."""
    named = os.environ.get("NATURAL_TTS_MATHCAT")
    for candidate in ([Path(named)] if named else []) + [REPO_BUILD]:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


@pytest.fixture(scope="module")
def mathcat() -> Iterator[MathCat]:
    helper = helper_path()
    if helper is None:
        pytest.skip(
            f"MathCAT helper not built: {len(ROWS)} golden rows skipped"
        )
    with MathCat([str(helper)]) as client:
        yield client


@pytest.mark.parametrize(("source", "language", "style", "expected"), ROWS)
def test_golden(mathcat, source, language, style, expected):
    pieces = Formulas(mathcat, style=style).speak(source, language)
    if expected == FALLBACK:
        assert pieces is None
    else:
        assert pieces is not None
        assert inline_words(pieces) == expected


def test_rows_cover_both_styles_and_both_sources():
    styles = {row[2] for row in ROWS}
    languages = {row[1] for row in ROWS}
    assert styles == {"clearspeak", "simplespeak"}
    assert languages == {"latex", "unicode"}
    assert len(ROWS) >= 40
