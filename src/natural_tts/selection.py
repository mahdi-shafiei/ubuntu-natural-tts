"""Reading the highlighted text or the clipboard on X11 and Wayland.

Besides the text, the richest form the same selection offers is read:
``text/html`` keeps headings, lists, links and code blocks for the reader.
The HTML comes from the selection that supplied the text, never from
another clipboard, so a stale or sensitive clipboard is not read in its
place. Every call is time-limited.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from natural_tts.system import Runner, run

# Each read is capped: on GNOME/Mutter, wl-paste can hang indefinitely
# because Mutter lacks the data-control protocol.
READ_TIMEOUT = 1.0
HTML_TARGET = "text/html"


@dataclass(frozen=True)
class Tool:
    """One clipboard tool on one selection: how to read text, targets, HTML."""

    text: tuple[str, ...]
    targets: tuple[str, ...]
    html: tuple[str, ...]


def _xclip(selection: str) -> Tool:
    base = ("xclip", "-o", "-selection", selection)
    return Tool(base, (*base, "-t", "TARGETS"), (*base, "-t", HTML_TARGET))


def _wl_paste(*flags: str) -> Tool:
    return Tool(
        ("wl-paste", *flags, "--no-newline"),
        ("wl-paste", *flags, "--list-types"),
        ("wl-paste", *flags, "--no-newline", "--type", HTML_TARGET),
    )


# xclip goes through XWayland, which GNOME keeps in sync, so it is tried
# first. Order: primary (X11, Wayland), then clipboard (X11, Wayland).
TOOLS: tuple[Tool, ...] = (
    _xclip("primary"),
    _wl_paste("--primary"),
    _xclip("clipboard"),
    _wl_paste(),
)
_PRIMARY_TOOLS = TOOLS[:2]
_CLIPBOARD_TOOLS = TOOLS[2:]


@dataclass(frozen=True)
class Selection:
    """What was read: the text, and its HTML when the source offered it."""

    text: str
    html: str | None = None


class Source(enum.Enum):
    """Where to read text from."""

    # Highlighted text, falling back to the clipboard.
    SELECTION = "selection"
    # The clipboard only (Ctrl+C). Needed for apps such as ONLYOFFICE whose
    # canvas-drawn selection never reaches the primary selection, and to
    # avoid reading a stale highlight.
    CLIPBOARD = "clipboard"

    @property
    def tools(self) -> tuple[Tool, ...]:
        """Tools to try, in order."""
        if self is Source.SELECTION:
            return _PRIMARY_TOOLS + _CLIPBOARD_TOOLS
        return _CLIPBOARD_TOOLS


def _read(runner: Runner, argv: tuple[str, ...]) -> str | None:
    result = runner(argv, timeout=READ_TIMEOUT)
    return result.text if result.ok and result.text.strip() else None


def read_selection(source: Source, runner: Runner = run) -> Selection:
    """Return the first non-blank text for ``source`` and its HTML, if any.

    The HTML is read only when the tool that supplied the text lists
    ``text/html`` among its targets; a failed or blank HTML read falls back
    to the text alone.
    """
    for tool in source.tools:
        text = _read(runner, tool.text)
        if text is None:
            continue
        targets = _read(runner, tool.targets) or ""
        html = (
            _read(runner, tool.html) if HTML_TARGET in targets.split() else None
        )
        return Selection(text, html)
    return Selection("", None)
