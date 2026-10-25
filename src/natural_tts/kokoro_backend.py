"""Adapters binding the speech engine to Kokoro and sounddevice.

Heavy imports (torch, kokoro, sounddevice) happen only inside the factory
functions, so the rest of the package stays fast to import; numpy is
imported lazily for the same reason.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from typing import Any

from natural_tts.config import (
    KOKORO_REPO_ID,
    KOKORO_SAMPLE_RATE,
    KokoroSettings,
)
from natural_tts.engine import Samples
from natural_tts.segments import Segment

PipelineFactory = Callable[[str, str], Any]


def _kpipeline(lang_code: str, repo_id: str) -> Any:
    from kokoro import KPipeline

    return KPipeline(lang_code=lang_code, repo_id=repo_id)


def _to_numpy(audio: Any) -> Samples:
    # Kokoro yields torch tensors; tests may pass NumPy arrays directly.
    return audio.cpu().numpy() if hasattr(audio, "cpu") else audio


# Edge silence, after Kokoro-FastAPI's AudioNormalizer (remsky/Kokoro-FastAPI
# api/src/services/audio.py, b048d6d, 2026-10-23): every sample under
# -45 dBFS at either end is silence, 50 ms is kept before the first and
# after the last voiced sample, and all-silent audio is returned untouched.
# hexgrad/kokoro #365 arrives at the same -45 dBFS gate; the model's own
# repository does no trimming.
SILENCE_FLOOR = 10 ** (-45 / 20)
TRIM_MARGIN = KOKORO_SAMPLE_RATE * 50 // 1000


def trim_silence(audio: Samples) -> Samples:
    """Drop leading and trailing silence, keeping a 50 ms margin."""
    import numpy

    loud = numpy.flatnonzero(numpy.abs(audio) >= SILENCE_FLOOR)
    if len(loud) == 0:
        return audio
    start = max(0, int(loud[0]) - TRIM_MARGIN)
    end = min(len(audio), int(loud[-1]) + 1 + TRIM_MARGIN)
    return audio[start:end]


class KokoroSynthesizer:
    """``Synthesizer`` backed by a Kokoro ``KPipeline``."""

    def __init__(self, settings: KokoroSettings, pipeline: Any) -> None:
        """Wrap an existing pipeline (use ``load`` to create one)."""
        self._settings = settings
        self._pipeline = pipeline

    @classmethod
    def load(
        cls,
        settings: KokoroSettings,
        factory: PipelineFactory = _kpipeline,
    ) -> KokoroSynthesizer:
        """Load the Kokoro model for the configured voice's language."""
        return cls(settings, factory(settings.lang_code, KOKORO_REPO_ID))

    def synthesize(self, segments: Iterable[Segment]) -> Iterator[Samples]:
        """Yield audio per segment (Kokoro may split a segment further).

        Kokoro pads every utterance with 0.3-0.4 s of leading and 0.4-0.5 s
        of trailing silence (measured 2026-10-25); both are trimmed, as
        kokoro-onnx and Kokoro-FastAPI do, so that a segment's
        ``pause_before`` is the whole gap the listener hears. The first
        segment of a request gets no silence at all. A segment's rate and
        voice override the configured speed and voice.
        """
        import numpy

        first = True
        for segment in segments:
            if segment.pause_before > 0 and not first:
                yield numpy.zeros(
                    round(segment.pause_before * KOKORO_SAMPLE_RATE),
                    dtype="float32",
                )
            first = False
            results = self._pipeline(
                segment.text,
                voice=segment.voice or self._settings.voice,
                speed=self._settings.speed * segment.rate,
                split_pattern=r"\n+",
            )
            for result in results:
                if result.audio is not None:
                    yield trim_silence(_to_numpy(result.audio))

    def warm_up(self) -> None:
        """Run one tiny synthesis; the first call is much slower."""
        for _ in self.synthesize([Segment("Ready.")]):
            pass


class _SoundDeviceStream:
    def __init__(self, stream: Any) -> None:
        self._stream = stream

    def write(self, samples: Samples) -> None:
        self._stream.write(samples.astype("float32", copy=False).reshape(-1, 1))


class SounddeviceSink:
    """``AudioSink`` writing mono float32 audio through PortAudio."""

    def __init__(self, sd: Any) -> None:
        """Wrap the ``sounddevice`` module (injectable for tests)."""
        self._sd = sd

    @classmethod
    def default(cls) -> SounddeviceSink:
        """Create a sink using the real ``sounddevice`` module."""
        import sounddevice

        return cls(sounddevice)

    @contextmanager
    def open(self) -> Iterator[_SoundDeviceStream]:
        """Open an output stream on the default device."""
        with self._sd.OutputStream(
            samplerate=KOKORO_SAMPLE_RATE, channels=1, dtype="float32"
        ) as stream:
            yield _SoundDeviceStream(stream)
