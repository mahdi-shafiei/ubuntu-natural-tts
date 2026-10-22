"""The semantic producer: W3C intents and phrasing on latex2mathml's MathML.

Each test converts LaTeX, runs ``annotate`` and checks the markup MathCAT
will read. Spoken results are pinned separately in ``golden_math.tsv``.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import pytest

from natural_tts.reading.intent import annotate
from natural_tts.reading.math import latex_to_mathml


def produce(latex: str) -> str:
    mathml = latex_to_mathml(latex)
    assert mathml is not None
    out = annotate(mathml)
    return re.sub(r"\s+", " ", out)


class TestProbability:
    @pytest.mark.parametrize(
        "latex", [r"P(A \mid B)", r"P(A|B)", r"\Pr(A \mid B)"]
    )
    def test_conditional_probability_gets_the_w3c_intent(self, latex):
        out = produce(latex)
        assert 'intent="conditional-probability($a,$b)"' in out
        assert 'arg="a">A<' in out and 'arg="b">B<' in out
        assert "&#x2223;" not in out and "∣" not in out
        assert re.search(r"<mo[^>]*>\|</mo>", out)

    def test_density_with_a_bar_is_conditional_too(self):
        out = produce(r"p(x \mid \theta)")
        assert 'intent="conditional-probability($a,$b)"' in out

    def test_lowercase_p_without_a_bar_is_left_alone(self):
        assert "intent" not in produce(r"p(1-p)")

    def test_simple_probability(self):
        out = produce(r"P(A \cap B) = P(A) P(B)")
        assert out.count('intent="probability($a)"') == 3

    def test_multi_token_sides_are_wrapped_as_arguments(self):
        out = produce(r"P(\theta \mid D, \alpha)")
        assert re.search(r'<mrow arg="b">.*?D.*?α.*?</mrow>', out)

    def test_set_builder_bar_is_not_touched(self):
        out = produce(r"\{x \mid x > 2\}")
        assert "intent" not in out and ("∣" in out or "&#x2223;" in out)


class TestExpectation:
    def test_expected_value(self):
        out = produce(r"E[X] + \mathbb{E}[Y]")
        assert out.count('intent="expected-value($a)"') == 2

    def test_conditional_expectation_says_given_inside(self):
        out = produce(r"E[X \mid Y]")
        assert 'intent="expected-value($a)"' in out
        assert "<mtext>given</mtext>" in out

    @pytest.mark.parametrize(
        ("latex", "intent"),
        [
            (r"\operatorname{Var}(X)", "variance($a)"),
            (r"\mathrm{Var}(X)", "variance($a)"),
            (r"\text{Var}(X)", "variance($a)"),
            (r"\mathrm{SD}(X)", "standard-deviation($a)"),
            (r"\operatorname{Cov}(X, Y)", "covariance($a)"),
            (r"\mathrm{Corr}(X, Y)", "correlation($a)"),
        ],
    )
    def test_moments(self, latex, intent):
        out = produce(latex)
        assert f'intent="{intent}"' in out

    def test_two_argument_moments_say_and_instead_of_comma(self):
        out = produce(r"\operatorname{Cov}(X, Y)")
        assert "<mtext>and</mtext>" in out and "<mo>,</mo>" not in out


class TestPostfixAndFences:
    @pytest.mark.parametrize(
        "latex", [r"A^T", r"A^\top", r"\mathbf{x}^{\mathsf{T}}"]
    )
    def test_transpose(self, latex):
        assert 'intent="transpose($a)"' in produce(latex)

    def test_inverse_only_for_matrices(self):
        assert 'intent="inverse($a)"' in produce(r"A^{-1}")
        assert 'intent="inverse($a)"' in produce(r"(X^T X)^{-1}")
        assert "inverse" not in produce(r"x^{-1}")

    def test_norm(self):
        assert 'intent="norm($a)"' in produce(r"\|x\|_2")


class TestRelations:
    def test_distributed_as(self):
        out = produce(r"X \sim \mathcal{N}(\mu, \sigma^2)")
        assert "<mtext>is distributed as</mtext>" in out and "~" not in out

    def test_approximately_is_not_touched(self):
        assert "distributed" not in produce(r"x \approx 3.14")

    def test_independence(self):
        out = produce(r"X \perp Y")
        assert "<mtext>is independent of</mtext>" in out

    def test_kl_divergence(self):
        out = produce(r"\mathrm{KL}(p \| q)")
        assert "<mtext>K L divergence from</mtext>" in out
        assert "<mtext>to</mtext>" in out and "‖" not in out


class TestOperators:
    @pytest.mark.parametrize(
        "latex", [r"\arg\max_\theta f", r"\operatorname*{arg\,max}_\theta f"]
    )
    def test_argmax(self, latex):
        out = produce(latex)
        assert (
            "<mtext>arg max over</mtext>" in out and "<mtext>of</mtext>" in out
        )
        assert "\\arg" not in out

    def test_argmin(self):
        assert "<mtext>arg min over</mtext>" in produce(r"\arg\min_x g")

    @pytest.mark.parametrize(
        ("latex", "phrase"),
        [
            (r"\nabla \cdot \vec{E}", "the divergence of"),
            (r"\nabla \times \vec{B}", "the curl of"),
            (r"\nabla^2 \phi", "the Laplacian of"),
        ],
    )
    def test_vector_calculus(self, latex, phrase):
        out = produce(latex)
        assert f"<mtext>{phrase}</mtext>" in out and "∇" not in out

    def test_lone_del(self):
        assert "<mi>del</mi>" in produce(r"\nabla f")


class TestUnits:
    def test_units_after_a_number_become_words_from_the_project_table(self):
        out = produce(r"5\,\mathrm{m/s}")
        assert "<mtext>meters per second</mtext>" in out

    def test_unit_with_negative_exponent(self):
        out = produce(r"3\,\mathrm{m}\,\mathrm{s}^{-1}")
        assert "<mtext>meters per second</mtext>" in out

    def test_letters_that_are_not_units_stay(self):
        assert "mtext" not in produce(r"5\,\mathrm{abc}")


class TestBraKet:
    def test_ket_and_bra(self):
        assert "<mtext>ket</mtext>" in produce(r"|\psi\rangle")
        assert "<mtext>ket</mtext>" in produce(r"\ket{\psi}")
        assert "<mtext>bra</mtext>" in produce(r"\langle \phi|")

    def test_two_sided_bracket_reads_its_contents_only(self):
        out = produce(r"\langle \phi | \psi \rangle")
        assert "bra" not in out and "ket" not in out and "|" not in out
        assert re.search(r"<mrow>.*?[φϕ].*?</mrow> ?<mrow>.*?ψ.*?</mrow>", out)

    def test_matrix_element(self):
        out = produce(r"\langle \phi | A | \psi \rangle")
        assert out.count("<mrow>") >= 3 and "|" not in out

    def test_expectation_value_in_angle_brackets(self):
        assert "<mtext>the expectation value of</mtext>" in produce(
            r"\langle A \rangle"
        )


class TestIdempotenceAndSafety:
    def test_plain_arithmetic_is_unchanged(self):
        mathml = latex_to_mathml(r"x^2 + y^2 = r^2")
        assert mathml is not None
        assert ET.canonicalize(annotate(mathml)) == ET.canonicalize(mathml)

    def test_annotating_twice_is_the_same_as_once(self):
        mathml = latex_to_mathml(r"P(A \mid B) E[X]")
        assert mathml is not None
        once = annotate(mathml)
        assert annotate(once) == once

    def test_namespace_is_preserved(self):
        assert produce(r"P(A)").startswith(
            '<math xmlns="http://www.w3.org/1998/Math/MathML"'
        )
