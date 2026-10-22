import pytest

from natural_tts.reading.numbers import (
    cardinal,
    decimal,
    digits,
    ordinal,
    year,
)


class TestCardinal:
    @pytest.mark.parametrize(
        ("value", "words"),
        [
            (0, "zero"),
            (1, "one"),
            (13, "thirteen"),
            (20, "twenty"),
            (21, "twenty-one"),
            (100, "one hundred"),
            (101, "one hundred one"),
            (999, "nine hundred ninety-nine"),
            (1000, "one thousand"),
            (1001, "one thousand one"),
            (12_345, "twelve thousand three hundred forty-five"),
            (1_000_000, "one million"),
            (2_500_000_000, "two billion five hundred million"),
            (-7, "minus seven"),
        ],
    )
    def test_american_style_without_and(self, value, words):
        assert cardinal(value) == words

    def test_rejects_absurd_magnitudes(self):
        with pytest.raises(ValueError, match="too large"):
            cardinal(10**24)


class TestOrdinal:
    @pytest.mark.parametrize(
        ("value", "words"),
        [
            (1, "first"),
            (2, "second"),
            (3, "third"),
            (4, "fourth"),
            (5, "fifth"),
            (8, "eighth"),
            (9, "ninth"),
            (12, "twelfth"),
            (20, "twentieth"),
            (21, "twenty-first"),
            (100, "one hundredth"),
            (1000, "one thousandth"),
        ],
    )
    def test_ordinals(self, value, words):
        assert ordinal(value) == words


class TestDecimal:
    @pytest.mark.parametrize(
        ("text", "words"),
        [
            ("0.05", "zero point zero five"),
            ("3.14", "three point one four"),
            ("1.0", "one point zero"),
            (".03", "point zero three"),
            ("10,000", "ten thousand"),
            ("1,234.5", "one thousand two hundred thirty-four point five"),
            ("-2.5", "minus two point five"),
        ],
    )
    def test_decimal_digits_are_read_one_by_one(self, text, words):
        assert decimal(text) == words


class TestYear:
    @pytest.mark.parametrize(
        ("value", "words"),
        [
            (2026, "twenty twenty-six"),
            (2000, "two thousand"),
            (2005, "two thousand five"),
            (1999, "nineteen ninety-nine"),
            (1900, "nineteen hundred"),
            (1066, "ten sixty-six"),
        ],
    )
    def test_years_are_read_in_pairs(self, value, words):
        assert year(value) == words


class TestDigits:
    def test_digits_are_read_one_by_one(self):
        assert digits("2024") == "two zero two four"
