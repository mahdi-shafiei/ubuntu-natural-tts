"""The Kokoro read-aloud daemon: receives text over a socket and speaks it."""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator
from typing import Protocol

from natural_tts.config import KOKORO_SAMPLE_RATE, Settings
from natural_tts.engine import (
    AudioSink,
    SpeechEngine,
    Synthesizer,
    report_to_stderr,
)
from natural_tts.ipc import STOP_MESSAGE, MessageServer, unframe
from natural_tts.reading import chunker_for, plain_segments
from natural_tts.segments import Segment

# 0.1 s of audio per device write keeps "stop" near-instant.
SLICE_SAMPLES = KOKORO_SAMPLE_RATE // 10


class Engine(Protocol):
    """The part of ``SpeechEngine`` the server loop needs."""

    def submit(self, text: str, format: str | None = None) -> None:
        """Speak text (or HTML), interrupting current speech."""
        ...

    def stop(self) -> None:
        """Stop speaking."""
        ...


class WarmSynthesizer(Synthesizer, Protocol):
    """A synthesizer that can be warmed up before serving."""

    def warm_up(self) -> None:
        """Run a throwaway synthesis."""
        ...


def plain_chunker(text: str, format: str | None = None) -> Iterator[Segment]:
    """Today's reading: one prose segment per text chunk, no rewriting."""
    return plain_segments(text)


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
        body, format = unframe(server.receive())
        if body == STOP_MESSAGE or not body.strip():
            engine.stop()
        else:
            engine.submit(body, format)


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
    chunker = chunker_for(settings)
    engine = SpeechEngine(
        synthesizer,
        sink,
        chunker=chunker,
        slice_len=SLICE_SAMPLES,
        on_error=report_to_stderr,
    )
    with (
        MessageServer(settings.paths.kokoro_socket) as server,
        chunker,
        engine,
    ):
        kokoro = settings.kokoro
        on_ready(
            f"natural-tts ready (voice {kokoro.voice}, speed {kokoro.speed})"
        )
        serve(server, engine, keep_running)
