import re
import time
from pathlib import Path

import pytest

from natural_tts.reading.normalize import normalize_words, spell_markup
from natural_tts.reading.tables import LETTER_PHONEMES, MISAKI_ALPHABET

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

    def test_hundred_kilobytes_cost_linear_time(self):
        # Measured as a ratio (ten times the text, at most twelve times the
        # time) so coverage tracing and shared CI runners cannot fail it; the
        # absolute cost is recorded with the release evidence.
        sentence = "We used buffer at 37 °C (n = 3; p < 0.05), see Eq. 2. "
        page, large = sentence * 190, sentence * 1900
        assert len(large) > 100_000

        def cost(text):
            start = time.perf_counter()
            out = normalize_words(text)
            assert "Equation two" in out
            return time.perf_counter() - start

        small = min(cost(page) for _ in range(3))
        big = min(cost(large) for _ in range(3))
        assert big < 12 * small + 0.01

    def test_output_is_single_spaced_and_stripped(self):
        out = normalize_words("  p  <  0.05 ,  see  Fig. 3 .  ")
        assert out == out.strip() and "  " not in out
        assert not re.search(r"\s[,.;:]", out)


class TestSpelling:
    def test_letter_table_covers_the_alphabet_in_misakis_alphabet(self):
        assert sorted(LETTER_PHONEMES) == list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
        for phonemes in LETTER_PHONEMES.values():
            assert set(phonemes) <= MISAKI_ALPHABET

    def test_one_word_with_primary_stress_on_the_last_letter(self):
        # misaki's own convention for an unknown capital run (get_NNP).
        assert spell_markup("DNA") == "[DNA](/dˌiˌɛnˈA/)"
        assert spell_markup("ODE") == "[ODE](/ˌOdˌiˈi/)"
        assert spell_markup("W") == "[W](/dˈʌbᵊlju/)"

    def test_plural_and_possessive_follow_the_last_letter_name(self):
        assert spell_markup("GPU", "s") == "[GPUs](/ʤˌipˌijˈuz/)"
        assert spell_markup("PDF", "s") == "[PDFs](/pˌidˌiˈɛfs/)"
        assert spell_markup("FAQ", "s") == "[FAQs](/ˌɛfˌAkjˈuz/)"
        assert spell_markup("OS", "s") == "[OSs](/ˌOˈɛsɪz/)"
        assert spell_markup("UN", "'s") == "[UN's](/jˌuˈɛnz/)"

    def test_lowercase_letters_are_spelled_with_the_same_names(self):
        assert spell_markup("df") == "[df](/dˌiˈɛf/)"


class TestFormulaGuard:
    def test_long_brand_names_are_not_chemical_formulas(self):
        # Every piece of AmWINS and OCSiAl is an element symbol; they are
        # brands, and six letters without a count is not a formula.
        assert (
            normalize_words("AmWINS Group and OCSiAl")
            == "AmWINS Group and OCSiAl"
        )

    def test_short_formulas_and_counted_ones_still_are(self):
        assert normalize_words("NaOH and KMnO4") == (
            "[NaOH](/ˌɛnˌAˌOˈAʧ/) and [KMnO](/kˌAˌɛmˌɛnˈO/) four"
        )
