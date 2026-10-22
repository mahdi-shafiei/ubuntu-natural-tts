import sys
import time
from pathlib import Path

import pytest

from natural_tts.reading.mathcat import (
    MathCat,
    MathCatUnavailable,
    parse_ssml,
    sentence,
)

FAKE = Path(__file__).with_name("fake_mathcat.py")
FRACTION = "<math><mfrac><mi>a</mi><mi>b</mi></mfrac></math>"


@pytest.fixture
def client():
    with MathCat([sys.executable, str(FAKE)], language="en", timeout=1.0) as c:
        yield c


class TestParseSsml:
    def test_breaks_become_pauses_and_characters_are_spelled(self):
        ssml = (
            "cap <say-as interpret-as='characters'>A</say-as> over "
            "<break time='128ms'/> <say-as interpret-as='characters'>b</say-as>"
            " <break time='400ms'/> end"
        )
        assert parse_ssml(ssml) == [
            (0.0, "cap A. over"),
            (0.128, "b"),
            (0.4, "end"),
        ]

    def test_plain_text_is_one_piece(self):
        assert parse_ssml("a over b") == [(0.0, "a over b")]

    def test_other_tags_are_dropped_and_entities_decoded(self):
        assert parse_ssml("<prosody rate='80%'>x &amp; y</prosody>") == [
            (0.0, "x & y")
        ]


class TestClient:
    def test_starts_lazily_and_speaks(self, client):
        assert client.process is None
        pieces = client.speak(FRACTION)
        assert client.process is not None
        assert pieces[0][1].startswith("[ClearSpeak Medium] cap A. over")

    def test_switches_style_only_when_it_changes(self, client):
        client.speak(FRACTION)
        client.speak(FRACTION, style="SimpleSpeak", verbosity="Terse")
        pieces = client.speak(FRACTION, style="SimpleSpeak", verbosity="Terse")
        assert pieces[0][1].startswith("[SimpleSpeak Terse]")
        assert client.switches == 1

    def test_error_lines_raise(self, client):
        with pytest.raises(MathCatUnavailable, match="Invalid MathML"):
            client.speak("<math>bad</math>")
        assert client.speak(FRACTION)  # still alive

    def test_crash_is_recovered_on_the_next_call(self, client):
        with pytest.raises(MathCatUnavailable):
            client.speak("<math>crash</math>")
        assert client.speak(FRACTION)[0][1].startswith("[ClearSpeak Medium]")

    def test_hang_times_out_and_restarts(self, client):
        start = time.perf_counter()
        with pytest.raises(MathCatUnavailable, match="timed out"):
            client.speak("<math>hang</math>")
        assert time.perf_counter() - start < 3
        assert client.speak(FRACTION)

    def test_newlines_inside_mathml_are_removed_before_sending(self, client):
        pieces = client.speak("<math>\n<mi>a</mi>\n</math>")
        assert pieces[0][1].startswith("[ClearSpeak Medium]")

    def test_missing_binary_is_unavailable_not_a_crash(self):
        with (
            MathCat(["/nonexistent/natural-tts-mathcat"], language="en") as c,
            pytest.raises(MathCatUnavailable, match="not found"),
        ):
            c.speak(FRACTION)

    def test_close_terminates_the_process(self):
        c = MathCat([sys.executable, str(FAKE)], language="en")
        c.speak(FRACTION)
        process = c.process
        c.close()
        assert process is not None and process.poll() is not None


class TestSentence:
    def test_breaks_become_punctuation_by_length(self):
        pieces = [
            (0.0, "the integral from 0"),
            (0.128, "to 1 of"),
            (0.256, "f of x d x"),
            (0.4, "is equal to"),
            (0.8, "one"),
        ]
        assert (
            sentence(pieces)
            == "the integral from 0 to 1 of, f of x d x. is equal to. one"
        )

    def test_single_piece_and_empty(self):
        assert sentence([(0.0, "x")]) == "x"
        assert sentence([]) == ""
