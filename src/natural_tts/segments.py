"""Segments: the unit of speech every reader produces and every engine takes.

A selection becomes a list of segments rather than one string so that each
piece can carry its own pause, speed and voice. Adding a content type adds a
reader that emits segments; the engines never change.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Kind(Enum):
    """What a segment is, for the engine's pause, speed and voice choices."""

    PROSE = "prose"
    HEADING = "heading"
    LIST_ITEM = "list_item"
    QUOTE = "quote"
    CODE = "code"
    MATH = "math"
    TABLE = "table"


@dataclass(frozen=True)
class Segment:
    """One piece of speakable text.

    Attributes:
        text: Words only, safe for the engine (no markup except pronunciation
            markup the engine understands).
        kind: The content type the text came from.
        pause_before: Seconds of silence before the segment.
        rate: Multiplies the engine's configured speed.
        voice: Kokoro voice override, or None for the configured voice.
    """

    text: str
    kind: Kind = Kind.PROSE
    pause_before: float = 0.0
    rate: float = 1.0
    voice: str | None = None

    def __post_init__(self) -> None:
        """Validate values."""
        if not self.text.strip():
            raise ValueError("text must not be blank")
        if self.pause_before < 0:
            raise ValueError("pause_before must be >= 0")
        if self.rate <= 0:
            raise ValueError("rate must be > 0")
