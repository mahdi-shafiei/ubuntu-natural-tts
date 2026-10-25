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


# MathCAT's own rendering for voices without SSML (its default, TTS=None;
# NSoiffer/MathCAT src/tts.rs get_string_none, bca65401, 2026-10-24): a
# break of at most 50 ms is dropped, at most 250 ms is a comma, anything
# longer a semicolon, attached to the preceding word; never a full stop,
# which the author found "didn't seem to reliably generate pauses". The
# helper is asked for SSML so letters can be spelled for the engine; the
# same thresholds are applied here to the break times it sends (MathCAT's
# named pauses are 200 / 400 / 800 ms and its "auto" pauses multiples of
# 128 ms, unscaled on this path). One engine call per formula: a call per
# piece would add the engine's edge silence each time.
MIN_BREAK = 0.05
COMMA_BREAK = 0.25


def sentence(pieces: list[tuple[float, str]]) -> str:
    """Join spoken pieces into one run of words, breaks as MathCAT renders."""
    words = ""
    for pause, piece in pieces:
        if not words:
            words = piece
        elif pause <= MIN_BREAK:
            words += " " + piece
        elif pause <= COMMA_BREAK:
            words += ", " + piece
        else:
            words += "; " + piece
    return words


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
        # Preferences in the order they were set; replayed on every start.
        self._preferences: dict[str, str] = {}
        self._sent: dict[str, str] = {}
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
        self._sent = {}
        if process is None:
            return
        if process.stdin:
            process.stdin.close()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

    def set(self, name: str, value: str) -> None:
        """Set a MathCAT preference, sent before the next expression.

        Preferences survive a helper restart: the client replays them.
        """
        self._preferences[name] = value

    def speak(
        self,
        mathml: str,
        *,
        style: str = "ClearSpeak",
        verbosity: str = "Medium",
    ) -> list[tuple[float, str]]:
        """Return the pieces for one expression.

        Raises:
            MathCatUnavailable: helper missing, crashed, timed out, a refused
                preference, or an ``ERROR`` reply (the helper stays up then).
        """
        self._ensure_started()
        self.set("SpeechStyle", style)
        self.set("Verbosity", verbosity)
        for name, value in self._preferences.items():
            if self._sent.get(name) == value:
                continue
            reply = self._exchange(f"@{name}={value}")
            if reply != "OK":
                raise MathCatUnavailable(f"preference refused: {reply}")
            self._sent[name] = value
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
        self._sent = {}
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
        self._sent = {}
        if process is not None and process.poll() is None:
            if kill:
                process.kill()
            process.wait()
