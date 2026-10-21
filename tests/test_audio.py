import pytest

from natural_tts.audio import APLAY_COMMAND, AudioError, play_wav
from natural_tts.system import Result


class FakeRunner:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def __call__(self, argv, *, stdin=None, timeout=None):
        self.calls.append((tuple(argv), stdin))
        return self.result


def test_play_wav_pipes_to_aplay_reading_stdin():
    runner = FakeRunner(Result(0, b"", b""))
    play_wav(b"RIFF", runner=runner)
    assert runner.calls == [(APLAY_COMMAND, b"RIFF")]
    assert APLAY_COMMAND[-1] == "-"


def test_play_failure_raises_with_reason():
    runner = FakeRunner(Result(1, b"", b"audio open error: Device busy"))
    with pytest.raises(AudioError, match="Device busy"):
        play_wav(b"RIFF", runner=runner)
