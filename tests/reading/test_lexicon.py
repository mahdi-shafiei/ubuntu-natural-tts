from pathlib import Path

import pytest

from natural_tts.reading.lexicon import (
    Entry,
    Lexicon,
    LexiconError,
    load_lexicon,
    packaged_lexicon,
)
from natural_tts.reading.normalize import normalize_words


def entries(*pairs: tuple[str, str]) -> Lexicon:
    return Lexicon([Entry(head, misaki) for head, misaki in pairs])


class TestPackagedLexicon:
    def test_loads_and_covers_the_seed_words(self):
        lexicon = packaged_lexicon()
        heads = {entry.head for entry in lexicon.entries}
        assert {"coli", "E. coli", "in vitro", "Cas9", "metformin"} <= heads
        assert len(lexicon.entries) >= 20

    def test_every_entry_round_trips_with_punctuation(self):
        lexicon = packaged_lexicon()
        for entry in lexicon.entries:
            out = lexicon.apply(f"See {entry.head}, then {entry.head}.")
            if entry.words:
                assert out == f"See {entry.words}, then {entry.words}.", out
                continue
            assert out.count("](/") == 2
            assert out.endswith("/)."), out
            assert "/)," in out, out


class TestSchema:
    def test_rejects_a_bracket_in_the_phonemes(self):
        with pytest.raises(LexiconError, match="misaki"):
            Entry("x", "kˈO)lI")

    def test_rejects_symbols_outside_misakis_alphabet(self):
        with pytest.raises(LexiconError, match="not in misaki's alphabet"):
            Entry("x", "kˈoʊlaɪ")

    def test_rejects_unknown_match_mode(self):
        with pytest.raises(LexiconError, match="match"):
            Entry("x", "ˈɛks", match="fuzzy")

    def test_rejects_blank_head(self):
        with pytest.raises(LexiconError, match="head"):
            Entry(" ", "ˈɛks")

    def test_file_with_unknown_key_is_rejected(self, tmp_path):
        path = tmp_path / "lexicon.toml"
        path.write_text('[[entry]]\nhead = "x"\nmisaki = "ˈɛks"\nvoice = 1\n')
        with pytest.raises(LexiconError, match="unknown key"):
            load_lexicon(path)

    def test_invalid_toml_is_rejected(self, tmp_path):
        path = tmp_path / "lexicon.toml"
        path.write_text("[[entry\n")
        with pytest.raises(LexiconError, match="invalid TOML"):
            load_lexicon(path)


class TestApply:
    def test_marks_whole_words_with_punctuation_outside(self):
        lexicon = entries(("coli", "kˈOlI"))
        assert lexicon.apply("E. coli, then coli.") == (
            "E. [coli](/kˈOlI/), then [coli](/kˈOlI/)."
        )

    def test_does_not_mark_inside_other_words(self):
        assert entries(("coli", "kˈOlI")).apply("colitis") == "colitis"

    def test_case_insensitive_by_default_exact_on_request(self):
        assert entries(("coli", "kˈOlI")).apply("COLI") == "[COLI](/kˈOlI/)"
        exact = Lexicon([Entry("lacZ", "lˈæk zˈi", match="exact")])
        assert exact.apply("LACZ and lacZ") == "LACZ and [lacZ](/lˈæk zˈi/)"

    def test_multi_word_heads_win_over_their_parts(self):
        lexicon = entries(("E. coli", "ˌi kˈOlI"), ("coli", "kˈOlI"))
        assert lexicon.apply("In E. coli cells") == (
            "In [E. coli](/ˌi kˈOlI/) cells"
        )

    def test_adjacent_entries_keep_a_space(self):
        lexicon = entries(("in vitro", "ɪn vˈitɹO"), ("coli", "kˈOlI"))
        out = lexicon.apply("coli in vitro")
        assert out == "[coli](/kˈOlI/) [in vitro](/ɪn vˈitɹO/)"

    def test_existing_markup_is_left_alone(self):
        lexicon = entries(("coli", "kˈOlI"))
        marked = "[coli](/kˈOlI/) and coli"
        assert lexicon.apply(marked) == "[coli](/kˈOlI/) and [coli](/kˈOlI/)"

    def test_words_rewrite_instead_of_phonemes(self):
        lexicon = Lexicon([Entry("et al.", "", words="et al")])
        assert lexicon.apply("Smith et al. found") == "Smith et al found"


class TestUserFile:
    def test_user_entries_override_packaged_ones(self, tmp_path):
        path = tmp_path / "lexicon.toml"
        path.write_text('[[entry]]\nhead = "coli"\nmisaki = "kˈOli"\n')
        merged = packaged_lexicon().merged(load_lexicon(path))
        assert merged.apply("coli") == "[coli](/kˈOli/)"

    def test_missing_user_file_is_empty(self, tmp_path):
        assert load_lexicon(tmp_path / "none.toml").entries == ()


class TestNormalizerLeavesMarkupAlone:
    def test_markup_spans_are_not_rewritten(self):
        text = "[Cas9](/kˈæs nˈIn/) at 37 °C and [E. coli](/ˌi kˈOlI/)."
        assert normalize_words(text) == (
            "[Cas9](/kˈæs nˈIn/) at thirty-seven degrees Celsius and "
            "[E. coli](/ˌi kˈOlI/)."
        )


def test_packaged_file_lives_in_the_package():
    from natural_tts import reading

    assert (Path(reading.__file__).parent / "data" / "lexicon.toml").is_file()


class TestPackagedInitialisms:
    def test_ieee_is_read_i_triple_e(self):
        lexicon = packaged_lexicon()
        assert lexicon.apply("the IEEE standard") == "the I triple E standard"
