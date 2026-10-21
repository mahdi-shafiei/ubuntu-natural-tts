import pytest

from natural_tts.selection import (
    CLIPBOARD_COMMANDS,
    PRIMARY_COMMANDS,
    READ_TIMEOUT,
    Source,
    read_text,
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


XCLIP_PRIMARY, WL_PRIMARY = PRIMARY_COMMANDS
XCLIP_CLIP, WL_CLIP = CLIPBOARD_COMMANDS


class TestReadText:
    def test_selection_prefers_highlighted_text(self):
        runner = FakeRunner(
            {XCLIP_PRIMARY: "highlighted", XCLIP_CLIP: "copied"}
        )
        assert read_text(Source.SELECTION, runner) == "highlighted"
        assert runner.argvs == [XCLIP_PRIMARY]
        assert_time_limited(runner)

    def test_selection_falls_back_through_wayland_then_clipboard(self):
        runner = FakeRunner(
            {
                XCLIP_PRIMARY: "  \n",
                WL_PRIMARY: None,
                XCLIP_CLIP: None,
                WL_CLIP: "from wayland",
            }
        )
        assert read_text(Source.SELECTION, runner) == "from wayland"
        assert runner.argvs == [XCLIP_PRIMARY, WL_PRIMARY, XCLIP_CLIP, WL_CLIP]
        assert_time_limited(runner)

    def test_clipboard_ignores_stale_highlight(self):
        runner = FakeRunner({XCLIP_PRIMARY: "stale", XCLIP_CLIP: "copied"})
        assert read_text(Source.CLIPBOARD, runner) == "copied"
        assert XCLIP_PRIMARY not in runner.argvs

    def test_nothing_anywhere_gives_empty_string(self):
        assert read_text(Source.SELECTION, FakeRunner({})) == ""

    def test_source_names(self):
        assert Source("selection") is Source.SELECTION
        assert Source("clipboard") is Source.CLIPBOARD


class TestCommands:
    @pytest.mark.parametrize("argv", [PRIMARY_COMMANDS, CLIPBOARD_COMMANDS])
    def test_commands_are_tuples_of_str(self, argv):
        assert all(isinstance(a, str) for cmd in argv for a in cmd)

    def test_timeout_is_short(self):
        assert 0 < READ_TIMEOUT <= 2
