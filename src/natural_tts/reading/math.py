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
# Delimited spans. Each alternative is bounded and cannot overlap itself.
_SPAN = re.compile(
    r"\$\$(?P<dd>[^$]{1,10000}?)\$\$"
    r"|\\\[(?P<br>.{1,10000}?)\\\]"
    r"|\\\((?P<pa>.{1,10000}?)\\\)"
    r"|\\begin\{(?P<env>" + "|".join(_ENVIRONMENTS) + r")(?P<star>\*?)\}"
    r"(?P<body>.{1,10000}?)\\end\{(?P=env)(?P=star)\}"
    r"|(?<![\\$\w])\$(?P<d>[^$\n]{1,10000}?)\$(?![\w$])",
    re.DOTALL,
)
_MATH_EVIDENCE = re.compile(r"\\[A-Za-z]+|[\^_=<>≤≥≠±×÷∑∫√∞→]|[α-ωΑ-Ω]")
_GREEK = re.compile(r"[α-ωΑ-Ω]")
# "\mid" inside P( ), Pr( ), E[ ], Var( ) or p( ): a conditional bar.
_CONDITIONAL = re.compile(
    r"((?<![A-Za-z])\\?(?:Pr|P|E|Var|p)\s*[(\[][^()\[\]]*?)\\mid(?![A-Za-z])"
)
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
    """Find delimited LaTeX spans; prices and shell variables are skipped."""
    spans: list[MathSpan] = []
    for match in _SPAN.finditer(text):
        kind = match.lastgroup
        if kind == "d":
            body, display = match.group("d"), False
            if not _is_math_dollars(body):
                continue
        elif kind == "dd":
            body, display = match.group("dd"), True
        elif kind == "br":
            body, display = match.group("br"), True
        elif kind == "pa":
            body, display = match.group("pa"), False
        else:
            body = match.group("body")
            display = match.group("env") in _DISPLAY_ENVIRONMENTS
        if len(body) > MAX_SPAN_CHARS:
            continue
        spans.append(MathSpan(match.start(), match.end(), body, display))
    return spans


def latex_to_mathml(latex: str) -> str | None:
    r"""Convert LaTeX to one line of MathML, or None when it cannot be done.

    A conditional bar (``P(A \mid B)``, ``E[X \mid Y]``, also inside a
    longer equation) becomes a plain bar before conversion so MathCAT says
    "given" rather than "divides"; set-builder bars are left alone.
    """
    if len(latex) > MAX_SPAN_CHARS or _brace_depth(latex) > MAX_BRACE_DEPTH:
        return None
    while True:
        rewritten = _CONDITIONAL.sub(r"\1|", latex)
        if rewritten == latex:
            break
        latex = rewritten
    from latex2mathml.converter import convert

    try:
        mathml = convert(latex)
    except Exception:
        return None
    return " ".join(mathml.split())


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
