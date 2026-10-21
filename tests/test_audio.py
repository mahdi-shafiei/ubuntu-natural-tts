import pytest

from natural_tts.audio import APLAY_COMMAND, AudioError, play_wav
from natural_tts.system import Result
from tests.fakes import RecordingRunner


def test_play_wav_pipes_to_aplay_reading_stdin():
    runner = RecordingRunner()
    play_wav(b"RIFF", runner=runner)
    assert [(c.argv, c.stdin) for c in runner.calls] == [
        (APLAY_COMMAND, b"RIFF")
    ]
    assert APLAY_COMMAND[-1] == "-"


def test_play_failure_raises_with_reason():
    busy = Result(1, b"", b"audio open error: Device busy")
    runner = RecordingRunner(lambda argv: busy)
    with pytest.raises(AudioError, match="Device busy"):
        play_wav(b"RIFF", runner=runner)
