"""Spell numbers as American English words."""

from __future__ import annotations

_ONES = [
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
]
_TENS = [
    "_",
    "_",
    "twenty",
    "thirty",
    "forty",
    "fifty",
    "sixty",
    "seventy",
    "eighty",
    "ninety",
]
_SCALES = ("", "thousand", "million", "billion", "trillion", "quadrillion")
_MAX = 1000 ** len(_SCALES) - 1
_ORDINAL_IRREGULAR = {
    "one": "first",
    "two": "second",
    "three": "third",
    "five": "fifth",
    "eight": "eighth",
    "nine": "ninth",
    "twelve": "twelfth",
}


def _below_thousand(value: int) -> str:
    words: list[str] = []
    hundreds, rest = divmod(value, 100)
    if hundreds:
        words.append(f"{_ONES[hundreds]} hundred")
    if rest < 20:
        if rest or not hundreds:
            words.append(_ONES[rest])
    else:
        tens, ones = divmod(rest, 10)
        words.append(f"{_TENS[tens]}-{_ONES[ones]}" if ones else _TENS[tens])
    return " ".join(words)


def cardinal(value: int) -> str:
    """Spell an integer ("twenty-one", no "and" before the tens).

    Raises:
        ValueError: above the quadrillions.
    """
    if value < 0:
        return f"minus {cardinal(-value)}"
    if value > _MAX:
        raise ValueError(f"{value} is too large to spell")
    if value < 1000:
        return _below_thousand(value)
    words: list[str] = []
    for scale in _SCALES:
        value, group = divmod(value, 1000)
        if group:
            words.append(f"{_below_thousand(group)} {scale}".rstrip())
        if not value:
            break
    return " ".join(reversed(words))


def ordinal(value: int) -> str:
    """Spell an ordinal ("twenty-first")."""
    words = cardinal(value)
    head, sep, last = words.rpartition("-")
    if not sep:
        head, sep, last = words.rpartition(" ")
    if last in _ORDINAL_IRREGULAR:
        last = _ORDINAL_IRREGULAR[last]
    elif last.endswith("y"):
        last = last[:-1] + "ieth"
    else:
        last += "th"
    return f"{head}{sep}{last}"


def digits(text: str) -> str:
    """Read digits one by one ("two zero two four")."""
    return " ".join(_ONES[int(d)] for d in text)


def decimal(text: str) -> str:
    """Spell ``[-]ddd[,ddd][.ddd]``: integer part as a cardinal, then digits.

    Thousands separators are allowed in the integer part; a leading point
    is read as "point".
    """
    sign = ""
    if text.startswith("-"):
        sign, text = "minus ", text[1:]
    whole, dot, fraction = text.partition(".")
    words = cardinal(int(whole.replace(",", ""))) if whole else ""
    if dot:
        words = f"{words} point {digits(fraction)}".strip()
    return sign + words


def year(value: int) -> str:
    """Read a four-digit year the way it is said ("twenty twenty-six").

    Years ending in 000 to 009 are read as cardinals ("two thousand five").
    """
    century, rest = divmod(value, 100)
    if not 1000 <= value <= 9999 or value % 1000 < 10:
        return cardinal(value)
    return f"{cardinal(century)} {cardinal(rest) if rest else 'hundred'}"
