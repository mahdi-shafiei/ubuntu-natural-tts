"""Mathematics: find formulas in text and turn them into MathML.

Pure conversion, no engine and no helper process here. LaTeX spans are
found by their delimiters (with a guard so prices and shell variables are
not formulas), converted with ``latex2mathml`` and post-processed; runs of
Unicode math copied from PDFs become MathML through a small linear
converter. ``nesting_depth`` decides when MathCAT should speak verbosely.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

MAX_SPAN_CHARS = 10_000
MAX_BRACE_DEPTH = 50
_ENVIRONMENTS = (
    "equation",
    "align",
    "gather",
    "multline",
    "eqnarray",
    "displaymath",
    "math",
)
_DISPLAY_ENVIRONMENTS = frozenset(_ENVIRONMENTS) - {"math"}
# Delimiters are paired in one left-to-right pass (``find_math_spans``);
# a closer found absent is not searched for again, so a window full of
# unclosed openers costs linear time.
_OPENERS = re.compile(
    r"\$\$|\\\[|\\\(|\\begin\{(?P<env>"
    + "|".join(_ENVIRONMENTS)
    + r")(?P<star>\*?)\}|(?<![\\$\w])\$(?!\$)"
)
_MATH_EVIDENCE = re.compile(r"\\[A-Za-z]+|[\^_=<>≤≥≠±×÷∑∫√∞→]|[α-ωΑ-Ω]")
_GREEK = re.compile(r"[α-ωΑ-Ω]")
_SUPERSCRIPTS = "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱ"
_SUBSCRIPTS = "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₒₓₔₕₖₗₘₙₚₛₜ"
_SCRIPT_TO_BASE = str.maketrans(
    _SUPERSCRIPTS + _SUBSCRIPTS,
    "0123456789+-=()ni" + "0123456789+-=()aeoxəhklmnpst",
)
_OPERATORS = "+−-=<>≤≥≠±×÷·⋅∑∏∫√∞→←↔∈∉⊂⊆∪∩∧∨¬∀∃∂∇/()[]{}|,"
_TOKEN = re.compile(
    rf"(?P<num>\d+(?:[.,]\d+)?)"
    rf"|(?P<sup>[{_SUPERSCRIPTS}]+)"
    rf"|(?P<sub>[{_SUBSCRIPTS}]+)"
    rf"|(?P<id>[A-Za-zα-ωΑ-Ω](?![A-Za-z]))"
    rf"|(?P<word>[A-Za-z]{{2,}})"
    rf"|(?P<op>[{re.escape(_OPERATORS)}])"
    r"|(?P<ws>\s+)"
    r"|(?P<other>.)"
)
_LAYOUT_TAGS = re.compile(
    r"<(/?)(mfrac|msqrt|mroot|msub|msup|msubsup|munder|mover|munderover|mtable)\b"
)


@dataclass(frozen=True)
class MathSpan:
    """A formula found in text: where it is, its LaTeX, display or inline."""

    start: int
    end: int
    latex: str
    display: bool


def _is_math_dollars(body: str) -> bool:
    # "$5 and $10" is money; a formula shows a command, an operator, a
    # script or a Greek letter.
    return bool(_MATH_EVIDENCE.search(body))


def find_math_spans(text: str) -> list[MathSpan]:
    """Find delimited LaTeX spans; prices and shell variables are skipped.

    One left-to-right pass. The next position of every closer and opener
    is cached, so a window full of unclosed openers costs linear time. A
    span whose body holds another opener of its own kind is not a span:
    the closer belongs to the inner opener.
    """
    spans: list[MathSpan] = []
    cache: dict[str, int] = {}
    position = 0
    while (match := _OPENERS.search(text, position)) is not None:
        opener = match.group(0)
        position = match.end()
        if opener.startswith("\\begin"):
            environment = match.group("env") + match.group("star")
            literal = f"\\begin{{{environment}}}"
            closer = f"\\end{{{environment}}}"
            display = match.group("env") in _DISPLAY_ENVIRONMENTS
        else:
            literal = opener
            closer, display = _CLOSERS[opener]
        if opener == "$":
            found = _dollar_closer(text, cache, position)
        else:
            found = _next(text, cache, closer, position)
            inner = _next(text, cache, literal, position)
            if 0 <= inner < found:
                continue
        if found < 0:
            continue
        body = text[position:found]
        if not body or len(body) > MAX_SPAN_CHARS:
            continue
        if opener == "$" and ("$" in body or not _is_math_dollars(body)):
            continue
        spans.append(
            MathSpan(match.start(), found + len(closer), body, display)
        )
        position = found + len(closer)
    return spans


_CLOSERS = {
    "$$": ("$$", True),
    "\\[": ("\\]", True),
    "\\(": ("\\)", False),
    "$": ("$", False),
}


def _next(text: str, cache: dict[str, int], needle: str, start: int) -> int:
    """``text.find(needle, start)``, remembered while ``start`` advances."""
    hit = cache.get(needle)
    if hit is None or 0 <= hit < start:
        hit = text.find(needle, start)
        cache[needle] = hit
    return hit


def _dollar_closer(text: str, cache: dict[str, int], start: int) -> int:
    """The next ``$`` that can close a span, on the same line, else -1."""
    hit = cache.get("$close")
    if hit is None or 0 <= hit < start:
        hit = _closing_dollar(text, start)
        cache["$close"] = hit
    if hit >= 0 and text.find("\n", start, hit) >= 0:
        return -1
    return hit


def _closing_dollar(text: str, start: int) -> int:
    found = text.find("$", start)
    while found >= 0:
        after = text[found + 1 : found + 2]
        if after != "$" and not (after.isalnum() or after == "_"):
            return found
        found = text.find("$", found + 1)
    return -1


def latex_to_mathml(latex: str) -> str | None:
    r"""Convert LaTeX to one line of MathML, or None when it cannot be done.

    Meaning (conditional bars, expectations, units) is added afterwards by
    ``intent.annotate``; this function only converts.
    """
    if len(latex) > MAX_SPAN_CHARS or _brace_depth(latex) > MAX_BRACE_DEPTH:
        return None
    from latex2mathml.converter import convert

    try:
        mathml = convert(latex)
    except Exception:
        return None
    # MathCAT spells "<mi>ln</mi>" letter by letter; name it.
    mathml = mathml.replace("<mi>ln</mi>", _NATURAL_LOG)
    return " ".join(mathml.split())


_NATURAL_LOG = "<mi>natural log</mi><mo>&#x2061;</mo>"


def _brace_depth(latex: str) -> int:
    depth = worst = 0
    for char in latex:
        if char == "{":
            depth += 1
            worst = max(worst, depth)
        elif char == "}":
            depth -= 1
    return worst


def looks_like_math(text: str) -> bool:
    """Whether a plain-text run reads as a formula rather than prose.

    Needs a script, or two or more operators, among at most a few words;
    ``n = 3`` and ``100%`` stay prose for the word rules.
    """
    scripts = sum(1 for c in text if c in _SUPERSCRIPTS or c in _SUBSCRIPTS)
    operators = sum(1 for c in text if c in _OPERATORS and c not in "(),")
    words = len(re.findall(r"[A-Za-z]{2,}", text))
    greek = len(_GREEK.findall(text))
    if words > 3:
        return False
    return scripts > 0 or operators >= 2 or (greek > 0 and operators >= 1)


def unicode_math_to_mathml(text: str) -> str | None:
    """Turn a Unicode formula run (``x² + y² = r²``) into MathML."""
    if not looks_like_math(text):
        return None
    parts: list[str] = []
    for match in _TOKEN.finditer(text):
        kind, value = match.lastgroup, match.group(0)
        if kind == "ws":
            continue
        if kind == "num":
            element = f"<mn>{value}</mn>"
        elif kind in {"id", "word"}:
            element = f"<mi>{value}</mi>"
        elif kind == "op":
            element = f"<mo>{_escape(value)}</mo>"
        elif kind == "sup":
            base = parts.pop() if parts else "<mrow></mrow>"
            element = f"<msup>{base}{_script_row(value)}</msup>"
        elif kind == "sub":
            base = parts.pop() if parts else "<mrow></mrow>"
            element = f"<msub>{base}{_script_row(value)}</msub>"
        else:
            element = f"<mi>{_escape(value)}</mi>"
        parts.append(element)
    if not parts:
        return None
    return "<math><mrow>" + "".join(parts) + "</mrow></math>"


def _script_row(script: str) -> str:
    folded = script.translate(_SCRIPT_TO_BASE)
    inner = "".join(
        f"<mn>{c}</mn>"
        if c.isdigit()
        else f"<mo>{_escape(c)}</mo>"
        if not c.isalpha()
        else f"<mi>{c}</mi>"
        for c in folded
    )
    return f"<mrow>{inner}</mrow>"


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def nesting_depth(mathml: str | None) -> int:
    """How deeply layout elements (fractions, roots, scripts) nest."""
    depth = worst = 0
    for closing, _tag in _LAYOUT_TAGS.findall(mathml or ""):
        if closing:
            depth -= 1
        else:
            depth += 1
            worst = max(worst, depth)
    return worst


def fold_scripts(text: str) -> str:
    """Fold Unicode super- and subscripts to plain characters (for logging)."""
    return unicodedata.normalize("NFC", text.translate(_SCRIPT_TO_BASE))
