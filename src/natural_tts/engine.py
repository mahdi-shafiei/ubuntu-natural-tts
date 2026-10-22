"""A cancellable, self-healing text-to-speech playback engine.

The engine is independent of Kokoro and of the audio library: it drives any
``Synthesizer`` and ``AudioSink``, which keeps it fully unit-testable.

Threading model:
    * one short-lived producer thread per request turns segments into
      audio; a lock ensures only one synthesis runs at a time;
    * one player thread owns the audio device (PortAudio must not be driven
      from several threads) and writes small slices so stop is near-instant;
    * a generation counter cancels stale work: every submit/stop bumps it,
      and anything tagged with an older generation is dropped.
"""

from __future__ import annotations

import itertools
import queue
import sys
import threading
from collections.abc import Callable, Iterable, Iterator
from contextlib import AbstractContextManager
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Protocol

from natural_tts.segments import Segment

# Audio samples: anything supporting len() and slicing (e.g. a NumPy array).
Samples = Any
ErrorReporter = Callable[[str], None]
# Turns a selection into segments; pulled lazily so speech starts early.
Chunker = Callable[[str], Iterator[Segment]]


class Synthesizer(Protocol):
    """Turns segments into audio, one or more sample buffers per segment."""

    def synthesize(self, segments: Iterable[Segment]) -> Iterable[Samples]:
        """Yield audio for each segment, lazily, in order."""
        ...


class AudioStream(Protocol):
    """An open audio output stream."""

    def write(self, samples: Samples) -> None:
        """Write samples, blocking until the device accepts them."""
        ...


class AudioSink(Protocol):
    """Opens audio output streams."""

    def open(self) -> AbstractContextManager[AudioStream]:
        """Open a stream; closing the context releases the device."""
        ...


def report_to_stderr(message: str) -> None:
    """Default error reporter (ends up in the systemd journal)."""
    print(message, file=sys.stderr, flush=True)


@dataclass(frozen=True)
class _Item:
    generation: int
    samples: Samples


class SpeechEngine:
    """Speaks text with interruption, stop and automatic error recovery."""

    def __init__(
        self,
        synthesizer: Synthesizer,
        sink: AudioSink,
        *,
        chunker: Chunker,
        slice_len: int,
        idle_close: float = 2.0,
        on_error: ErrorReporter = report_to_stderr,
        queue_size: int = 4,
    ) -> None:
        """Create an engine (call ``start`` or use it as a context manager).

        Args:
            synthesizer: Produces audio for segments.
            sink: Audio output.
            chunker: Turns submitted text into segments; only the first is
                taken before synthesis starts.
            slice_len: Samples per device write; bounds stop latency.
            idle_close: Seconds of silence before the device is released.
            on_error: Receives human-readable error messages.
            queue_size: Synthesized chunks buffered ahead of playback.
        """
        self._synth = synthesizer
        self._sink = sink
        self._chunker = chunker
        self._slice_len = slice_len
        self._idle_close = idle_close
        self._on_error = on_error
        self._queue: queue.Queue[_Item | None] = queue.Queue(queue_size)
        self._cond = threading.Condition()
        self._synth_lock = threading.Lock()
        self._generation = 0
        self._work = 0  # running producers + queued or playing items
        self._closed = False
        self._player: threading.Thread | None = None

    # -- lifecycle -----------------------------------------------------------

    def start(self) -> None:
        """Start the player thread (idempotent)."""
        if self._player is None:
            self._player = threading.Thread(
                target=self._player_loop, name="tts-player", daemon=True
            )
            self._player.start()

    def close(self) -> None:
        """Stop speech and shut the player down (idempotent)."""
        if self._closed:
            return
        self._closed = True
        self.stop()
        if self._player is not None:
            self._queue.put(None)
            self._player.join(timeout=5)

    def __enter__(self) -> SpeechEngine:
        """Start the engine."""
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Close the engine."""
        self.close()

    # -- public API ----------------------------------------------------------

    def submit(self, text: str) -> None:
        """Speak ``text``, interrupting anything currently playing.

        Raises:
            RuntimeError: if the engine has been closed.
        """
        if self._closed:
            raise RuntimeError("SpeechEngine is closed")
        segments = self._chunker(text)
        first = next(segments, None)
        with self._cond:
            generation = self._cancel_locked()
            if first is None:
                return
            self._work += 1
        threading.Thread(
            target=self._produce,
            args=(itertools.chain([first], segments), generation),
            name="tts-producer",
            daemon=True,
        ).start()

    def stop(self) -> None:
        """Stop speaking immediately and discard pending audio."""
        with self._cond:
            self._cancel_locked()

    def wait_idle(self, timeout: float | None = None) -> bool:
        """Wait until nothing is being synthesized or played.

        Returns:
            True if idle, False if ``timeout`` expired first.
        """
        with self._cond:
            return self._cond.wait_for(lambda: self._work == 0, timeout)

    # -- internals -----------------------------------------------------------

    def _cancel_locked(self) -> int:
        self._generation += 1
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break
            if item is None:  # keep a pending shutdown request
                self._queue.put_nowait(None)
                break
            self._work -= 1
        self._cond.notify_all()
        return self._generation

    def _is_current(self, generation: int) -> bool:
        return generation == self._generation

    def _finish_one(self) -> None:
        with self._cond:
            self._work -= 1
            self._cond.notify_all()

    def _produce(self, segments: Iterable[Segment], generation: int) -> None:
        try:
            with self._synth_lock:
                for samples in self._synth.synthesize(segments):
                    if not self._is_current(generation):
                        return
                    with self._cond:
                        if not self._is_current(generation):
                            return
                        self._work += 1
                    self._queue.put(_Item(generation, samples))
        except Exception as exc:
            self._on_error(f"synthesis failed: {exc}")
        finally:
            self._finish_one()

    def _player_loop(self) -> None:
        item = self._queue.get()
        while item is not None:
            if self._is_current(item.generation):
                item = self._play_session(item)
            else:
                self._finish_one()
                item = self._queue.get()

    def _play_session(self, first: _Item) -> _Item | None:
        """Play ``first`` and following items on one stream until idle.

        Returns:
            The next queue item to handle (None means shut down).
        """
        item: _Item | None = first
        try:
            with self._sink.open() as stream:
                while item is not None:
                    try:
                        self._write(stream, item)
                    finally:
                        item = None
                        self._finish_one()
                    try:
                        item = self._queue.get(timeout=self._idle_close)
                    except queue.Empty:
                        break
                    if item is None:
                        return None
        except Exception as exc:
            self._on_error(f"audio output failed: {exc}")
            if item is not None:
                self._finish_one()
        return self._queue.get()

    def _write(self, stream: AudioStream, item: _Item) -> None:
        samples = item.samples
        for start in range(0, len(samples), self._slice_len):
            if not self._is_current(item.generation):
                return
            stream.write(samples[start : start + self._slice_len])
