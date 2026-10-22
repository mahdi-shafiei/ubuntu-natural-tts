"""The Kokoro read-aloud daemon: receives text over a socket and speaks it."""

from __future__ import annotations

import functools
import sys
from collections.abc import Callable, Iterator
from typing import Protocol

from natural_tts.config import (
    CHUNK_MAX_CHARS,
    FIRST_CHUNK_MIN_CHARS,
    KOKORO_SAMPLE_RATE,
    Settings,
)
from natural_tts.engine import (
    AudioSink,
    SpeechEngine,
    Synthesizer,
    report_to_stderr,
)
from natural_tts.ipc import STOP_MESSAGE, MessageServer
from natural_tts.reading import prepare
from natural_tts.segments import Segment
from natural_tts.text import chunk_text

# 0.1 s of audio per device write keeps "stop" near-instant.
SLICE_SAMPLES = KOKORO_SAMPLE_RATE // 10


class Engine(Protocol):
    """The part of ``SpeechEngine`` the server loop needs."""

    def submit(self, text: str) -> None:
        """Speak text, interrupting current speech."""
        ...

    def stop(self) -> None:
        """Stop speaking."""
        ...


class WarmSynthesizer(Synthesizer, Protocol):
    """A synthesizer that can be warmed up before serving."""

    def warm_up(self) -> None:
        """Run a throwaway synthesis."""
        ...


def plain_chunker(text: str) -> Iterator[Segment]:
    """Today's reading: one prose segment per text chunk, no rewriting."""
    for chunk in chunk_text(text, FIRST_CHUNK_MIN_CHARS, CHUNK_MAX_CHARS):
        yield Segment(chunk)


def announce(message: str) -> None:
    """Print a status line and flush it.

    Under systemd stdout is a pipe and therefore block-buffered; without the
    flush the line would not appear in the journal.
    """
    print(message, file=sys.stdout, flush=True)


def serve(
    server: MessageServer,
    engine: Engine,
    keep_running: Callable[[], bool] = lambda: True,
) -> None:
    """Dispatch incoming messages to ``engine`` until told to stop."""
    while keep_running():
        message = server.receive()
        if message == STOP_MESSAGE or not message.strip():
            engine.stop()
        else:
            engine.submit(message)


def run(
    settings: Settings,
    synthesizer: WarmSynthesizer,
    sink: AudioSink,
    *,
    on_ready: Callable[[str], None] = announce,
    keep_running: Callable[[], bool] = lambda: True,
) -> None:
    """Warm up, then listen on the daemon socket and speak what arrives.

    The socket only appears once the model is ready, so clients that connect
    too early get a clear "not running or still starting" error.
    """
    synthesizer.warm_up()
    engine = SpeechEngine(
        synthesizer,
        sink,
        chunker=functools.partial(prepare, settings=settings),
        slice_len=SLICE_SAMPLES,
        on_error=report_to_stderr,
    )
    with MessageServer(settings.paths.kokoro_socket) as server, engine:
        kokoro = settings.kokoro
        on_ready(
            f"natural-tts ready (voice {kokoro.voice}, speed {kokoro.speed})"
        )
        serve(server, engine, keep_running)
