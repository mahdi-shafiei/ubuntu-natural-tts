import pytest

from natural_tts.selection import (
    HTML_TARGET,
    READ_TIMEOUT,
    TOOLS,
    Selection,
    Source,
    read_selection,
)
from natural_tts.system import Result
from tests.fakes import RecordingRunner


def FakeRunner(outputs):
    """Answers with canned output per command; None means failure."""

    def respond(argv):
        out = outputs.get(argv)
        if out is None:
            return Result(1, b"", b"no selection")
        return Result(0, out.encode(), b"")

    return RecordingRunner(respond)


def assert_time_limited(runner):
    # wl-paste can hang on GNOME/Mutter; every read must be time-limited.
    assert all(c.timeout == READ_TIMEOUT for c in runner.calls)


XCLIP_PRIMARY, WL_PRIMARY, XCLIP_CLIP, WL_CLIP = TOOLS
PLAIN_TARGETS = "TIMESTAMP TARGETS UTF8_STRING STRING text/plain"
HTML_TARGETS = PLAIN_TARGETS + "\ntext/html"


class TestReadSelection:
    def test_selection_prefers_highlighted_text(self):
        runner = FakeRunner(
            {
                XCLIP_PRIMARY.text: "highlighted",
                XCLIP_PRIMARY.targets: PLAIN_TARGETS,
                XCLIP_CLIP.text: "copied",
            }
        )
        assert read_selection(Source.SELECTION, runner) == Selection(
            "highlighted", None
        )
        assert runner.argvs == [XCLIP_PRIMARY.text, XCLIP_PRIMARY.targets]
        assert_time_limited(runner)

    def test_html_is_read_when_the_same_selection_offers_it(self):
        runner = FakeRunner(
            {
                XCLIP_PRIMARY.text: "the docs",
                XCLIP_PRIMARY.targets: HTML_TARGETS,
                XCLIP_PRIMARY.html: "<p>the <b>docs</b></p>",
            }
        )
        assert read_selection(Source.SELECTION, runner) == Selection(
            "the docs", "<p>the <b>docs</b></p>"
        )
        assert runner.argvs == [
            XCLIP_PRIMARY.text,
            XCLIP_PRIMARY.targets,
            XCLIP_PRIMARY.html,
        ]
        assert_time_limited(runner)

    def test_html_target_name(self):
        assert HTML_TARGET == "text/html"
        assert HTML_TARGET in HTML_TARGETS.split()

    def test_failed_or_blank_html_falls_back_to_the_text(self):
        for html in (None, "  \n"):
            runner = FakeRunner(
                {
                    XCLIP_PRIMARY.text: "words",
                    XCLIP_PRIMARY.targets: HTML_TARGETS,
                    XCLIP_PRIMARY.html: html,
                }
            )
            assert read_selection(Source.SELECTION, runner) == Selection(
                "words", None
            )

    def test_failed_targets_query_means_text_only(self):
        runner = FakeRunner({XCLIP_PRIMARY.text: "words"})
        assert read_selection(Source.SELECTION, runner) == Selection(
            "words", None
        )
        assert XCLIP_PRIMARY.html not in runner.argvs

    def test_selection_falls_back_through_wayland_then_clipboard(self):
        runner = FakeRunner(
            {
                XCLIP_PRIMARY.text: "  \n",
                WL_PRIMARY.text: None,
                XCLIP_CLIP.text: None,
                WL_CLIP.text: "from wayland",
                WL_CLIP.targets: "text/plain\ntext/html",
                WL_CLIP.html: "<i>from wayland</i>",
            }
        )
        assert read_selection(Source.SELECTION, runner) == Selection(
            "from wayland", "<i>from wayland</i>"
        )
        assert runner.argvs == [
            XCLIP_PRIMARY.text,
            WL_PRIMARY.text,
            XCLIP_CLIP.text,
            WL_CLIP.text,
            WL_CLIP.targets,
            WL_CLIP.html,
        ]
        assert_time_limited(runner)

    def test_clipboard_ignores_stale_highlight(self):
        runner = FakeRunner(
            {XCLIP_PRIMARY.text: "stale", XCLIP_CLIP.text: "copied"}
        )
        assert read_selection(Source.CLIPBOARD, runner).text == "copied"
        assert XCLIP_PRIMARY.text not in runner.argvs

    def test_nothing_anywhere_gives_an_empty_selection(self):
        assert read_selection(Source.SELECTION, FakeRunner({})) == Selection(
            "", None
        )

    def test_source_names(self):
        assert Source("selection") is Source.SELECTION
        assert Source("clipboard") is Source.CLIPBOARD


class TestTools:
    @pytest.mark.parametrize("tool", TOOLS)
    def test_commands_are_tuples_of_str(self, tool):
        for argv in (tool.text, tool.targets, tool.html):
            assert all(isinstance(a, str) for a in argv)

    def test_wayland_tools_never_append_a_newline(self):
        assert (
            "--no-newline" in WL_PRIMARY.text and "--no-newline" in WL_CLIP.text
        )

    def test_timeout_is_short(self):
        assert 0 < READ_TIMEOUT <= 2
