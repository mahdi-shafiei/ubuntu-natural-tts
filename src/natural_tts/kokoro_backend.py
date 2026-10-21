"""Adapters binding the speech engine to Kokoro and sounddevice.

Heavy imports (torch, kokoro, sounddevice) happen only inside the factory
functions, so the rest of the package stays fast to import.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from typing import Any

from natural_tts.config import (
    KOKORO_REPO_ID,
    KOKORO_SAMPLE_RATE,
    KokoroSettings,
)
from natural_tts.engine import Samples

PipelineFactory = Callable[[str, str], Any]


def _kpipeline(lang_code: str, repo_id: str) -> Any:
    from kokoro import KPipeline

    return KPipeline(lang_code=lang_code, repo_id=repo_id)


def _to_numpy(audio: Any) -> Samples:
    # Kokoro yields torch tensors; tests may pass NumPy arrays directly.
    return audio.cpu().numpy() if hasattr(audio, "cpu") else audio


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

    def synthesize(self, chunks: Sequence[str]) -> Iterator[Samples]:
        """Yield one audio buffer per chunk (Kokoro may split further)."""
        results = self._pipeline(
            "\n".join(chunks),
            voice=self._settings.voice,
            speed=self._settings.speed,
            split_pattern=r"\n+",
        )
        for result in results:
            if result.audio is not None:
                yield _to_numpy(result.audio)

    def warm_up(self) -> None:
        """Run one tiny synthesis; the first call is much slower."""
        for _ in self.synthesize(["Ready."]):
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
