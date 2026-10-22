from natural_tts.reading.lexicon import Entry, Lexicon
from natural_tts.reading.normalize import normalize_words
from natural_tts.reading.protected import protect, split_protected, unprotect


class TestProtectedSpans:
    def test_round_trip(self):
        text = "Run " + protect("git add minus A") + " at 37 °C."
        parts = list(split_protected(text))
        assert parts == [
            ("Run ", False),
            ("git add minus A", True),
            (" at 37 °C.", False),
        ]
        assert unprotect(text) == "Run git add minus A at 37 °C."

    def test_normalizer_leaves_protected_spans_alone(self):
        text = "See " + protect("Fig. 3 mm equals") + " and Fig. 3 mm."
        assert normalize_words(text) == (
            "See Fig. 3 mm equals and Figure three millimeters."
        )

    def test_lexicon_leaves_protected_spans_alone(self):
        lexicon = Lexicon([Entry("coli", "kˈOlI")])
        text = protect("coli") + " and coli"
        assert lexicon.apply(text) == protect("coli") + " and [coli](/kˈOlI/)"

    def test_sentinels_never_survive_unprotect(self):
        out = unprotect(protect("a") + protect("b"))
        assert "" not in out and "" not in out
