"""Client for the natural-tts-mathcat helper (MathCAT in a subprocess).

One helper per client, started on first use and restarted after a crash
or a timeout. The protocol is line based: ``@Style Verbosity`` switches
preferences (sent only when they change), one MathML expression per line
yields one SSML line. ``parse_ssml`` turns that line into pieces of
``(pause_before_seconds, words)`` for the reader.
"""

from __future__ import annotations

import html
import os
import queue
import re
import subprocess
import threading
from collections.abc import Sequence
from types import TracebackType

DEFAULT_TIMEOUT = 2.0
# The helper starts in this style; a switch is sent only to leave it.
HELPER_DEFAULT_STYLE = ("ClearSpeak", "Medium")
_BREAK = re.compile(r"<break\s+time='(\d+(?:\.\d+)?)(ms|s)'\s*/>")
_CHARACTER = re.compile(r"<say-as interpret-as='characters'>(.*?)</say-as>")
_TAG = re.compile(r"<[^>]{1,200}>")


class MathCatUnavailable(RuntimeError):
    """The helper is missing, crashed, timed out or rejected the input."""


def parse_ssml(ssml: str) -> list[tuple[float, str]]:
    """Split MathCAT's SSML into ``(pause_before, words)`` pieces.

    ``<break>`` elements become the pause before the next piece; letters
    marked as characters are spelled, a capital as ``A.`` (what Kokoro's
    phonemizer needs to say the letter name); other tags are dropped and
    entities decoded.
    """
    pieces: list[tuple[float, str]] = []
    pause = 0.0
    for part in _BREAK.split(ssml):
        if part in {"ms", "s"}:
            continue
        if re.fullmatch(r"\d+(?:\.\d+)?", part or ""):
            value = float(part)
            pause = value / 1000 if _unit_is_ms(ssml, part) else value
            continue
        words = _words(part)
        if words:
            pieces.append((pause, words))
            pause = 0.0
    return pieces or [(0.0, "")] if not ssml.strip() else pieces


def _unit_is_ms(ssml: str, number: str) -> bool:
    match = re.search(rf"<break\s+time='{re.escape(number)}(ms|s)'", ssml)
    return match is None or match.group(1) == "ms"


def _words(fragment: str) -> str:
    def spell(match: re.Match[str]) -> str:
        letter = match.group(1).strip()
        return (
            f" {letter}. "
            if len(letter) == 1 and letter.isupper()
            else f" {letter} "
        )

    text = _CHARACTER.sub(spell, fragment)
    text = _TAG.sub(" ", text)
    return " ".join(html.unescape(text).split())


class MathCat:
    """Owns one helper process and speaks MathML through it."""

    def __init__(
        self,
        command: Sequence[str],
        *,
        language: str = "en",
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        """Remember how to start the helper; nothing runs until ``speak``."""
        self._command = tuple(command)
        self._language = language
        self._timeout = timeout
        self.process: subprocess.Popen[str] | None = None
        self._lines: queue.Queue[str | None] = queue.Queue()
        self._style: tuple[str, str] | None = None
        self.switches = 0

    @property
    def language(self) -> str:
        """The MathCAT rules language the helper runs with."""
        return self._language

    def __enter__(self) -> MathCat:
        """Use as a context manager; the process starts lazily."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Terminate the helper."""
        self.close()

    def close(self) -> None:
        """Stop the helper if it is running."""
        process, self.process = self.process, None
        self._style = None
        if process is None:
            return
        if process.stdin:
            process.stdin.close()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

    def speak(
        self,
        mathml: str,
        *,
        style: str = "ClearSpeak",
        verbosity: str = "Medium",
    ) -> list[tuple[float, str]]:
        """Return the pieces for one expression.

        Raises:
            MathCatUnavailable: helper missing, crashed, timed out, or an
                ``ERROR`` reply (the helper stays up in that last case).
        """
        self._ensure_started()
        if (style, verbosity) != self._style:
            reply = self._exchange(f"@{style} {verbosity}")
            if reply != "OK":
                raise MathCatUnavailable(f"style switch refused: {reply}")
            self._style = (style, verbosity)
            self.switches += 1
        reply = self._exchange(" ".join(mathml.split()))
        if reply.startswith("ERROR"):
            raise MathCatUnavailable(reply.removeprefix("ERROR").strip())
        return parse_ssml(reply)

    # -- process management --------------------------------------------------

    def _ensure_started(self) -> None:
        if self.process is not None and self.process.poll() is None:
            return
        self.process = None
        self._style = None
        self._lines = queue.Queue()
        env = dict(os.environ, MC_LANG=self._language)
        try:
            self.process = subprocess.Popen(
                self._command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
                env=env,
            )
        except FileNotFoundError as exc:
            raise MathCatUnavailable(
                f"helper not found: {self._command[0]}"
            ) from exc
        threading.Thread(
            target=self._pump, args=(self.process, self._lines), daemon=True
        ).start()
        self._style = HELPER_DEFAULT_STYLE

    @staticmethod
    def _pump(
        process: subprocess.Popen[str], lines: queue.Queue[str | None]
    ) -> None:
        assert process.stdout is not None
        for line in process.stdout:
            lines.put(line.rstrip("\n"))
        lines.put(None)

    def _exchange(self, line: str) -> str:
        process = self.process
        assert process is not None and process.stdin is not None
        try:
            process.stdin.write(line + "\n")
            process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            self._drop()
            raise MathCatUnavailable("helper exited") from exc
        try:
            reply = self._lines.get(timeout=self._timeout)
        except queue.Empty:
            self._drop(kill=True)
            raise MathCatUnavailable(
                f"helper timed out after {self._timeout:g} s"
            ) from None
        if reply is None:
            self._drop()
            raise MathCatUnavailable("helper exited")
        return reply

    def _drop(self, kill: bool = False) -> None:
        process, self.process = self.process, None
        self._style = None
        if process is not None and process.poll() is None:
            if kill:
                process.kill()
            process.wait()
