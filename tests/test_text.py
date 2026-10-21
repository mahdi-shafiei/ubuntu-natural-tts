import random

import pytest

from natural_tts.text import chunk_text, clean_text, decode_text

FIRST, MAX = 60, 300


def words(chunks: list[str]) -> list[str]:
    return " ".join(chunks).split()


class TestCleanText:
    def test_rejoins_words_hyphenated_across_line_breaks(self):
        assert clean_text("trans-\nformed") == "transformed"

    def test_keeps_real_hyphens(self):
        assert clean_text("near-experimental") == "near-experimental"

    def test_collapses_hard_wraps_and_extra_whitespace(self):
        assert clean_text("one\n  two\r\n\tthree   four") == (
            "one two three four"
        )

    def test_strips(self):
        assert clean_text("  \n hi \n ") == "hi"


class TestChunkText:
    @pytest.mark.parametrize("text", ["", "   ", "\n\n\t"])
    def test_blank_input_gives_no_chunks(self, text):
        assert chunk_text(text, FIRST, MAX) == []

    def test_short_text_is_one_chunk(self):
        assert chunk_text("Hi.", FIRST, MAX) == ["Hi."]

    def test_short_sentences_are_merged_until_first_minimum(self):
        text = "One. Two. Three is a longer sentence that goes past the limit."
        chunks = chunk_text(text, FIRST, MAX)
        assert len(chunks[0]) >= FIRST or len(chunks) == 1
        assert chunks[0].startswith("One. Two.")

    def test_later_chunks_hold_several_sentences(self):
        sentence = "This sentence is about forty characters. "
        chunks = chunk_text(sentence * 20, FIRST, MAX)
        assert len(chunks) > 2
        assert all(len(c) <= MAX for c in chunks)
        assert all(c.count(".") >= 2 for c in chunks[1:-1])

    def test_long_opening_sentence_is_split_at_a_comma_for_a_fast_start(self):
        text = (
            "Kokoro is an open-weight text to speech model with eighty "
            "two million parameters, and it is surprisingly natural for "
            "its size, which makes it a good fit for reading documents."
        )
        chunks = chunk_text(text, FIRST, MAX)
        assert chunks[0].endswith("parameters,")
        assert len(chunks[0]) < len(text) // 2 + FIRST

    def test_long_opening_sentence_without_comma_is_not_split(self):
        text = "word " * 30 + "end."
        assert len(chunk_text(text, FIRST, MAX)) == 1

    def test_unpunctuated_text_is_wrapped_at_word_boundaries(self):
        text = "no punctuation at all just words " * 20
        chunks = chunk_text(text, FIRST, MAX)
        assert all(len(c) <= MAX for c in chunks)
        assert words(chunks) == text.split()

    def test_overlong_single_word_is_kept_whole(self):
        url = "https://example.org/" + "a" * 400
        chunks = chunk_text(f"See {url} now.", FIRST, MAX)
        assert url in chunks[0].split() or url in " ".join(chunks).split()
        assert words(chunks) == ["See", url, "now."]

    def test_pdf_text_is_cleaned_before_chunking(self):
        chunks = chunk_text(
            "Deep learning has trans-\nformed biology.", FIRST, MAX
        )
        assert chunks == ["Deep learning has transformed biology."]

    @pytest.mark.parametrize("seed", range(25))
    def test_no_words_lost_and_limits_hold_on_random_text(self, seed):
        rng = random.Random(seed)
        vocab = [
            "alpha",
            "beta,",
            "gamma.",
            "delta!",
            "eps?",
            "zeta;",
            "eta:",
            "theta",
            "iota",
            "kappa-\nlambda",
        ]
        text = " ".join(rng.choice(vocab) for _ in range(rng.randint(1, 400)))
        chunks = chunk_text(text, FIRST, MAX)
        assert words(chunks) == clean_text(text).split()
        assert all(c and c == c.strip() for c in chunks)
        assert all(len(c) <= MAX for c in chunks)

    def test_rejects_inconsistent_limits(self):
        with pytest.raises(ValueError, match="first_min"):
            chunk_text("x", 400, 300)
        with pytest.raises(ValueError, match="first_min"):
            chunk_text("x", 0, 300)


class TestDecodeText:
    def test_utf8(self):
        assert decode_text("Café — “ok”".encode()) == "Café — “ok”"

    def test_latin1_from_speech_dispatcher(self):
        # Speech Dispatcher re-encodes text to ISO-8859-1 for languages
        # its generic module config does not declare as UTF-8.
        assert decode_text("Café naïve".encode("latin-1")) == "Café naïve"

    def test_never_yields_surrogates(self):
        text = decode_text(bytes(range(256)))
        assert all(not 0xD800 <= ord(c) <= 0xDFFF for c in text)
        text.encode("utf-8")  # must not raise
