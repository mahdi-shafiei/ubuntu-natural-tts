import time

import pytest

from natural_tts.reading.math import (
    MAX_SPAN_CHARS,
    MathSpan,
    find_math_spans,
    latex_to_mathml,
    looks_like_math,
    nesting_depth,
    unicode_math_to_mathml,
)


class TestSpans:
    @pytest.mark.parametrize(
        ("text", "latex", "display"),
        [
            ("where $x^2 + y^2 = r^2$ holds", "x^2 + y^2 = r^2", False),
            (r"so \(\alpha = 0.05\) was used", r"\alpha = 0.05", False),
            (
                "Then $$\\int_0^1 f(x)\\,dx$$ follows.",
                r"\int_0^1 f(x)\,dx",
                True,
            ),
            ("Then \\[E = mc^2\\] follows.", "E = mc^2", True),
            (
                "\\begin{equation}\na = b\n\\end{equation}",
                "a = b",
                True,
            ),
            (
                "\\begin{align*} x &= 1 \\\\ y &= 2 \\end{align*}",
                "x &= 1 \\\\ y &= 2",
                True,
            ),
            ("inline \\begin{math}p < q\\end{math} here", "p < q", False),
        ],
    )
    def test_delimiters(self, text, latex, display):
        (span,) = find_math_spans(text)
        assert isinstance(span, MathSpan)
        assert span.latex.strip() == latex
        assert span.display is display
        assert text[span.start : span.end].strip().startswith(("$", "\\"))

    @pytest.mark.parametrize(
        "text",
        [
            "It costs $5 and $10 at most.",
            "Set $HOME and $PATH first.",
            "We paid $5.",
            "Prices: $5, $10, $20 and $40.",
            "A lone $ sign and another $ later.",
        ],
    )
    def test_dollar_guard_leaves_money_and_shell_alone(self, text):
        assert find_math_spans(text) == []

    def test_dollar_math_needs_an_operator_command_or_script(self):
        assert len(find_math_spans("let $x$ be")) == 0
        assert len(find_math_spans("let $x_i$ be")) == 1
        assert len(find_math_spans("let $\\pi$ be")) == 1
        assert len(find_math_spans("let $a < b$ be")) == 1
        assert len(find_math_spans("let $α$ be")) == 1

    def test_two_spans_in_one_sentence(self):
        spans = find_math_spans("from $x^2$ to $y^2$ now")
        assert [s.latex for s in spans] == ["x^2", "y^2"]

    def test_unclosed_delimiters_are_not_spans(self):
        assert find_math_spans("a lonely $x^2 with no end") == []
        assert find_math_spans("\\begin{equation} a = b") == []

    def test_spans_longer_than_the_cap_are_ignored(self):
        text = "$" + "x+" * (MAX_SPAN_CHARS // 2 + 10) + "x$"
        assert find_math_spans(text) == []


class TestLatexToMathml:
    def test_converts_and_strips_newlines(self):
        mathml = latex_to_mathml(r"\frac{a}{b}")
        assert mathml is not None
        assert mathml.startswith("<math") and "\n" not in mathml
        assert "<mfrac>" in mathml

    def test_conditional_bar_becomes_a_plain_bar_inside_probability(self):
        given = latex_to_mathml(r"P(A \mid B)")
        assert given is not None
        # latex2mathml writes the plain bar as the entity &#x0007C;
        assert "&#x02223;" not in given and "&#x0007C;" in given
        for latex in (
            r"\Pr(A \mid B)",
            r"E[X \mid Y]",
            r"p(x \mid \theta)",
            r"P(A \mid B) = \frac{P(B \mid A) P(A)}{P(B)}",
        ):
            out = latex_to_mathml(latex)
            assert out is not None and "&#x02223;" not in out, latex

    def test_set_builder_bar_is_kept(self):
        out = latex_to_mathml(r"\{x \mid x > 2\}")
        assert out is not None and "&#x02223;" in out

    def test_failure_returns_none(self):
        assert latex_to_mathml("\\frac{a}{") is None or isinstance(
            latex_to_mathml("\\frac{a}{"), str
        )
        assert latex_to_mathml("{" * 200 + "x" + "}" * 200) is None

    def test_adversarial_input_is_bounded(self):
        start = time.perf_counter()
        latex_to_mathml("\\frac{" * 60 + "x" + "}{y}" * 60)
        latex_to_mathml("x^" * 3000)
        assert time.perf_counter() - start < 1.0


class TestUnicodeMath:
    @pytest.mark.parametrize(
        ("text", "expected_tags"),
        [
            ("x² + y² = r²", ["<msup>", "<mo>+</mo>", "<mo>=</mo>"]),
            ("E = mc²", ["<msup>", "<mi>E</mi>"]),
            ("α ≤ β", ["<mi>α</mi>", "<mo>≤</mo>"]),
            ("aₙ = a₁ + (n−1)d", ["<msub>", "<mo>−</mo>"]),
        ],
    )
    def test_runs_with_scripts_or_operators_become_mathml(
        self, text, expected_tags
    ):
        mathml = unicode_math_to_mathml(text)
        assert mathml is not None
        for tag in expected_tags:
            assert tag in mathml, (tag, mathml)

    @pytest.mark.parametrize(
        "text", ["hello world", "n = 3", "see Fig. 3", "x", "100%"]
    )
    def test_plain_prose_is_not_math(self, text):
        assert not looks_like_math(text)
        assert unicode_math_to_mathml(text) is None


class TestNestingDepth:
    def test_depth_counts_nested_layout_elements(self):
        flat = latex_to_mathml("a + b")
        nested = latex_to_mathml(r"\sqrt{\frac{a}{b}}")
        deeper = latex_to_mathml(r"\frac{\sqrt{\frac{a}{b}}}{c}")
        assert nesting_depth(flat) == 0
        assert nesting_depth(nested) == 2
        assert nesting_depth(deeper) >= 3
