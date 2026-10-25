"""Read a code block aloud, line by line, at a chosen verbosity level.

Levels follow NVDA's symbol sets: 1 speaks the operators and the dot, drops
brackets, quotes and separators; 2 adds brackets, quotes, separators and
indentation changes; 3 speaks every symbol. The comma is spoken from level
2 on (NVDA says it only at "all") because in code it separates arguments
the way a bracket encloses them. Identifiers are split on case changes,
underscores, hyphens and digits; numbers go through the number speller;
string and comment contents are read as words. Pygments, when it knows
the language, tells strings, comments and numbers apart; everything else
goes through the small tokeniser here, so an unknown language still reads.
"""

from __future__ import annotations

import functools
import re
from collections.abc import Iterable, Iterator
from typing import Any

from natural_tts.config import CODE_LEVELS
from natural_tts.reading.numbers import cardinal, decimal, digits

# Operators and symbols, longest first, with the level at which each is spoken.
SYMBOLS: tuple[tuple[str, str, int], ...] = (
    ("===", "triple equals", 1),
    ("!==", "not triple equals", 1),
    ("==", "equals equals", 1),
    ("!=", "not equals", 1),
    # No maintained reader names two-character operators (NVDA, Speech
    # Dispatcher and eSpeak speak them character by character); these rows
    # are the project's, worded after NVDA's names for the Unicode glyphs
    # ("greater-than or equal to", "not equal to", "right arrow").
    ("<=", "less than or equal to", 1),
    (">=", "greater than or equal to", 1),
    ("->", "arrow", 1),
    ("=>", "fat arrow", 1),
    ("+=", "plus equals", 1),
    ("-=", "minus equals", 1),
    ("*=", "star equals", 1),
    ("/=", "slash equals", 1),
    ("&&", "and and", 1),
    ("||", "or or", 1),
    ("**", "star star", 1),
    ("//", "slash slash", 1),
    ("::", "colon colon", 2),
    ("=", "equals", 1),
    ("+", "plus", 1),
    ("-", "minus", 1),
    ("*", "star", 1),
    ("/", "slash", 1),
    ("%", "percent", 1),
    ("<", "less than", 1),
    (">", "greater than", 1),
    (".", "dot", 1),
    ("@", "at", 1),
    ("#", "hash", 1),
    ("&", "and", 1),
    ("(", "left paren", 2),
    (")", "right paren", 2),
    ("[", "left bracket", 2),
    ("]", "right bracket", 2),
    ("{", "left brace", 2),
    ("}", "right brace", 2),
    ('"', "quote", 2),
    ("'", "quote", 2),
    ("`", "backtick", 2),
    (":", "colon", 2),
    (";", "semicolon", 2),
    (",", "comma", 2),
    ("|", "bar", 2),
    ("\\", "backslash", 2),
    ("^", "caret", 2),
    ("~", "tilde", 2),
    ("_", "underscore", 2),
    ("!", "bang", 3),
    ("?", "question mark", 3),
    ("$", "dollar", 3),
)
_SYMBOL_WORDS = {symbol: (words, level) for symbol, words, level in SYMBOLS}
_SYMBOL_RE = "|".join(re.escape(s) for s, _, _ in SYMBOLS)
# A hyphen opening a word is "dash" and a hyphen before a digit "minus",
# NVDA's two symbols.dic rows ("-" dash; "negative number" minus), which
# Speech Dispatcher imports verbatim, so "-A" and "--all" are "dash A" and
# "dash dash all" in every language. Between operands the table below says
# "minus" ("x - y", "x-y"); no maintained reader does that, it is this
# project's addition for code.
_FLAG = re.compile(r"(?<!\S)(-+)(?=[A-Za-z_])")
_TOKEN = re.compile(
    r"(?P<ws>\s+)"
    r"|(?P<string>\"[^\"\n]*\"|'[^'\n]*')"
    r"|(?P<comment>#[^\n]*|//[^\n]*)"
    r"|(?P<number>0[xX][0-9A-Fa-f_]+|\d[\d_]*(?:\.\d+)?(?:[eE][+-]?\d+)?)"
    r"|(?P<word>[A-Za-z_][A-Za-z0-9_]*)"
    rf"|(?P<symbol>{_SYMBOL_RE})"
    r"|(?P<other>.)"
)
# NVDA's camel-case rules: split before a capital that follows a lowercase
# letter, between an acronym and the Capitalised word after it (XMLHttp ->
# XML Http), and between letters and digits.
_IDENTIFIER_PARTS = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")
# Tokens kept whole although they mix letters and digits.
KEEP_WHOLE = frozenset(
    [
        "utf8",
        "utf16",
        "mp3",
        "mp4",
        "2d",
        "3d",
        "ipv4",
        "ipv6",
        "sha1",
        "sha256",
        "sha512",
        "md5",
        "int8",
        "int16",
        "int32",
        "int64",
        "uint8",
        "uint16",
        "uint32",
        "uint64",
        "float32",
        "float64",
        "x86",
        "x64",
        "h264",
        "base64",
        "oauth2",
        "http2",
        "i18n",
        "l10n",
        "XPath",
    ]
)
# Short abbreviations whose expansion is unambiguous in code.
EXPANSIONS: dict[str, str] = {
    "str": "string",
    "len": "length",
    "cfg": "config",
    "idx": "index",
    "num": "number",
    "ptr": "pointer",
    "msg": "message",
    "buf": "buffer",
    "cnt": "count",
    "src": "source",
    "dst": "destination",
    "tmp": "temp",
    "err": "error",
    "ctx": "context",
    "pkg": "package",
    "env": "environment",
    "args": "arguments",
    "kwargs": "keyword arguments",
}
_COMMENT_MARKERS = re.compile(r"^(?:#+|//+|/\*+|\*+/|--+|;+|<!--|-->|%+)\s?")
_QUOTES = "\"'`"
_DIFF_LINE = (
    ("--- ", "old file"),
    ("+++ ", "new file"),
    ("@@", "hunk"),
    ("+", "added"),
    ("-", "removed"),
)


def split_identifier(name: str) -> list[str]:
    """Split an identifier into spoken parts; underscores and hyphens vanish.

    Case changes, delimiters and digits are the only cues (a dictionary adds
    little on conventional names and fails on the rest, per the research
    notes); a keep-list protects tokens such as ``utf8`` and a short table
    expands unambiguous abbreviations such as ``cfg``.
    """
    parts: list[str] = []
    for piece in re.split(r"[_\-]+", name):
        if not piece:
            continue
        if piece in KEEP_WHOLE or piece.lower() in KEEP_WHOLE:
            parts.append(piece)
            continue
        for part in _parts_pattern().findall(piece):
            parts.append(EXPANSIONS.get(part.lower(), part))
    return parts or [name]


@functools.lru_cache(maxsize=1)
def _parts_pattern() -> re.Pattern[str]:
    kept = "|".join(
        re.escape(token) for token in sorted(KEEP_WHOLE, key=len, reverse=True)
    )
    return re.compile(rf"(?i:{kept})|" + _IDENTIFIER_PARTS.pattern)


def read_code(text: str, *, language: str | None, level: int) -> list[str]:
    """Return one spoken line per non-empty code line.

    Raises:
        ValueError: if ``level`` is not 1, 2 or 3.
    """
    if level not in CODE_LEVELS:
        raise ValueError(f"level must be one of {CODE_LEVELS}")
    if language == "diff":
        return [line for line in _read_diff(text, level) if line]
    spoken: list[str] = []
    previous_indent: int | None = None
    for raw, words in _lines(text, language, level):
        if not raw.strip():
            continue
        expanded = raw.expandtabs(4)
        indent = len(expanded) - len(expanded.lstrip(" "))
        prefix: list[str] = []
        if level >= 2 and previous_indent is not None:
            if indent > previous_indent:
                prefix = ["indent"]
            elif indent < previous_indent:
                prefix = ["dedent"]
        previous_indent = indent
        line = " ".join(prefix + words)
        if line:
            spoken.append(line)
    return spoken


# -- lines and tokens ----------------------------------------------------------


def _lines(
    text: str, language: str | None, level: int
) -> Iterator[tuple[str, list[str]]]:
    lexer = _lexer(language) if language else None
    for raw in text.split("\n"):
        raw = _FLAG.sub(lambda m: " dash" * len(m.group(1)) + " ", raw)
        yield raw, _speak_line(raw, lexer, level)


def _speak_line(raw: str, lexer: Any, level: int) -> list[str]:
    words: list[str] = []
    if lexer is None:
        for kind, value in _tokenize(raw):
            words.extend(_speak(kind, value, level))
        return words
    for token_type, value in _merge_operators(
        _merge_strings(lexer.get_tokens(raw))
    ):
        name = str(token_type)
        if "Comment" in name:
            words.extend(_speak("comment", value, level))
        elif "String" in name or _is_quoted(value):
            words.extend(_speak("string", value, level))
        elif "Number" in name:
            words.extend(_speak("number", value, level))
        else:
            for kind, piece in _tokenize(value):
                words.extend(_speak(kind, piece, level))
    return words


def _merge_strings(tokens: Any) -> Iterator[tuple[Any, str]]:
    # Pygments splits a string literal into its quotes and its content; one
    # token per literal keeps the quotes spoken once on each side.
    pending: list[str] = []
    pending_type: Any = None
    for token_type, value in tokens:
        if value == "\n":
            continue
        if "String" in str(token_type):
            pending.append(value)
            pending_type = token_type
            continue
        if pending:
            yield pending_type, "".join(pending)
            pending = []
        yield token_type, value
    if pending:
        yield pending_type, "".join(pending)


def _merge_operators(
    tokens: Iterable[tuple[Any, str]],
) -> Iterator[tuple[Any, str]]:
    # Pygments' Python lexer yields ">=" as ">" then "="; joined back, the
    # symbol table's longest-first match reads it as one operator.
    pending: list[str] = []
    pending_type: Any = None
    for token_type, value in tokens:
        if "Operator" in str(token_type) and not value.isspace():
            pending.append(value)
            pending_type = token_type
            continue
        if pending:
            yield pending_type, "".join(pending)
            pending = []
        yield token_type, value
    if pending:
        yield pending_type, "".join(pending)


def _is_quoted(value: str) -> bool:
    return len(value) >= 2 and value[0] in _QUOTES and value[-1] == value[0]


def _tokenize(text: str) -> Iterator[tuple[str, str]]:
    for match in _TOKEN.finditer(text):
        kind = match.lastgroup or "other"
        if kind != "ws":
            yield kind, match.group(0)


def _speak(kind: str, value: str, level: int) -> list[str]:
    if kind == "word":
        return split_identifier(value)
    if kind == "number":
        return _number_words(value)
    if kind == "symbol":
        words, needed = _SYMBOL_WORDS[value]
        return [words] if level >= needed else []
    if kind == "comment":
        return ["comment", *_COMMENT_MARKERS.sub("", value).split()]
    if kind == "string":
        return _string_words(value, level)
    return [value] if level >= 3 else []


def _string_words(literal: str, level: int) -> list[str]:
    content = literal[1:-1] if _is_quoted(literal) else literal
    if level == 1:
        return content.split()
    inner: list[str] = []
    for kind, piece in _tokenize(content):
        inner.extend(_speak(kind, piece, level))
    return ["quote", *inner, "quote"]


def _number_words(value: str) -> list[str]:
    value = value.replace("_", "")
    if value[:2].lower() == "0x":
        spelled = (digits(c) if c.isdigit() else c.upper() for c in value[2:])
        return ["hex", *spelled]
    if "e" in value.lower():
        mantissa, _, exponent = value.lower().partition("e")
        sign = "minus " if exponent.startswith("-") else ""
        return [
            decimal(mantissa),
            "e",
            (sign + cardinal(int(exponent.lstrip("+-")))),
        ]
    return [decimal(value)]


@functools.lru_cache(maxsize=32)
def _lexer(language: str) -> Any:
    from pygments.lexers import get_lexer_by_name
    from pygments.util import ClassNotFound

    try:
        return get_lexer_by_name(language)
    except ClassNotFound:
        return None


# -- diffs ------------------------------------------------------------------


def _read_diff(text: str, level: int) -> Iterator[str]:
    for raw in text.split("\n"):
        if not raw.strip():
            continue
        for marker, words in _DIFF_LINE:
            if raw.startswith(marker):
                rest = raw[len(marker) :].strip()
                if marker in {"--- ", "+++ "}:
                    name = rest.split("\t")[0]
                    name = (
                        name.split("/", 1)[1]
                        if name[:2] in {"a/", "b/"}
                        else name
                    )
                    yield f"{words} {name}"
                elif marker == "@@":
                    yield words
                else:
                    yield " ".join([words, *_speak_line(rest, None, level)])
                break
        else:
            yield " ".join(_speak_line(raw.strip(), None, level))
