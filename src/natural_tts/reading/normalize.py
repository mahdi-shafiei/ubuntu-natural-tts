"""Rewrite English prose into the words a reader would say.

``normalize_words`` runs a fixed list of rules over a cleaned selection:
links, URLs, citations, dates, times, versions, scientific notation,
currency, ranges, units, abbreviations, symbols, mixed tokens and plain
numbers, in that order. Every pattern is linear (no nested quantifiers,
possessive where a run could be re-matched), and the golden file in the
tests is the specification.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from natural_tts.config import CITATION_MODES
from natural_tts.reading import tables
from natural_tts.reading.lexicon import MARKUP
from natural_tts.reading.numbers import cardinal, decimal, digits, ordinal, year

_NUMBER = r"\d+(?:,\d{3})*(?:\.\d+)?|\.\d+"
_UNIT_KEYS = sorted(
    {*tables.UNITS}
    | {
        prefix + unit
        for unit, prefixes in tables.PREFIXED_UNITS.items()
        for prefix in prefixes
    },
    key=len,
    reverse=True,
)
_UNIT = "|".join(re.escape(u) for u in _UNIT_KEYS)
_LETTER_NAMES = {"A": "A."}  # a bare capital A is read as the article


@dataclass(frozen=True)
class Options:
    """What the reader's voice and settings ask for."""

    british: bool = False
    citations: str = "skip"


Rule = Callable[[str, Options], str]


def _sub(pattern: str, flags: int = 0) -> Callable[[Callable[..., str]], Rule]:
    compiled = re.compile(pattern, flags)

    def wrap(replace: Callable[..., str]) -> Rule:
        def rule(text: str, options: Options) -> str:
            return compiled.sub(lambda m: replace(m, options), text)

        rule.__name__ = replace.__name__
        return rule

    return wrap


def _num(text: str) -> str:
    return decimal(text.replace(",", "")) if text else ""


def _plural(count: str, singular: str, plural: str) -> str:
    if not plural:
        return singular
    return singular if count.replace(",", "") in {"1", "1.0"} else plural


def _spell(letters: str) -> str:
    return " ".join(_LETTER_NAMES.get(c, c) for c in letters)


# -- links, URLs, e-mail ----------------------------------------------------


@_sub(r"\[([^\[\]\n]{1,200}+)\]\([^()\s]{1,2000}+\)")
def _markdown_links(m: re.Match[str], _: Options) -> str:
    # A Markdown link reads as its text; misaki would otherwise take
    # [text](target) for pronunciation markup and drop the words.
    return m.group(1)


@_sub(r"\]\(")
def _break_links(m: re.Match[str], _: Options) -> str:
    # Any leftover "](" pair is broken so misaki cannot misread it.
    return "] ("


@_sub(r"\b(?:https?://|www\.)([\w.-]++)(/[^\s)\]]*+)?[^\s)\]]*")
def _url(m: re.Match[str], _: Options) -> str:
    host = m.group(1).removeprefix("www.").rstrip(".").replace(".", " dot ")
    path = (m.group(2) or "").rstrip("/").strip("/")
    words = [host]
    if path:
        words += ["slash " + part for part in path.split("/") if part]
    return " ".join(words)


@_sub(r"\b([\w.+-]{1,64}+)@([\w-]++(?:\.[\w-]++)*+)\b")
def _email(m: re.Match[str], _: Options) -> str:
    user, host = (g.replace(".", " dot ") for g in m.groups())
    return f"{user} at {host}"


# -- citations ---------------------------------------------------------------

_NUMERIC_CITATION = r"\[(\d{1,4})(?:\s?[-–,]\s?(\d{1,4}))*+\]"
# "(Smith et al., 2019; Doe and Roe, 2020)": each entry is at most 80
# characters of name text, then a year. No nested repeats, so a run of
# capital letters cannot blow up (the research measured 17 s for a naive
# pattern on 40 letters).
_AUTHOR_YEAR = r"\((?:[^()\d]{1,80}+(?:19|20)\d\d[a-z]?(?:; )?)++\)"


def _citations(text: str, options: Options) -> str:
    if options.citations == "read":
        return re.sub(_NUMERIC_CITATION, _read_citation, text)
    text = re.sub(r"\s?" + _NUMERIC_CITATION, "", text)
    text = re.sub(r"\s?" + _AUTHOR_YEAR, "", text)
    # Superscript digits right after a word are footnote or citation marks.
    return re.sub(r"(?<=[A-Za-z]{2})[⁰¹²³⁴⁵⁶⁷⁸⁹]++", "", text)


def _read_citation(m: re.Match[str]) -> str:
    spoken: list[str] = []
    for part in re.split(r"[,;]", m.group(0)[1:-1]):
        bounds = re.split(r"\s?[-–]\s?", part.strip(), maxsplit=1)
        spoken.append(" to ".join(cardinal(int(b)) for b in bounds))
    plural = len(spoken) > 1 or " to " in spoken[0]
    label = "references" if plural else "reference"
    return f"{label} {', '.join(spoken)}"


# -- dates and times ---------------------------------------------------------

_MONTH_WORDS = "|".join(tables.MONTHS + list(tables.MONTH_ABBREVIATIONS))


def _date_words(month: int, day: int, yr: int | None, british: bool) -> str:
    name = tables.MONTHS[month - 1]
    when = (
        f"the {ordinal(day)} of {name}" if british else f"{name} {ordinal(day)}"
    )
    if yr is None:
        return when
    return f"{when} {year(yr)}" if british else f"{when}, {year(yr)}"


@_sub(r"\b(\d{4})-(\d{2})-(\d{2})\b")
def _iso_date(m: re.Match[str], options: Options) -> str:
    return _date_words(
        int(m.group(2)), int(m.group(3)), int(m.group(1)), options.british
    )


@_sub(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
def _slash_date(m: re.Match[str], options: Options) -> str:
    first, second, yr = (int(g) for g in m.groups())
    month, day = (second, first) if options.british else (first, second)
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return m.group(0)
    return _date_words(month, day, yr, options.british)


@_sub(rf"\b({_MONTH_WORDS})\.? (\d{{1,2}})(?:st|nd|rd|th)?(?:, (\d{{4}}))?\b")
def _month_day(m: re.Match[str], options: Options) -> str:
    name = tables.MONTH_ABBREVIATIONS.get(m.group(1), m.group(1))
    month = tables.MONTHS.index(name) + 1
    yr = int(m.group(3)) if m.group(3) else None
    if yr is None:
        return f"{name} {cardinal(int(m.group(2)))}"
    return _date_words(month, int(m.group(2)), yr, options.british)


@_sub(rf"\b(\d{{1,2}}) ({_MONTH_WORDS})\.? (\d{{4}})\b")
def _day_month(m: re.Match[str], options: Options) -> str:
    name = tables.MONTH_ABBREVIATIONS.get(m.group(2), m.group(2))
    return _date_words(
        tables.MONTHS.index(name) + 1,
        int(m.group(1)),
        int(m.group(3)),
        options.british,
    )


@_sub(r"\b(\d{1,2}):(\d{2})\b(?:\s?([ap])\.?m\.?(?![\w]))?")
def _time(m: re.Match[str], _: Options) -> str:
    hour, minute = int(m.group(1)), int(m.group(2))
    suffix = f" {m.group(3).upper()} M" if m.group(3) else ""
    if hour > 24 or minute > 59:
        return f"{cardinal(hour)} to {cardinal(int(m.group(2)))}"
    if minute == 0:
        return (
            f"{cardinal(hour)}{suffix or ' hundred'}"
            if hour > 12
            else f"{cardinal(hour)} o'clock{suffix}"
        )
    if minute < 10:
        return f"{cardinal(hour)} oh {cardinal(minute)}{suffix}"
    return f"{cardinal(hour)} {cardinal(minute)}{suffix}"


@_sub(r"\b(\d{1,3}):(\d{3,5})\b")
def _ratio(m: re.Match[str], _: Options) -> str:
    return f"{cardinal(int(m.group(1)))} to {cardinal(int(m.group(2)))}"


@_sub(r"\b(\d{1,3}):(\d)\b(?!:)")
def _small_ratio(m: re.Match[str], _: Options) -> str:
    return f"{cardinal(int(m.group(1)))} to {cardinal(int(m.group(2)))}"


@_sub(r"\b(\d{1,2}) ?([ap])\.m\.(?!\w)")
def _am_pm(m: re.Match[str], _: Options) -> str:
    return f"{cardinal(int(m.group(1)))} {m.group(2).upper()} M"


# -- versions, scientific notation, currency, ranges -----------------------


@_sub(r"\b(v)?(\d+)\.(\d+)\.(\d+)(?:\.(\d+))?\b")
def _version(m: re.Match[str], _: Options) -> str:
    parts = " point ".join(cardinal(int(g)) for g in m.groups()[1:] if g)
    return f"version {parts}" if m.group(1) else parts


@_sub(r"\b([A-Z][a-z]+) (\d{1,3})\.(\d{1,3})\b(?!\.)")
def _product_version(m: re.Match[str], _: Options) -> str:
    # "Python 3.12", "Ubuntu 24.04": a version after a product name, read
    # as whole numbers ("three point twelve", "twenty-four point oh four").
    name, major, minor = m.groups()
    oh = "oh " if minor.startswith("0") and len(minor) > 1 else ""
    return f"{name} {cardinal(int(major))} point {oh}{cardinal(int(minor))}"


@_sub(r"\bv(\d+)\.(\d+)\b")
def _short_version(m: re.Match[str], _: Options) -> str:
    return (
        f"version {cardinal(int(m.group(1)))} point {cardinal(int(m.group(2)))}"
    )


@_sub(rf"\b({_NUMBER})\s?(?:[×x*]\s?10\^?|[eE])(-?\d+)\b")
def _scientific(m: re.Match[str], _: Options) -> str:
    exponent = int(m.group(2))
    power = (
        f"minus {cardinal(-exponent)}" if exponent < 0 else cardinal(exponent)
    )
    return f"{_num(m.group(1))} times ten to the power of {power}"


@_sub(r"([$€£¥])\s?(\d+(?:,\d{3})*)(?:\.(\d{2}))?\b")
def _currency(m: re.Match[str], _: Options) -> str:
    major, majors, minor, minors = tables.CURRENCIES[m.group(1)]
    amount = int(m.group(2).replace(",", ""))
    words = f"{cardinal(amount)} {major if amount == 1 else majors}"
    if m.group(3) and int(m.group(3)) and minor:
        cents = int(m.group(3))
        words += f" and {cardinal(cents)} {minor if cents == 1 else minors}"
    return words


@_sub(rf"({_NUMBER})\s?[–-]\s?({_NUMBER})(?=\s?(?:{_UNIT})\b|\s?%|$|[\s,.;:)])")
def _range(m: re.Match[str], _: Options) -> str:
    return f"{m.group(1)} to {m.group(2)}"


# -- units -------------------------------------------------------------------


def _unit_words(symbol: str, count: str) -> str | None:
    if symbol in tables.UNITS:
        return _plural(count, *tables.UNITS[symbol])
    prefix, base = symbol[0], symbol[1:]
    if base in tables.PREFIXED_UNITS and prefix in tables.PREFIXED_UNITS[base]:
        singular, plural = tables.UNITS[base]
        name = tables.PREFIXES[prefix]
        return _plural(
            count, name + singular, (name + plural) if plural else ""
        )
    return None


@_sub(rf"({_NUMBER})\s?({_UNIT})(?:/({_UNIT}))?(?![\w%])")
def _units(m: re.Match[str], _: Options) -> str:
    words = _unit_words(m.group(2), m.group(1))
    if words is None:
        return m.group(0)
    if m.group(3):
        per = _unit_words(m.group(3), "1")
        if per is None:
            return m.group(0)
        words = f"{words} per {per}"
    return f"{_num(m.group(1))} {words}"


@_sub(r"\b([a-zA-Z]+)/([a-zA-Z]+)\b")
def _unit_per_unit(m: re.Match[str], _: Options) -> str:
    left, right = _unit_words(m.group(1), "2"), _unit_words(m.group(2), "1")
    if left is None or right is None or len(m.group(1)) > 3:
        return m.group(0)
    return f"{left} per {right}"


# -- abbreviations -----------------------------------------------------------

_NUMBERED = "|".join(sorted(tables.NUMBERED, key=len, reverse=True))
_TITLES = "|".join(sorted(tables.TITLES, key=len, reverse=True))
_MONTH_ABBR = "|".join(tables.MONTH_ABBREVIATIONS)
_DAY_ABBR = "|".join(sorted(tables.DAY_ABBREVIATIONS, key=len, reverse=True))


@_sub(rf"\b({_NUMBERED})\.\s?(?=\(?(?:\d|[IVX]+\b))")
def _numbered(m: re.Match[str], _: Options) -> str:
    return tables.NUMBERED[m.group(1)] + " "


def _always(text: str, _: Options) -> str:
    for written, spoken in tables.ALWAYS.items():
        pattern = r"(?<![\w.])" + re.escape(written) + r"(?![\w.])"
        if written == "etc.":
            text = re.sub(pattern + r"(?=\s[A-Z]|$)", spoken + ".", text)
            text = re.sub(pattern, spoken, text)
        else:
            text = re.sub(pattern, spoken, text, flags=re.IGNORECASE)
    # "et al." keeps its full stop only where it ends a sentence.
    text = re.sub(r"\bet al\.(?=\s[A-Z]|$)", "et al\x00", text)
    text = re.sub(r"\bet al\.", "et al", text)
    return text.replace("\x00", ".")


@_sub(r"\bSt\.\s(?=[A-Z])")
def _saint(m: re.Match[str], _: Options) -> str:
    return "Saint "


@_sub(r"(?<=[A-Z][a-z]\w\s)St\.(?!\w)|(?<=\d\s)St\.(?!\w)")
def _street(m: re.Match[str], _: Options) -> str:
    return "Street"


@_sub(r"\b(\d+ [A-Z][a-z]+) Dr\.(?!\w)")
def _drive(m: re.Match[str], _: Options) -> str:
    return f"{m.group(1)} Drive"


@_sub(r"\bDr\.(?=\s)")
def _doctor(m: re.Match[str], _: Options) -> str:
    return "Doctor"


@_sub(rf"\b({_TITLES})\.(?!\w)")
def _titles(m: re.Match[str], _: Options) -> str:
    return tables.TITLES[m.group(1)]


@_sub(rf"\b({_MONTH_ABBR})\.(?!\w)")
def _months(m: re.Match[str], _: Options) -> str:
    return tables.MONTH_ABBREVIATIONS[m.group(1)]


@_sub(rf"\b({_DAY_ABBR})\.(?!\w)")
def _days(m: re.Match[str], _: Options) -> str:
    return tables.DAY_ABBREVIATIONS[m.group(1)]


@_sub(r"\b(?:[A-Za-z]{1,2}\.){2,}+(?!\w)")
def _dotted(m: re.Match[str], _: Options) -> str:
    # U.S., Ph.D., d.f.: letters, said one by one.
    return _spell(m.group(0).replace(".", ""))


# -- symbols -----------------------------------------------------------------


def _power_words(value: int) -> str:
    if value == 2:
        return " squared"
    if value == 3:
        return " cubed"
    sign = "minus " if value < 0 else ""
    return f" to the power of {sign}{cardinal(abs(value))}"


@_sub(r"(?<=[\w)])\^(-?\d+)\b|(?<=[\w)])\*\*(-?\d+)\b")
def _caret(m: re.Match[str], _: Options) -> str:
    return _power_words(int(m.group(1) or m.group(2)))


@_sub(r"(?<=[\w)])[⁰¹²³⁴⁵⁶⁷⁸⁹⁻]++")
def _superscript(m: re.Match[str], _: Options) -> str:
    return _power_words(int(m.group(0).translate(tables.SUPERSCRIPT_DIGITS)))


@_sub(r"[₀₁₂₃₄₅₆₇₈₉]++")
def _subscript(m: re.Match[str], _: Options) -> str:
    return " " + cardinal(int(m.group(0).translate(tables.SUBSCRIPT_DIGITS)))


@_sub(r"\b([A-Za-z])_([A-Za-z0-9]+)\b")
def _sub_variable(m: re.Match[str], _: Options) -> str:
    return f"{m.group(1)} sub {m.group(2)}"


@_sub(r"~\s?(?=\d)")
def _tilde(m: re.Match[str], _: Options) -> str:
    return "approximately "


@_sub(r"\b([A-Z])#|\b([A-Z])\+\+")
def _languages(m: re.Match[str], _: Options) -> str:
    return f"{m.group(1)} sharp" if m.group(1) else f"{m.group(2)} plus plus"


_SYMBOL_RE = re.compile(
    "|".join(
        re.escape(s) for s in sorted(tables.SYMBOLS, key=len, reverse=True)
    )
)
_GREEK_RE = re.compile("|".join(re.escape(s) for s in tables.GREEK))


def _symbols(text: str, _: Options) -> str:
    text = _SYMBOL_RE.sub(lambda m: f" {tables.SYMBOLS[m.group(0)]} ", text)
    return _GREEK_RE.sub(lambda m: f" {tables.GREEK[m.group(0)]} ", text)


# -- mixed tokens, formulas ----------------------------------------------------


def _formula_groups(token: str) -> list[str] | None:
    groups = re.findall(r"[A-Z][a-z]?\d*", token)
    if "".join(groups) != token or len(groups) < 2:
        return None
    if any(g.rstrip("0123456789") not in tables.ELEMENTS for g in groups):
        return None
    if not any(ch.isdigit() for ch in token) and len(groups) < 3:
        return None
    return groups


def _token_words(token: str) -> str:
    if token in tables.NAMED_FORMULAS:
        return tables.NAMED_FORMULAS[token]
    if token in tables.SAID_AS_WORDS:
        return token
    groups = _formula_groups(token)
    if groups:
        words = []
        for g in groups:
            letters = g.rstrip("0123456789")
            words.append(_spell(letters.upper()))
            if len(letters) < len(g):
                words.append(cardinal(int(g[len(letters) :])))
        return " ".join(words)
    parts = re.findall(r"[A-Z]+(?![a-z])|[A-Z][a-z]+|[a-z]+|\d+", token)
    words = []
    for part in parts:
        if part.isdigit():
            words.append(
                cardinal(int(part)) if len(part) <= 2 else digits(part)
            )
        elif part.isupper():
            words.append(_spell(part) if len(part) <= 3 else part)
        elif len(part) <= 2:
            words.append(_spell(part))
        else:
            words.append(part)
    return " ".join(words)


@_sub(
    r"\b(?=[A-Za-z]*\d|[a-z]*[A-Z])([A-Za-z]+\d*(?:-\d+)?(?:[A-Za-z]+\d*)*)\b"
)
def _tokens(m: re.Match[str], _: Options) -> str:
    token = m.group(1)
    if token in tables.KEEP or token in tables.SAID_AS_WORDS:
        return token
    if token in tables.NAMED_FORMULAS:
        return tables.NAMED_FORMULAS[token]
    if "-" in token:
        head, tail = token.split("-", 1)
        tail_words = cardinal(int(tail)) if tail.isdigit() else tail
        return f"{_tokens_word(head)} {tail_words}"
    return _tokens_word(token)


def _tokens_word(token: str) -> str:
    if token.isupper():
        return _spell(token) if 2 <= len(token) <= 3 else token
    if not any(c.isdigit() for c in token) and (
        token.islower() or token[1:].islower()
    ):
        return token  # an ordinary word
    return _token_words(token)


# -- plain numbers -----------------------------------------------------------


_YEAR_PREPOSITIONS = [
    "in",
    "since",
    "from",
    "until",
    "till",
    "by",
    "of",
    "before",
    "after",
    "during",
    "circa",
    "around",
    "between",
    "est",
]


@_sub(
    rf"\b((?:{'|'.join(_YEAR_PREPOSITIONS)}) )(1[1-9]\d\d|20\d\d)\b(?![\w.])"
    r"|\((1[1-9]\d\d|20\d\d)\)",
    re.IGNORECASE,
)
def _year_in_context(m: re.Match[str], _: Options) -> str:
    if m.group(3):
        return f"({year(int(m.group(3)))})"
    return f"{m.group(1)}{year(int(m.group(2)))}"


@_sub(rf"\b({_MONTH_WORDS})\.? (1[1-9]\d\d|20\d\d)\b(?![\w.])")
def _month_year(m: re.Match[str], _: Options) -> str:
    name = tables.MONTH_ABBREVIATIONS.get(m.group(1), m.group(1))
    return f"{name} {year(int(m.group(2)))}"


@_sub(r"\b(\d+)(st|nd|rd|th)\b")
def _ordinal(m: re.Match[str], _: Options) -> str:
    return ordinal(int(m.group(1)))


@_sub(r"\b(1[1-9]|20)(\d)0s\b")
def _decade(m: re.Match[str], _: Options) -> str:
    return f"{cardinal(int(m.group(1)))} {_decade_words(int(m.group(2)))}"


def _decade_words(tens: int) -> str:
    return cardinal(tens * 10).replace("y", "ies") if tens else "hundreds"


@_sub(r"\b(\d{1,2})/(\d{1,2})\b")
def _fraction(m: re.Match[str], _: Options) -> str:
    numerator, denominator = int(m.group(1)), int(m.group(2))
    if denominator == 2:
        unit = "half" if numerator == 1 else "halves"
    elif 3 <= denominator <= 10:
        unit = ordinal(denominator) + ("" if numerator == 1 else "s")
    else:
        return f"{cardinal(numerator)} over {cardinal(denominator)}"
    return f"{cardinal(numerator)} {unit}"


@_sub(rf"(?<![\w.])(-?)({_NUMBER})(?!\w|\.\d|,\d)")
def _number(m: re.Match[str], _: Options) -> str:
    return ("minus " if m.group(1) else "") + _num(m.group(2))


@_sub(r"\s?—\s?|\s–\s")
def _dashes(m: re.Match[str], _: Options) -> str:
    return ", "


def _tidy(text: str, _: Options) -> str:
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([,.;:)])", r"\1", text)
    text = re.sub(r"\(\s+", "(", text)
    return text.strip()


RULES: tuple[Rule, ...] = (
    _markdown_links,
    _break_links,
    _url,
    _email,
    _citations,
    _iso_date,
    _slash_date,
    _month_day,
    _day_month,
    _time,
    _ratio,
    _small_ratio,
    _am_pm,
    _version,
    _product_version,
    _short_version,
    _scientific,
    _currency,
    _numbered,
    _range,
    _ordinal,
    _decade,
    _units,
    _unit_per_unit,
    _always,
    _saint,
    _street,
    _drive,
    _doctor,
    _titles,
    _months,
    _days,
    _dotted,
    _caret,
    _superscript,
    _subscript,
    _sub_variable,
    _tilde,
    _languages,
    _symbols,
    _tokens,
    _year_in_context,
    _month_year,
    _fraction,
    _number,
    _dashes,
)


def normalize_words(
    text: str, *, british: bool = False, citations: str = "skip"
) -> str:
    """Rewrite ``text`` into the words a reader would say.

    Args:
        text: Cleaned prose (single-spaced).
        british: Read dates day-first ("the third of April").
        citations: ``"skip"`` drops citation markers, ``"read"`` says them.

    Raises:
        ValueError: if ``citations`` is not a known mode.
    """
    if citations not in CITATION_MODES:
        raise ValueError(f"citations must be one of {CITATION_MODES}")
    options = Options(british=british, citations=citations)
    # Pronunciation markup from the lexicon is passed through untouched.
    pieces: list[str] = []
    last = 0
    for markup in MARKUP.finditer(text):
        pieces.append(_rewrite(text[last : markup.start()], options))
        pieces.append(markup.group(0))
        last = markup.end()
    pieces.append(_rewrite(text[last:], options))
    return _tidy("".join(pieces), options)


def _rewrite(text: str, options: Options) -> str:
    for rule in RULES:
        text = rule(text, options)
    return text
