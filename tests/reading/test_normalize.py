import re
import time
from pathlib import Path

import pytest

from natural_tts.reading.normalize import normalize_words

GOLDEN = Path(__file__).with_name("golden.tsv")


def golden_rows():
    for line in GOLDEN.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        text, expected, note = line.split("\t")
        yield pytest.param(text, expected, id=f"{note}: {text[:40]}")


@pytest.mark.parametrize(("text", "expected"), list(golden_rows()))
def test_golden(text, expected):
    assert normalize_words(text) == expected


class TestOptions:
    def test_citations_can_be_read(self):
        assert normalize_words("as shown [12].", citations="read") == (
            "as shown reference twelve."
        )
        assert normalize_words("see [1-3].", citations="read") == (
            "see references one to three."
        )

    def test_british_dates_are_day_first(self):
        assert normalize_words("03/04/2026", british=True) == (
            "the third of April twenty twenty-six"
        )
        assert normalize_words("21 October 2026", british=True) == (
            "the twenty-first of October twenty twenty-six"
        )

    def test_rejects_unknown_citation_mode(self):
        with pytest.raises(ValueError, match="citations"):
            normalize_words("x", citations="drop")


class TestRobustness:
    @pytest.mark.parametrize(
        "text",
        [
            "(" * 20_000,
            "(" + "A" * 44 + ", 2019)",
            "(" + "A, " * 2000 + "2019)",
            "$" * 20_000,
            "1." * 20_000,
            "a-" * 20_000,
            "<" * 20_000,
            "e.g." * 5_000,
            "[1, " * 5_000,
            "x^" * 10_000,
            "http://" + "a." * 10_000,
        ],
    )
    def test_adversarial_input_is_linear(self, text):
        start = time.perf_counter()
        normalize_words(text)
        assert time.perf_counter() - start < 0.5

    def test_hundred_kilobytes_within_budget(self):
        text = "We used buffer at 37 °C (n = 3; p < 0.05), see Eq. 2. " * 1900
        assert len(text) > 100_000
        start = time.perf_counter()
        out = normalize_words(text)
        assert time.perf_counter() - start < 0.3
        assert "Equation two" in out

    def test_output_is_single_spaced_and_stripped(self):
        out = normalize_words("  p  <  0.05 ,  see  Fig. 3 .  ")
        assert out == out.strip() and "  " not in out
        assert not re.search(r"\s[,.;:]", out)
