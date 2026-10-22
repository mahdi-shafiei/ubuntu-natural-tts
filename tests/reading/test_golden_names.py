"""Golden company and product names: spoken text, and phonemes with misaki.

``golden_names.tsv`` rows are ``name, spoken text, phonemes``. The spoken
text is what ``prepare`` emits with the packaged lexicon (checked always);
the phonemes are misaki's reading of that text with its espeak fallback,
checked only when both import, so the phoneme column is skipped with a
visible count in environments without the Kokoro extra.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from natural_tts.reading import prepare
from tests.fakes import make_settings

GOLDEN = Path(__file__).with_name("golden_names.tsv")


def golden_rows() -> Iterator[tuple[str, str, str]]:
    """Yield ``(name, spoken, phonemes)`` rows."""
    for line in GOLDEN.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        name, spoken, phonemes = line.split("\t")
        yield name, spoken, phonemes


ROWS = list(golden_rows())


@pytest.mark.parametrize(("name", "spoken", "phonemes"), ROWS)
def test_spoken_text(tmp_path, name, spoken, phonemes):
    out = " ".join(s.text for s in prepare(name, make_settings(tmp_path)))
    assert out == spoken


@pytest.fixture(scope="module")
def g2p():
    try:
        from misaki import en, espeak
    except ImportError:
        pytest.skip(f"misaki not installed: {len(ROWS)} phoneme rows skipped")
    return en.G2P(
        trf=False, british=False, fallback=espeak.EspeakFallback(british=False)
    )


@pytest.mark.parametrize(("name", "spoken", "phonemes"), ROWS)
def test_phonemes(g2p, name, spoken, phonemes):
    assert g2p(spoken)[0] == phonemes
