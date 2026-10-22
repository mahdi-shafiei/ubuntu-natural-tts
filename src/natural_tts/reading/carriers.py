"""Code-block carriers in plain text other than Markdown.

reStructuredText literal blocks and code directives, LaTeX verbatim-style
environments, Org mode and AsciiDoc source blocks, Python and IPython
prompts, terminal transcripts, unified diffs, a shebang line, and dense
unmarked code. Everything not claimed by a carrier is prose.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from natural_tts.reading.blocks import Block
from natural_tts.segments import Kind

_RST_LITERAL = re.compile(r"::\s*$")
_RST_DIRECTIVE = re.compile(
    r"^\s*\.\. (?:code-block|code|sourcecode)::\s*(\S+)?\s*$"
)
_RST_OPTION = re.compile(r"^\s+:[\w-]+:")
_LATEX_BEGIN = re.compile(
    r"^\s*\\begin\{(verbatim|lstlisting|minted)\}"
    r"(?:\[[^\]]*language=([A-Za-z0-9+#]+)[^\]]*\])?(?:\{([A-Za-z0-9+#]+)\})?"
)
_ORG_BEGIN = re.compile(
    r"^\s*#\+begin_(src|example)(?:\s+(\S+))?", re.IGNORECASE
)
_ASCIIDOC_SOURCE = re.compile(r"^\[source(?:,\s*([\w+#-]+))?[^\]]*\]\s*$")
_ASCIIDOC_FENCE = re.compile(r"^-{4,}\s*$")
_PYTHON_PROMPT = re.compile(r"^(>>> |\.\.\. )")
_IPYTHON = re.compile(r"^(In \[\d+\]: |Out\[\d+\]: )")
# Only "$ " prompts: "# " is also a Markdown heading and a comment.
_SHELL_PROMPT = re.compile(r"^\$ \S")
_DIFF_HEADER = re.compile(r"^(?:--- |\+\+\+ |@@ )")
_SHEBANG = re.compile(r"^#!\s*(\S+)(?:\s+(\S+))?")
_CODE_LINE_END = re.compile(r"[;{}:]\s*$")
_SENTENCE_END = re.compile(r"\b[a-z]{2,}\.\s*$")


@dataclass(frozen=True)
class _Span:
    kind: Kind
    lines: list[str]
    language: str | None


def scan(window: str) -> Iterator[Block]:
    """Yield prose and code blocks for a plain-text window."""
    lines = window.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    dense = _looks_like_dense_code(lines)
    index = 0
    prose: list[str] = []

    def flush_prose() -> Iterator[Block]:
        text = "\n".join(prose).strip()
        prose.clear()
        if text:
            yield Block(Kind.PROSE, text)

    if dense:
        language = _shebang_language(lines[0]) if lines else None
        yield Block(Kind.CODE, "\n".join(lines).strip("\n"), language=language)
        return
    while index < len(lines):
        found = None
        for carrier in _CARRIERS:
            found = carrier(lines, index)
            if found is not None:
                break
        if found is None:
            prose.append(lines[index])
            index += 1
            continue
        yield from flush_prose()
        span, index = found
        text = "\n".join(span.lines).strip("\n")
        if text:
            yield Block(span.kind, text, language=span.language)
    yield from flush_prose()


# -- the carriers: each returns (span, next_index) or None ---------------------

Carrier = Callable[[list[str], int], "tuple[_Span, int] | None"]


def _indented_body(lines: list[str], start: int) -> tuple[list[str], int]:
    body: list[str] = []
    index = start
    while index < len(lines) and (
        not lines[index].strip() or lines[index][:1].isspace()
    ):
        body.append(lines[index])
        index += 1
    while body and not body[-1].strip():
        body.pop()
    return _dedent(body), index


def _dedent(lines: list[str]) -> list[str]:
    indents = [len(line) - len(line.lstrip()) for line in lines if line.strip()]
    cut = min(indents) if indents else 0
    return [line[cut:] for line in lines]


def _rst_literal(lines: list[str], index: int) -> tuple[_Span, int] | None:
    if not _RST_LITERAL.search(lines[index]) or lines[
        index
    ].lstrip().startswith(".."):
        return None
    if index + 1 >= len(lines) or lines[index + 1].strip():
        return None
    body, end = _indented_body(lines, index + 2)
    if not body:
        return None
    # The introducing paragraph stays prose; keep its text without "::".
    return _Span(Kind.CODE, body, None), end


def _rst_directive(lines: list[str], index: int) -> tuple[_Span, int] | None:
    match = _RST_DIRECTIVE.match(lines[index])
    if not match:
        return None
    position = index + 1
    while position < len(lines) and _RST_OPTION.match(lines[position]):
        position += 1
    body, end = _indented_body(lines, position)
    language = match.group(1).lower() if match.group(1) else None
    return _Span(Kind.CODE, body, language), end


def _latex(lines: list[str], index: int) -> tuple[_Span, int] | None:
    match = _LATEX_BEGIN.match(lines[index])
    if not match:
        return None
    closer = f"\\end{{{match.group(1)}}}"
    language = (match.group(2) or match.group(3) or "").lower() or None
    return _until(lines, index + 1, lambda line: closer in line, language)


def _org(lines: list[str], index: int) -> tuple[_Span, int] | None:
    match = _ORG_BEGIN.match(lines[index])
    if not match:
        return None
    closer = re.compile(rf"^\s*#\+end_{match.group(1)}\b", re.IGNORECASE)
    language = (match.group(2) or "").lower() or None
    return _until(
        lines, index + 1, lambda line: bool(closer.match(line)), language
    )


def _asciidoc(lines: list[str], index: int) -> tuple[_Span, int] | None:
    language = None
    position = index
    match = _ASCIIDOC_SOURCE.match(lines[position])
    if match:
        language = (match.group(1) or "").lower() or None
        position += 1
    if position >= len(lines) or not _ASCIIDOC_FENCE.match(lines[position]):
        return None
    return _until(
        lines,
        position + 1,
        lambda line: bool(_ASCIIDOC_FENCE.match(line)),
        language,
    )


def _python_prompt(lines: list[str], index: int) -> tuple[_Span, int] | None:
    if not _PYTHON_PROMPT.match(lines[index]):
        return None
    body: list[str] = []
    position = index
    while position < len(lines) and lines[position].strip():
        body.append(_PYTHON_PROMPT.sub("", lines[position]))
        position += 1
    return _Span(Kind.CODE, body, "python"), position


def _ipython(lines: list[str], index: int) -> tuple[_Span, int] | None:
    if not _IPYTHON.match(lines[index]):
        return None
    body: list[str] = []
    position = index
    while position < len(lines) and lines[position].strip():
        body.append(_IPYTHON.sub("", lines[position]))
        position += 1
    return _Span(Kind.CODE, body, "python"), position


def _shell_transcript(lines: list[str], index: int) -> tuple[_Span, int] | None:
    if not _SHELL_PROMPT.match(lines[index]):
        return None
    body: list[str] = []
    position = index
    while position < len(lines) and lines[position].strip():
        body.append(
            _SHELL_PROMPT.sub(lambda m: m.group(0)[2:], lines[position])
        )
        position += 1
    return _Span(Kind.CODE, body, "shell"), position


def _diff(lines: list[str], index: int) -> tuple[_Span, int] | None:
    if not lines[index].startswith("--- ") or index + 1 >= len(lines):
        return None
    if not lines[index + 1].startswith("+++ "):
        return None
    body: list[str] = []
    position = index
    while position < len(lines) and (
        _DIFF_HEADER.match(lines[position])
        or lines[position][:1] in {"+", "-", " "}
    ):
        body.append(lines[position])
        position += 1
    return _Span(Kind.CODE, body, "diff"), position


def _shebang(lines: list[str], index: int) -> tuple[_Span, int] | None:
    if index != 0 or not _SHEBANG.match(lines[0]):
        return None
    return _Span(Kind.CODE, list(lines), _shebang_language(lines[0])), len(
        lines
    )


def _shebang_language(line: str) -> str | None:
    match = _SHEBANG.match(line)
    if not match:
        return None
    program = match.group(1).rsplit("/", 1)[-1]
    if program == "env" and match.group(2):
        program = match.group(2)
    return re.sub(r"[\d.]+$", "", program) or None


def _until(
    lines: list[str],
    start: int,
    is_closer: Callable[[str], bool],
    language: str | None,
) -> tuple[_Span, int]:
    body: list[str] = []
    position = start
    while position < len(lines) and not is_closer(lines[position]):
        body.append(lines[position])
        position += 1
    return _Span(Kind.CODE, body, language), min(position + 1, len(lines))


_CARRIERS: tuple[Carrier, ...] = (
    _shebang,
    _diff,
    _rst_directive,
    _rst_literal,
    _latex,
    _org,
    _asciidoc,
    _python_prompt,
    _ipython,
    _shell_transcript,
)


def _looks_like_dense_code(lines: list[str]) -> bool:
    """Unmarked code: mostly statement-like lines, indented, no sentences."""
    content = [line for line in lines if line.strip()]
    if len(content) < 3:
        return False
    if any(_SENTENCE_END.search(line) for line in content):
        return False
    statement = sum(1 for line in content if _CODE_LINE_END.search(line))
    indented = sum(1 for line in content if line[:1].isspace())
    return statement * 3 >= len(content) and indented * 3 >= len(content)
