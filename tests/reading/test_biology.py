"""Variants, karyotypes, bands, genotypes, enzymes: the standards' segments.

Sources per the research notes: HGVS recommendations (prefix, position,
reference, alternate, del/dup/ins/fs/Ter), ISCN 2024 as modelled by
iscn-authenticator, HGNC/MGI symbol shapes, JAX genotype notation, and the
practitioners' spoken forms (GEP glossary, Edvotek: "eco R one").
"""

import pytest

from natural_tts.reading.biology import (
    band_words,
    enzyme_words,
    genotype_words,
    hgvs_words,
    karyotype_words,
)


class TestHgvs:
    @pytest.mark.parametrize(
        ("variant", "spoken"),
        [
            ("c.123A>G", "c dot one twenty-three, A to G"),
            (
                "g.33038255C>A",
                "g dot three three zero three eight two five five, C to A",
            ),
            ("c.76_78del", "c dot seventy-six to seventy-eight deletion"),
            ("c.76dup", "c dot seventy-six duplication"),
            ("c.76_77insT", "c dot seventy-six to seventy-seven insertion T"),
            ("p.Arg175His", "p dot arg one seventy-five his"),
            ("p.R175H", "p dot R one seventy-five H"),
            ("p.Trp24Ter", "p dot trp twenty-four stop"),
            ("p.Trp24*", "p dot trp twenty-four stop"),
            ("p.Arg97fs", "p dot arg ninety-seven frameshift"),
            (
                "p.Arg97ProfsTer23",
                "p dot arg ninety-seven pro frameshift stop twenty-three",
            ),
        ],
    )
    def test_variants(self, variant, spoken):
        assert hgvs_words(variant) == spoken

    def test_not_a_variant(self):
        assert hgvs_words("c.f. the appendix") is None
        assert hgvs_words("p.12") is None


class TestKaryotype:
    def test_translocation(self):
        assert karyotype_words("46,XY,t(9;22)(q34;q11)") == (
            "forty-six, X Y, translocation between nine and twenty-two, "
            "q thirty-four, q eleven"
        )

    def test_trisomy_and_deletion(self):
        assert (
            karyotype_words("47,XX,+21")
            == "forty-seven, X X, trisomy twenty-one"
        )
        assert karyotype_words("46,XX,del(17)(p13)") == (
            "forty-six, X X, deletion on seventeen p thirteen"
        )

    def test_plain_count_is_left(self):
        assert karyotype_words("46,XY") == "forty-six, X Y"
        assert karyotype_words("46 people") is None


class TestBandsGenotypesEnzymes:
    def test_chromosome_band(self):
        assert band_words("17p13.1") == "seventeen p thirteen point one"
        assert band_words("Xq28") == "X q twenty-eight"
        assert band_words("p13") is None

    def test_genotypes(self):
        assert genotype_words("Tp53−/−") == "Tp53 knockout"
        assert genotype_words("Tp53-/-") == "Tp53 knockout"
        assert genotype_words("Cftr+/−") == "Cftr heterozygous"
        assert genotype_words("Cftr+/+") == "Cftr wild type"
        assert genotype_words("Cftrfl/fl") is None

    def test_restriction_enzymes(self):
        assert enzyme_words("EcoRI") == "Eco R one"
        assert enzyme_words("HindIII") == "Hin D three"
        assert enzyme_words("BamHI") == "Bam H one"
        assert enzyme_words("NotI") == "Not one"
        assert enzyme_words("XhoI") == "Xho one"
        assert enzyme_words("Notice") is None and enzyme_words("III") is None
