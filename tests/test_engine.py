import threading
import time
from contextlib import contextmanager

import pytest

from natural_tts.engine import SpeechEngine
from natural_tts.segments import Segment
from natural_tts.text import chunk_text

SLICE = 10  # samples per write; tiny so tests can interrupt mid-chunk


def chunker(text: str):
    """The daemon's default shape: one prose segment per text chunk."""
    return (Segment(chunk) for chunk in chunk_text(text, 10, 40))


class FakeSynth:
    """Yields one 'audio' list per segment: its characters as ints."""

    def __init__(self, delay=0.0, fail_on=None):
        self.delay = delay
        self.fail_on = fail_on
        self.calls: list[list[str]] = []
        self.active = 0
        self.max_active = 0
        self._lock = threading.Lock()

    def synthesize(self, segments):
        with self._lock:
            call: list[str] = []
            self.calls.append(call)
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            for segment in segments:
                call.append(segment.text)
                time.sleep(self.delay)
                if self.fail_on and self.fail_on in segment.text:
                    raise RuntimeError("synth exploded")
                yield [ord(c) for c in segment.text]
        finally:
            with self._lock:
                self.active -= 1


class FakeSink:
    """Records samples written; each write takes write_delay seconds."""

    def __init__(self, write_delay=0.0, fail_opens=0, fail_writes=0):
        self.write_delay = write_delay
        self.fail_opens = fail_opens
        self.fail_writes = fail_writes
        self.opens = 0
        self.written: list[int] = []

    @contextmanager
    def open(self):
        self.opens += 1
        if self.fail_opens:
            self.fail_opens -= 1
            raise OSError("no audio device")
        yield self

    def write(self, samples):
        if self.fail_writes:
            self.fail_writes -= 1
            raise OSError("device unplugged")
        time.sleep(self.write_delay)
        self.written.extend(samples)


def text_of(samples):
    return "".join(map(chr, samples))


@pytest.fixture
def errors():
    return []


def make_engine(synth, sink, errors, idle_close=0.05):
    return SpeechEngine(
        synth,
        sink,
        chunker=chunker,
        slice_len=SLICE,
        idle_close=idle_close,
        on_error=errors.append,
    )


class TestSpeechEngine:
    def test_plays_all_chunks_in_order(self, errors):
        synth, sink = FakeSynth(), FakeSink()
        with make_engine(synth, sink, errors) as engine:
            engine.submit("First one here. Second sentence. Third.")
            assert engine.wait_idle(5)
        assert text_of(sink.written).replace(" ", "") == (
            "Firstonehere.Secondsentence.Third."
        )
        assert errors == []

    def test_text_is_chunked_with_configured_limits(self, errors):
        synth = FakeSynth()
        with make_engine(synth, FakeSink(), errors) as engine:
            engine.submit("A. " * 30)
            engine.wait_idle(5)
        (chunks,) = synth.calls
        assert len(chunks) > 1 and all(len(c) <= 40 for c in chunks)

    def test_segments_are_pulled_lazily_after_the_first(self, errors):
        # A long selection must not be fully prepared before speech
        # starts: only the first segment is taken synchronously.
        pulled = []

        def lazy(text):
            for i in range(3):
                pulled.append(i)
                yield Segment(f"part {i}.")

        synth, sink = FakeSynth(), FakeSink()
        engine = SpeechEngine(
            synth, sink, chunker=lazy, slice_len=SLICE, on_error=errors.append
        )
        with engine:
            engine.submit("anything")
            assert pulled == [0]
            assert engine.wait_idle(5)
        assert pulled == [0, 1, 2]
        assert text_of(sink.written) == "part 0.part 1.part 2."

    def test_blank_text_is_ignored(self, errors):
        synth, sink = FakeSynth(), FakeSink()
        with make_engine(synth, sink, errors) as engine:
            engine.submit("  \n ")
            assert engine.wait_idle(1)
        assert synth.calls == [] and sink.written == []

    def test_stop_cuts_speech_mid_chunk(self, errors):
        sink = FakeSink(write_delay=0.02)
        with make_engine(FakeSynth(), sink, errors) as engine:
            engine.submit("x" * 39 + ". " + "y" * 39 + ".")
            time.sleep(0.05)
            engine.stop()
            assert engine.wait_idle(2)
            played = len(sink.written)
            time.sleep(0.1)
        assert 0 < played < 60
        assert len(sink.written) == played  # nothing after stop

    def test_new_text_interrupts_current_speech(self, errors):
        sink = FakeSink(write_delay=0.02)
        with make_engine(FakeSynth(), sink, errors) as engine:
            engine.submit("a" * 39 + ". " + "a" * 39 + ".")
            time.sleep(0.05)
            engine.submit("Second.")
            assert engine.wait_idle(5)
        played = text_of(sink.written)
        assert played.endswith("Second.")
        assert played.count("a") < 78

    def test_only_one_synthesis_runs_at_a_time(self, errors):
        synth = FakeSynth(delay=0.02)
        with make_engine(synth, FakeSink(), errors) as engine:
            for i in range(5):
                engine.submit(f"Message number {i}. " * 3)
                time.sleep(0.005)
            assert engine.wait_idle(5)
        assert synth.max_active == 1

    def test_audio_device_failure_is_reported_and_recovered(self, errors):
        # Regression: a device error used to kill the player thread
        # silently, leaving the daemon running but mute.
        sink = FakeSink(fail_opens=1)
        with make_engine(FakeSynth(), sink, errors) as engine:
            engine.submit("Lost to the error.")
            assert engine.wait_idle(5)
            engine.submit("Heard after recovery.")
            assert engine.wait_idle(5)
        assert any("no audio device" in e for e in errors)
        assert text_of(sink.written) == "Heard after recovery."

    def test_write_failure_mid_stream_is_recovered(self, errors):
        sink = FakeSink(fail_writes=1)
        with make_engine(FakeSynth(), sink, errors) as engine:
            engine.submit("Broken write.")
            engine.wait_idle(5)
            engine.submit("Works again.")
            assert engine.wait_idle(5)
        assert any("device unplugged" in e for e in errors)
        assert text_of(sink.written).endswith("Works again.")

    def test_synthesis_failure_is_reported_and_recovered(self, errors):
        synth = FakeSynth(fail_on="BOOM")
        sink = FakeSink()
        with make_engine(synth, sink, errors) as engine:
            engine.submit("BOOM.")
            assert engine.wait_idle(5)
            engine.submit("Fine now.")
            assert engine.wait_idle(5)
        assert any("synth exploded" in e for e in errors)
        assert text_of(sink.written) == "Fine now."

    def test_stream_is_closed_after_idle_and_reopened(self, errors):
        sink = FakeSink()
        with make_engine(FakeSynth(), sink, errors, idle_close=0.05) as engine:
            engine.submit("One.")
            engine.wait_idle(5)
            time.sleep(0.2)
            engine.submit("Two.")
            engine.wait_idle(5)
        assert sink.opens == 2

    def test_consecutive_chunks_share_one_stream(self, errors):
        sink = FakeSink()
        with make_engine(FakeSynth(), sink, errors, idle_close=1) as engine:
            engine.submit(
                "Sentence one is here. Sentence two is here. "
                "Sentence three is here."
            )
            engine.wait_idle(5)
        assert sink.opens == 1

    def test_close_is_idempotent_and_rejects_new_work(self, errors):
        engine = make_engine(FakeSynth(), FakeSink(), errors)
        engine.start()
        engine.close()
        engine.close()
        with pytest.raises(RuntimeError, match="closed"):
            engine.submit("late")

    def test_wait_idle_times_out_while_busy(self, errors):
        sink = FakeSink(write_delay=0.05)
        with make_engine(FakeSynth(), sink, errors) as engine:
            engine.submit("z" * 39 + ".")
            assert engine.wait_idle(0.01) is False
            engine.stop()


class TestLifecycle:
    def test_default_error_reporter_writes_to_stderr(self, capsys):
        from natural_tts.engine import report_to_stderr

        report_to_stderr("audio output failed: x")
        assert capsys.readouterr().err == "audio output failed: x\n"

    def test_close_without_start(self, errors):
        engine = make_engine(FakeSynth(), FakeSink(), errors)
        engine.close()  # must not hang or raise

    def test_start_is_idempotent(self, errors):
        engine = make_engine(FakeSynth(), FakeSink(), errors)
        engine.start()
        engine.start()
        engine.close()

    def test_close_while_speaking_returns_promptly(self, errors):
        sink = FakeSink(write_delay=0.02)
        engine = make_engine(FakeSynth(), sink, errors, idle_close=5)
        engine.start()
        engine.submit("q" * 39 + ". " + "r" * 39 + ".")
        time.sleep(0.05)
        started = time.monotonic()
        engine.close()
        assert time.monotonic() - started < 2
        assert errors == []
