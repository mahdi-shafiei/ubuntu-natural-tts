import time
from dataclasses import replace
from itertools import islice
from types import GeneratorType

from natural_tts.config import KokoroSettings, ReadingSettings
from natural_tts.daemon import plain_chunker
from natural_tts.reading import prepare
from natural_tts.segments import Kind, Segment
from tests.fakes import make_settings

TEXT = "In E. coli the gene lacZ is expressed, as Dr. Smith showed in Fig. 3."


def texts(segments):
    return [s.text for s in segments]


class TestPrepare:
    def test_returns_prose_segments_lazily(self, tmp_path):
        segments = prepare(TEXT, make_settings(tmp_path))
        assert isinstance(segments, GeneratorType)
        first = next(segments)
        assert isinstance(first, Segment) and first.kind is Kind.PROSE

    def test_english_voice_gets_words_and_pronunciations(self, tmp_path):
        (out,) = texts(prepare(TEXT, make_settings(tmp_path)))
        assert "Figure three" in out and "Doctor Smith" in out
        assert "[E. coli](/" in out and "lac Z" in out

    def test_disabled_gives_todays_chunks_byte_for_byte(self, tmp_path):
        settings = replace(
            make_settings(tmp_path), reading=ReadingSettings(enabled=False)
        )
        assert texts(prepare(TEXT, settings)) == texts(plain_chunker(TEXT))

    def test_non_english_voice_keeps_todays_words(self, tmp_path):
        # Structure (segments, pauses, code reading) applies to every
        # voice; the English word rules and lexicon do not. So the words
        # are exactly today's words, even if the segmentation differs.
        settings = replace(
            make_settings(tmp_path), kokoro=KokoroSettings(voice="ef_dora")
        )
        words = " ".join(texts(prepare(TEXT, settings))).split()
        assert words == " ".join(texts(plain_chunker(TEXT))).split()
        assert "[E. coli]" not in " ".join(texts(prepare(TEXT, settings)))

    def test_british_voice_reads_dates_day_first(self, tmp_path):
        settings = replace(
            make_settings(tmp_path), kokoro=KokoroSettings(voice="bf_emma")
        )
        (out,) = texts(prepare("Due 03/04/2026.", settings))
        assert out == "Due the third of April twenty twenty-six."

    def test_citation_setting_is_honoured(self, tmp_path):
        settings = replace(
            make_settings(tmp_path), reading=ReadingSettings(citations="read")
        )
        (out,) = texts(prepare("As shown [12].", settings))
        assert out == "As shown reference twelve."

    def test_user_lexicon_overrides_the_packaged_one(self, tmp_path):
        settings = make_settings(tmp_path)
        settings.paths.lexicon_file.parent.mkdir(parents=True, exist_ok=True)
        settings.paths.lexicon_file.write_text(
            '[[entry]]\nhead = "coli"\nmisaki = "kˈOli"\n'
        )
        (out,) = texts(prepare("Only coli here.", settings))
        assert "[coli](/kˈOli/)" in out

    def test_blank_and_citation_only_chunks_yield_nothing(self, tmp_path):
        settings = make_settings(tmp_path)
        assert texts(prepare("  \n ", settings)) == []
        assert texts(prepare("[12]", settings)) == []

    def test_first_segment_does_not_wait_for_a_long_selection(self, tmp_path):
        text = (TEXT + " ") * 15_000  # about 1 MiB, the IPC cap
        start = time.perf_counter()
        first = next(prepare(text, make_settings(tmp_path)))
        assert time.perf_counter() - start < 0.05
        assert "Figure three" in first.text

    def test_markup_never_straddles_a_segment(self, tmp_path):
        text = ("E. coli and Saccharomyces cerevisiae grow; " * 400).strip()
        for segment in islice(prepare(text, make_settings(tmp_path)), 50):
            assert segment.text.count("[") == segment.text.count("](/")
            assert segment.text.count("](/") == segment.text.count("/)")
