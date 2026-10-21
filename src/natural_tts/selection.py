"""Reading the highlighted text or the clipboard on X11 and Wayland."""

from __future__ import annotations

import enum

from natural_tts.system import Runner, run

# Each read is capped: on GNOME/Mutter, wl-paste can hang indefinitely
# because Mutter lacks the data-control protocol.
READ_TIMEOUT = 1.0

# xclip goes through XWayland, which GNOME keeps in sync, so it is tried first.
PRIMARY_COMMANDS: tuple[tuple[str, ...], ...] = (
    ("xclip", "-o", "-selection", "primary"),
    ("wl-paste", "--primary", "--no-newline"),
)
CLIPBOARD_COMMANDS: tuple[tuple[str, ...], ...] = (
    ("xclip", "-o", "-selection", "clipboard"),
    ("wl-paste", "--no-newline"),
)


class Source(enum.Enum):
    """Where to read text from."""

    # Highlighted text, falling back to the clipboard.
    SELECTION = "selection"
    # The clipboard only (Ctrl+C). Needed for apps such as ONLYOFFICE whose
    # canvas-drawn selection never reaches the primary selection, and to
    # avoid reading a stale highlight.
    CLIPBOARD = "clipboard"

    @property
    def commands(self) -> tuple[tuple[str, ...], ...]:
        """Commands to try, in order."""
        if self is Source.SELECTION:
            return PRIMARY_COMMANDS + CLIPBOARD_COMMANDS
        return CLIPBOARD_COMMANDS


def read_text(source: Source, runner: Runner = run) -> str:
    """Return the first non-blank text found for ``source`` ('' if none)."""
    for argv in source.commands:
        result = runner(argv, timeout=READ_TIMEOUT)
        if result.ok and result.text.strip():
            return result.text
    return ""
