import sys
import time
from dataclasses import replace
from itertools import islice
from pathlib import Path
from types import GeneratorType

import pytest

from natural_tts.config import KokoroSettings, ReadingSettings
from natural_tts.daemon import plain_chunker
from natural_tts.ipc import HTML_FORMAT
from natural_tts.reading import chunker_for, prepare
from natural_tts.segments import Kind, Segment
from tests.fakes import make_settings

TEXT = "In E. coli the gene lacZ is expressed, as Dr. Smith showed in Fig. 3."


def texts(segments):
    return [s.text for s in segments]


class TestChunkerFor:
    def test_binds_the_settings_and_passes_the_format(self, tmp_path):
        chunker = chunker_for(make_settings(tmp_path))
        (segment,) = list(chunker("See Fig. 3.", None))
        assert segment.text == "See Figure three."


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


HTML = (
    "<h2>Results</h2><p>Run <code>git add -A</code> at 37 °C, see Fig. 3.</p>"
    "<ul><li>first item</li><li>second item</li></ul>"
    "<ol><li>alpha</li><li>beta</li></ol>"
    "<blockquote><p>a quote</p></blockquote>"
    '<pre><code class="language-python">def f(x):\n'
    "    return x[0]\n</code></pre>"
    "<table><tr><th>Name</th><th>Size</th></tr>"
    "<tr><td>a</td><td>5 mm</td></tr></table>"
)


class TestStructure:
    def test_html_becomes_typed_segments(self, tmp_path):
        out = list(prepare(HTML, make_settings(tmp_path), HTML_FORMAT))
        kinds = [s.kind for s in out]
        assert kinds[:7] == [
            Kind.HEADING,
            Kind.PROSE,
            Kind.LIST_ITEM,
            Kind.LIST_ITEM,
            Kind.LIST_ITEM,
            Kind.LIST_ITEM,
            Kind.QUOTE,
        ]
        assert Kind.CODE in kinds and Kind.TABLE in kinds
        heading = out[0]
        assert heading.text == "Results"
        assert heading.pause_before == 0.6 and heading.rate == 0.9

    def test_prose_words_are_normalised_but_inline_code_is_not(self, tmp_path):
        out = list(prepare(HTML, make_settings(tmp_path), HTML_FORMAT))
        prose = out[1].text
        assert "git add minus A" in prose
        assert "thirty-seven degrees Celsius" in prose
        assert "Figure three" in prose
        assert "`" not in prose and "\ue000" not in prose

    def test_list_items_pause_and_ordered_ones_count(self, tmp_path):
        out = list(prepare(HTML, make_settings(tmp_path), HTML_FORMAT))
        items = [s for s in out if s.kind is Kind.LIST_ITEM]
        assert [s.text for s in items] == [
            "first item",
            "second item",
            "one, alpha",
            "two, beta",
        ]
        assert all(s.pause_before == 0.25 for s in items)

    def test_code_is_read_at_the_configured_level(self, tmp_path):
        settings = make_settings(tmp_path)
        code = [
            s
            for s in prepare(HTML, settings, HTML_FORMAT)
            if s.kind is Kind.CODE
        ]
        assert code[0].text == "def f x. return x zero"
        assert code[0].rate == 0.9 and code[0].voice is None
        level_two = replace(settings, reading=ReadingSettings(code_level=2))
        code = [
            s
            for s in prepare(HTML, level_two, HTML_FORMAT)
            if s.kind is Kind.CODE
        ]
        assert code[0].text.startswith("def f left paren x right paren colon.")

    def test_tables_announce_their_shape_then_rows(self, tmp_path):
        out = list(prepare(HTML, make_settings(tmp_path), HTML_FORMAT))
        table = [s for s in out if s.kind is Kind.TABLE]
        assert [s.text for s in table] == [
            "table, two columns, one row",
            "Name: a, Size: five millimeters",
        ]
        assert all(s.pause_before == 0.25 for s in table)

    def test_markdown_in_plain_text_is_structured_too(self, tmp_path):
        text = "# Title\n\nSome prose.\n\n```sh\nls -la\n```\n"
        out = list(prepare(text, make_settings(tmp_path)))
        assert [s.kind for s in out] == [Kind.HEADING, Kind.PROSE, Kind.CODE]
        assert out[2].text == "ls minus la"

    def test_disabled_reads_html_as_plain_chunks(self, tmp_path):
        settings = replace(
            make_settings(tmp_path), reading=ReadingSettings(enabled=False)
        )
        assert texts(prepare(HTML, settings, HTML_FORMAT)) == texts(
            plain_chunker(HTML)
        )

    def test_non_english_voice_gets_structure_but_no_word_rules(self, tmp_path):
        settings = replace(
            make_settings(tmp_path), kokoro=KokoroSettings(voice="ef_dora")
        )
        out = list(prepare(HTML, settings, HTML_FORMAT))
        assert out[0].kind is Kind.HEADING
        assert "37 °C" in out[1].text and "Fig. 3" in out[1].text

    def test_first_segment_time_does_not_grow_with_the_document(self, tmp_path):
        settings = make_settings(tmp_path)

        def first_ms(text, format):
            start = time.perf_counter()
            next(prepare(text, settings, format))
            return time.perf_counter() - start

        page_md = "# Title\n\n" + "Some prose here.\n\n- item\n\n" * 400
        cap_md = "# Title\n\n" + "Some prose here.\n\n- item\n\n" * 45000
        page_html = "<h1>Title</h1>" + "<p>more words here.</p>" * 400
        cap_html = "<h1>Title</h1>" + "<p>more words here.</p>" * 50000
        for page, cap, format in (
            (page_md, cap_md, None),
            (page_html, cap_html, HTML_FORMAT),
        ):
            assert len(cap) > 1_000_000
            small = min(first_ms(page, format) for _ in range(3))
            large = min(first_ms(cap, format) for _ in range(3))
            assert large < 2.5 * small + 0.01

    def test_no_sentinel_or_broken_markup_in_any_segment(self, tmp_path):
        text = "Run `x = 1` on E. coli and `y`; see Saccharomyces.\n\n" * 300
        for segment in prepare(text, make_settings(tmp_path)):
            assert "\ue000" not in segment.text and "\ue001" not in segment.text
            assert segment.text.count("[") == segment.text.count("](/")


FAKE_HELPER = Path(__file__).with_name("fake_mathcat.py")


@pytest.fixture
def fake_helper(tmp_path):
    """Install a shim running the fake helper where setup would put it."""
    helper = make_settings(tmp_path).paths.mathcat_helper
    helper.parent.mkdir(parents=True, exist_ok=True)
    helper.write_text(
        f'#!/bin/sh\nexec "{sys.executable}" "{FAKE_HELPER}" "$@"\n'
    )
    helper.chmod(0o755)
    return helper


class TestMath:
    def test_display_math_becomes_math_segments_with_mathcats_pauses(
        self, tmp_path, fake_helper
    ):
        text = "Before.\n\n$$\\frac{a}{b}$$\n\nAfter."
        out = list(prepare(text, make_settings(tmp_path)))
        math = [s for s in out if s.kind is Kind.MATH]
        assert [s.text for s in math] == [
            "[ClearSpeak Medium] cap A. over",
            "b",
            "end",
        ]
        assert [s.pause_before for s in math] == [0.25, 0.128, 0.4]

    def test_inline_math_is_spoken_inside_the_sentence(
        self, tmp_path, fake_helper
    ):
        (out,) = texts(
            prepare("where $x^2 + y^2 = r^2$ holds.", make_settings(tmp_path))
        )
        assert out == "where [ClearSpeak Medium] cap A. over, b, end holds."

    def test_simplespeak_and_verbose_for_deep_nesting(
        self, tmp_path, fake_helper
    ):
        settings = replace(
            make_settings(tmp_path),
            reading=ReadingSettings(math_style="simplespeak"),
        )
        (out,) = texts(prepare("so $\\sqrt{\\frac{a}{b}}$ holds.", settings))
        assert out.startswith("so [SimpleSpeak Verbose]")

    def test_missing_helper_falls_back_to_the_word_rules(self, tmp_path):
        (out,) = texts(
            prepare("where $x^2 + y^2 = r^2$ holds.", make_settings(tmp_path))
        )
        assert out == "where x squared plus y squared equals r squared holds."
        text = "Before.\n\n$$a^2$$\n\nAfter."
        kinds = [s.kind for s in prepare(text, make_settings(tmp_path))]
        assert kinds == [Kind.PROSE, Kind.MATH, Kind.PROSE]

    def test_one_helper_process_per_chunker(self, tmp_path, fake_helper):
        chunker = chunker_for(make_settings(tmp_path))
        assert chunker.mathcat is not None
        list(chunker("$$a^2$$", None))
        first = chunker.mathcat.process
        list(chunker("$$b^2$$", None))
        assert chunker.mathcat.process is first and first is not None
        chunker.close()
        assert chunker.mathcat.process is None

    def test_language_follows_the_voice(self, tmp_path, fake_helper):
        settings = replace(
            make_settings(tmp_path), kokoro=KokoroSettings(voice="ef_dora")
        )
        with chunker_for(settings) as chunker:
            assert chunker.mathcat is not None
            assert chunker.mathcat.language == "es"
        with chunker_for(make_settings(tmp_path)) as chunker:
            assert chunker.mathcat is not None
            assert chunker.mathcat.language == "en"

    def test_pdf_formula_line_goes_through_mathcat(self, tmp_path, fake_helper):
        text = "Energy is given by\n\nE = mc²\n\nwhere m is mass."
        out = list(prepare(text, make_settings(tmp_path)))
        assert [s.kind for s in out][:2] == [Kind.PROSE, Kind.MATH]

    def test_disabled_reads_latex_raw(self, tmp_path, fake_helper):
        settings = replace(
            make_settings(tmp_path), reading=ReadingSettings(enabled=False)
        )
        text = "$$\\frac{a}{b}$$"
        assert texts(prepare(text, settings)) == texts(plain_chunker(text))

    def test_missing_latex2mathml_falls_back_with_one_warning(
        self, tmp_path, fake_helper, monkeypatch, caplog
    ):
        monkeypatch.setitem(sys.modules, "latex2mathml.converter", None)
        text = "where $x^2$ and $y^2$ hold."
        (out,) = texts(prepare(text, make_settings(tmp_path)))
        assert out == "where x squared and y squared hold."
        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) == 1 and "latex2mathml" in warnings[0].message
