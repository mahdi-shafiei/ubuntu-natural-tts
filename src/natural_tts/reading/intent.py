"""The semantic producer: say what the notation means, not how it looks.

latex2mathml keeps every signal a reader needs (the bar's code point, the
letters of an operator name, the shape of a fence) but none of the
meaning. This pass walks the MathML tree and writes what MathCAT can
speak: W3C ``intent`` names where the core concept list has one
(conditional-probability, probability, expected-value, variance,
transpose, inverse, norm), and plain ``mtext`` phrases where MathCAT's
fallback would insert "comma" ("is distributed as", "arg max over",
"the divergence of", unit words). Spoken forms follow the research notes
(W3C intent list, Chang 1983, lecture transcripts); the two-sided Dirac
bracket is read as its contents only, because its meaning depends on the
context.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterator

from natural_tts.reading.normalize import unit_words

MATHML_NS = "http://www.w3.org/1998/Math/MathML"
_BAR = {"|", "∣"}
_PROBABILITY_HEADS = {"P", "Pr", "\U0001d443"}
_DENSITY_HEADS = {"p"}
_EXPECTATION_HEADS = {"E", "\U0001d53c"}
_MOMENTS = {
    "Var": "variance",
    "SD": "standard-deviation",
    "Cov": "covariance",
    "Corr": "correlation",
}
_OPEN = {"(": ")", "[": "]", "{": "}"}
_TRANSPOSE_MARKS = {"T", "⊤", "\U0001d5b3"}
_DOUBLE_BAR = "‖"
_TILDE = "~"
_PERP = "⟂"
_NABLA = "∇"
_LANGLE, _RANGLE = "⟨", "⟩"
_DOT = {"·", "⋅"}
_CROSS = "×"

ET.register_namespace("", MATHML_NS)


def annotate(mathml: str) -> str:
    """Return ``mathml`` with intents and phrases added; idempotent."""
    root = ET.fromstring(mathml)
    for element in _postorder(root):
        _rewrite_children(element)
    text = ET.tostring(root, encoding="unicode")
    return text.replace(
        f'xmlns="{MATHML_NS}" xmlns="{MATHML_NS}"', f'xmlns="{MATHML_NS}"'
    )


# -- tree helpers --------------------------------------------------------------


def _postorder(element: ET.Element) -> Iterator[ET.Element]:
    for child in list(element):
        yield from _postorder(child)
    yield element


def _local(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _text(element: ET.Element) -> str:
    return (element.text or "").strip()


def _is(element: ET.Element, tag: str, *texts: str) -> bool:
    return _local(element) == tag and (not texts or _text(element) in texts)


def _new(tag: str, text: str = "", **attrs: str) -> ET.Element:
    element = ET.Element(f"{{{MATHML_NS}}}{tag}", attrs)
    element.text = text
    return element


def _mtext(phrase: str) -> ET.Element:
    return _new("mtext", phrase)


def _closing(children: list[ET.Element], start: int) -> int | None:
    """Index of the fence closing the one at ``start``; None if unbalanced."""
    opener = _text(children[start])
    closer = _OPEN.get(opener)
    if closer is None:
        return None
    depth = 0
    for index in range(start, len(children)):
        child = children[index]
        if _is(child, "mo", opener):
            depth += 1
        elif _is(child, "mo", closer):
            depth -= 1
            if depth == 0:
                return index
    return None


def _top_level_bars(children: list[ET.Element]) -> list[int]:
    depth = 0
    bars = []
    for index, child in enumerate(children):
        if _is(child, "mo") and _text(child) in _OPEN:
            depth += 1
        elif _is(child, "mo") and _text(child) in _OPEN.values():
            depth -= 1
        elif depth == 0 and _is(child, "mo") and _text(child) in _BAR:
            bars.append(index)
    return bars


def _group(nodes: list[ET.Element], **attrs: str) -> ET.Element:
    """One node (with the attributes) or an mrow holding several."""
    if len(nodes) == 1:
        for key, value in attrs.items():
            nodes[0].set(key, value)
        return nodes[0]
    row = _new("mrow", **attrs)
    row.extend(nodes)
    return row


def _replace(
    parent: ET.Element, start: int, end: int, nodes: list[ET.Element]
) -> None:
    children = list(parent)
    for child in children[start:end]:
        parent.remove(child)
    for offset, node in enumerate(nodes):
        parent.insert(start + offset, node)


def _letters(children: list[ET.Element], start: int) -> tuple[str, int]:
    """Join a run of normal-variant single letters; returns (word, end)."""
    word = ""
    index = start
    while index < len(children) and (
        _is(children[index], "mi")
        and children[index].get("mathvariant") == "normal"
        and len(_text(children[index])) == 1
    ):
        word += _text(children[index])
        index += 1
    return word, index


def _head_name(
    children: list[ET.Element], index: int
) -> tuple[str, int] | None:
    """An operator name at ``index``: ``(name, end)`` for a token or run."""
    child = children[index]
    if _local(child) in {"mi", "mo", "mtext"} and _text(child):
        if _local(child) == "mi" and child.get("mathvariant") == "normal":
            word, end = _letters(children, index)
            return word, end
        return _text(child), index + 1
    if _local(child) == "mrow":
        inner = list(child)
        word, end = _letters(inner, 0)
        if word and end == len(inner):
            return word, index + 1
    return None


# -- the passes ----------------------------------------------------------------

Pass = Callable[[ET.Element, list[ET.Element]], bool]


def _rewrite_children(parent: ET.Element) -> None:
    changed = True
    while changed:
        changed = False
        for rule in _PASSES:
            if rule(parent, list(parent)):
                changed = True
                break


def _probability(parent: ET.Element, children: list[ET.Element]) -> bool:
    for index in range(len(children) - 1):
        name = _head_name(children, index)
        if name is None:
            continue
        head, after = name
        if head not in _PROBABILITY_HEADS | _DENSITY_HEADS:
            continue
        if after >= len(children) or not _is(children[after], "mo", "(", "["):
            continue
        close = _closing(children, after)
        if close is None or parent.get("intent"):
            continue
        inner = children[after + 1 : close]
        bars = _top_level_bars(inner)
        if len(bars) == 1:
            bar = inner[bars[0]]
            bar.text = "|"
            left = _group(inner[: bars[0]], arg="a")
            right = _group(inner[bars[0] + 1 :], arg="b")
            wrapped = _new("mrow", intent="conditional-probability($a,$b)")
            wrapped.extend(
                [
                    *children[index:after],
                    children[after],
                    left,
                    bar,
                    right,
                    children[close],
                ]
            )
        elif head in _DENSITY_HEADS or bars:
            continue
        else:
            wrapped = _new("mrow", intent="probability($a)")
            wrapped.extend(
                [
                    *children[index:after],
                    children[after],
                    _group(inner, arg="a"),
                    children[close],
                ]
            )
        _replace(parent, index, close + 1, [wrapped])
        return True
    return False


def _expectation(parent: ET.Element, children: list[ET.Element]) -> bool:
    for index in range(len(children) - 1):
        name = _head_name(children, index)
        if name is None:
            continue
        head, after = name
        if head not in _EXPECTATION_HEADS and head not in _MOMENTS:
            continue
        if after >= len(children) or not _is(children[after], "mo", "(", "["):
            continue
        close = _closing(children, after)
        if close is None or parent.get("intent"):
            continue
        inner = children[after + 1 : close]
        if head in _EXPECTATION_HEADS:
            intent = "expected-value($a)"
            for bar in _top_level_bars(inner):
                inner[bar] = _mtext("given")
        else:
            intent = f"{_MOMENTS[head]}($a)"
            inner = [_mtext("and") if _is(n, "mo", ",") else n for n in inner]
        wrapped = _new("mrow", intent=intent)
        wrapped.extend(
            [
                *children[index:after],
                children[after],
                _group(inner, arg="a"),
                children[close],
            ]
        )
        _replace(parent, index, close + 1, [wrapped])
        return True
    return False


def _exponent_kind(exponent: ET.Element) -> str | None:
    if _text(exponent) in _TRANSPOSE_MARKS or (
        _local(exponent) == "mrow"
        and len(exponent) == 1
        and _text(exponent[0]) in _TRANSPOSE_MARKS
    ):
        return "transpose($a)"
    if (
        _local(exponent) == "mrow"
        and len(exponent) == 2
        and _is(exponent[0], "mo", "−", "-")
        and _is(exponent[1], "mn", "1")
    ):
        return "inverse($a)"
    return None


def _opening(children: list[ET.Element], end: int) -> int | None:
    """Index of the fence opening the ")" at ``end``; None if unbalanced."""
    depth = 0
    for index in range(end, -1, -1):
        child = children[index]
        base = child[0] if _is(child, "msup") and len(child) else child
        if _is(base, "mo", ")"):
            depth += 1
        elif _is(base, "mo", "("):
            depth -= 1
            if depth == 0:
                return index
    return None


def _postfix(parent: ET.Element, children: list[ET.Element]) -> bool:
    for index, child in enumerate(children):
        if not _is(child, "msup") or child.get("intent") or len(child) != 2:
            continue
        base, exponent = list(child)
        kind = _exponent_kind(exponent)
        if kind is None:
            continue
        if _is(base, "mo", ")"):
            # (X^T X)^{-1}: the power hangs on the closing parenthesis.
            start = _opening(children, index)
            if start is None:
                continue
            group = _new("mrow", arg="a")
            group.extend([*children[start:index], base])
            wrapped = _new("mrow", intent=kind)
            wrapped.append(group)
            _replace(parent, start, index + 1, [wrapped])
            return True
        matrix_like = (_is(base, "mi") and _text(base)[:1].isupper()) or (
            _local(base) == "mrow"
        )
        if kind == "transpose($a)" or matrix_like:
            child.set("intent", kind)
            base.set("arg", "a")
            return True
    return False


def _is_double_bar(node: ET.Element) -> bool:
    if _is(node, "mo", _DOUBLE_BAR):
        return True
    return (
        _is(node, "msub") and len(node) == 2 and _is(node[0], "mo", _DOUBLE_BAR)
    )


def _norm(parent: ET.Element, children: list[ET.Element]) -> bool:
    if parent.get("intent"):
        return False
    bars = [i for i, c in enumerate(children) if _is_double_bar(c)]
    if len(bars) != 2:
        return False
    start, end = bars
    wrapped = _new("mrow", intent="norm($a)")
    wrapped.extend(
        [
            children[start],
            _group(children[start + 1 : end], arg="a"),
            children[end],
        ]
    )
    _replace(parent, start, end + 1, [wrapped])
    return True


def _relations(parent: ET.Element, children: list[ET.Element]) -> bool:
    for index, child in enumerate(children):
        if _is(child, "mi", _TILDE) and 0 < index < len(children) - 1:
            _replace(parent, index, index + 1, [_mtext("is distributed as")])
            return True
        if _is(child, "mi", _PERP) and 0 < index < len(children) - 1:
            _replace(parent, index, index + 1, [_mtext("is independent of")])
            return True
    for index in range(len(children)):
        name = _head_name(children, index)
        if name is None or name[0] != "KL":
            continue
        after = name[1]
        if after >= len(children) or not _is(children[after], "mo", "("):
            continue
        close = _closing(children, after)
        if close is None:
            continue
        inner = children[after + 1 : close]
        bars = [i for i, c in enumerate(inner) if _is(c, "mo", _DOUBLE_BAR)]
        if len(bars) != 1:
            continue
        nodes = [
            _mtext("K L divergence from"),
            *inner[: bars[0]],
            _mtext("to"),
            *inner[bars[0] + 1 :],
        ]
        _replace(parent, index, close + 1, nodes)
        return True
    return False


def _operators(parent: ET.Element, children: list[ET.Element]) -> bool:
    for index, child in enumerate(children):
        # \arg\max_θ: <mi>\arg</mi><msub><mo>max</mo>θ</msub>
        if (
            _is(child, "mi", "\\arg")
            and index + 1 < len(children)
            and _is(children[index + 1], "msub")
        ):
            sub = children[index + 1]
            if len(sub) == 2 and _text(sub[0]) in {"max", "min"}:
                phrase = f"arg {_text(sub[0])} over"
                _replace(
                    parent,
                    index,
                    index + 2,
                    [_mtext(phrase), sub[1], _mtext("of")],
                )
                return True
        # \operatorname*{arg\,max}_θ: <mo/><mo>*</mo><msub><mrow>a r g m a x
        # </mrow>θ</msub>
        if (
            _is(child, "msub")
            and len(child) == 2
            and _local(child[0]) == "mrow"
        ):
            word = "".join(_text(n) for n in child[0] if _local(n) == "mi")
            if word in {"argmax", "argmin"}:
                start = index
                while (
                    start > 0
                    and _is(children[start - 1], "mo")
                    and _text(children[start - 1]) in {"", "*"}
                ):
                    start -= 1
                phrase = f"arg {word[3:]} over"
                _replace(
                    parent,
                    start,
                    index + 1,
                    [_mtext(phrase), child[1], _mtext("of")],
                )
                return True
        if _is(child, "mo", _NABLA) and _local(parent) != "msup":
            nxt = children[index + 1] if index + 1 < len(children) else None
            if nxt is not None and _is(nxt, "mo") and _text(nxt) in _DOT:
                _replace(
                    parent, index, index + 2, [_mtext("the divergence of")]
                )
                return True
            if nxt is not None and _is(nxt, "mo", _CROSS):
                _replace(parent, index, index + 2, [_mtext("the curl of")])
                return True
            _replace(parent, index, index + 1, [_new("mi", "del")])
            return True
        if (
            _is(child, "msup")
            and len(child) == 2
            and _is(child[0], "mo", _NABLA)
            and _is(child[1], "mn", "2")
        ):
            _replace(parent, index, index + 1, [_mtext("the Laplacian of")])
            return True
    return False


def _unit_run(children: list[ET.Element], start: int) -> tuple[str | None, int]:
    """Unit words for the nodes from ``start``: ``(words, end)``."""
    index = start
    while index < len(children) and _is(children[index], "mspace"):
        index += 1
    parts: list[str] = []
    per = False
    while index < len(children):
        node = children[index]
        symbol, power = None, 1
        if _is(node, "mi") and node.get("mathvariant") == "normal":
            symbol, end = _letters(children, index)
        elif _is(node, "mi") and _text(node):
            symbol, end = _text(node), index + 1
        elif _is(node, "mrow") and all(
            _local(n) in {"mi", "mo", "msup"} for n in node
        ):
            words, inner_end = _unit_run(list(node), 0)
            if words is None or inner_end != len(node):
                break
            parts.append(words)
            index += 1
            continue
        elif _is(node, "msup") and len(node) == 2 and _is(node[0], "mi"):
            symbol, end = _text(node[0]), index + 1
            exponent = node[1]
            if (
                _local(exponent) == "mrow"
                and len(exponent) == 2
                and _is(exponent[0], "mo", "−")
            ):
                power = -int(_text(exponent[1]) or 1)
            elif _is(exponent, "mn"):
                power = int(_text(exponent))
        elif _is(node, "mo", "/"):
            per = True
            index += 1
            continue
        elif _is(node, "mtext") and _text(node):
            # \text{m/s}: the unit written as plain text.
            words_text = _unit_text(_text(node), per)
            if words_text is None:
                break
            parts.append(words_text)
            per = False
            index += 1
            continue
        elif _is(node, "mspace"):
            index += 1
            continue
        else:
            break
        if symbol is None:
            break
        words = unit_words(symbol, "1" if (per or power < 0) else "2")
        if words is None:
            break
        if power < 0 or per:
            parts.append("per " + words)
            per = False
        else:
            parts.append(
                words
                + (" squared" if power == 2 else " cubed" if power == 3 else "")
            )
        index = end
    if not parts:
        return None, start
    return " ".join(parts), index


def _unit_text(text: str, per: bool) -> str | None:
    """Words for a textual unit such as ``m/s`` or ``kg``; None if not one."""
    numerator, slash, denominator = text.partition("/")
    top = unit_words(numerator.strip(), "1" if per else "2")
    if top is None:
        return None
    words = ("per " if per else "") + top
    if slash:
        bottom = unit_words(denominator.strip(), "1")
        if bottom is None:
            return None
        words += " per " + bottom
    return words


def _units(parent: ET.Element, children: list[ET.Element]) -> bool:
    for index, child in enumerate(children[:-1]):
        if not _is(child, "mn"):
            continue
        words, end = _unit_run(children, index + 1)
        if words is None:
            continue
        _replace(parent, index + 1, end, [_mtext(words)])
        return True
    return False


def _braket(parent: ET.Element, children: list[ET.Element]) -> bool:
    for index, child in enumerate(children):
        if _is(child, "mo", _LANGLE) or _is(child, "mi", _LANGLE):
            end = next(
                (
                    i
                    for i in range(index + 1, len(children))
                    if _text(children[i]) == _RANGLE
                ),
                None,
            )
            if end is not None:
                inner = children[index + 1 : end]
                bars = [
                    i
                    for i, c in enumerate(inner)
                    if _is(c, "mo") and _text(c) in _BAR
                ]
                if not bars:
                    nodes = [_mtext("the expectation value of"), _group(inner)]
                else:
                    pieces = []
                    last = 0
                    for bar in [*bars, len(inner)]:
                        pieces.append(
                            _group(inner[last:bar])
                            if len(inner[last:bar]) != 1
                            else _new_row(inner[last:bar])
                        )
                        last = bar + 1
                    nodes = pieces
                _replace(parent, index, end + 1, nodes)
                return True
            bar_at = next(
                (
                    i
                    for i in range(index + 1, len(children))
                    if _is(children[i], "mo") and _text(children[i]) in _BAR
                ),
                None,
            )
            if bar_at is not None:
                _replace(
                    parent,
                    index,
                    bar_at + 1,
                    [_mtext("bra"), _group(children[index + 1 : bar_at])],
                )
                return True
        if (_is(child, "mo") and _text(child) in _BAR) and index + 1 < len(
            children
        ):
            end = next(
                (
                    i
                    for i in range(index + 1, len(children))
                    if _text(children[i]) == _RANGLE
                ),
                None,
            )
            if end is not None and not any(
                _is(c, "mo") and _text(c) in _BAR
                for c in children[index + 1 : end]
            ):
                _replace(
                    parent,
                    index,
                    end + 1,
                    [_mtext("ket"), _group(children[index + 1 : end])],
                )
                return True
    return False


def _new_row(nodes: list[ET.Element]) -> ET.Element:
    row = _new("mrow")
    row.extend(nodes)
    return row


_PASSES: tuple[Pass, ...] = (
    _probability,
    _expectation,
    _postfix,
    _norm,
    _relations,
    _operators,
    _units,
    _braket,
)
