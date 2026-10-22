"""The structural unit of a selection, shared by every reader."""

from __future__ import annotations

from dataclasses import dataclass

from natural_tts.segments import Kind


@dataclass(frozen=True)
class Block:
    """One structural unit of a selection.

    Attributes:
        kind: What it is; TABLE blocks carry ``columns`` and ``rows``.
        text: Prose or code text (code keeps its lines; prose may keep
            line breaks that the prose reader joins).
        level: Heading level, 1 to 6, for headings.
        ordered_index: The item's number in an ordered list, else None.
        language: A code block's language as the document named it; a
            MATH block's source form: ``latex``, ``unicode`` or ``mathml``.
        columns: Table header cells (two header rows joined as "Group, Name").
        rows: Table body rows, spanning cells repeated in every cell they cover.
        caption: The table's caption, or "".
        row_headers: Whether the first cell of each row names the row.
    """

    kind: Kind
    text: str
    level: int = 0
    ordered_index: int | None = None
    language: str | None = None
    columns: tuple[str, ...] = ()
    rows: tuple[tuple[str, ...], ...] = ()
    caption: str = ""
    row_headers: bool = False
