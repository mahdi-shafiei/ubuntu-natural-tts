"""Playing synthesized WAV audio."""

from __future__ import annotations

from collections.abc import Callable

from natural_tts.system import Runner, run

WavPlayer = Callable[[bytes], None]

# aplay goes through ALSA's default device, which pipewire-alsa routes to
# PipeWire on Ubuntu desktops.
APLAY_COMMAND = ("aplay", "-q", "-")


class AudioError(RuntimeError):
    """Raised when audio cannot be played."""


def play_wav(wav: bytes, runner: Runner = run) -> None:
    """Play WAV data, blocking until playback ends.

    Raises:
        AudioError: if the player fails.
    """
    result = runner(APLAY_COMMAND, stdin=wav)
    if not result.ok:
        raise AudioError(result.describe(APLAY_COMMAND))
