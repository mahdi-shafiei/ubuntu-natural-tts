from contextlib import contextmanager

import numpy as np
import pytest

from natural_tts.config import KOKORO_SAMPLE_RATE, KokoroSettings
from natural_tts.kokoro_backend import KokoroSynthesizer, SounddeviceSink
from natural_tts.segments import Segment


class FakeResult:
    def __init__(self, audio):
        self.audio = audio


class FakeTensor:
    """Mimics a torch tensor: .cpu().numpy()."""

    def __init__(self, values):
        self.values = np.asarray(values, dtype=np.float32)

    def cpu(self):
        return self

    def numpy(self):
        return self.values


class FakePipeline:
    def __init__(self, results):
        self.results = results
        self.calls = []

    def __call__(self, text, **kwargs):
        self.calls.append((text, kwargs))
        return iter(self.results)


class TestKokoroSynthesizer:
    def test_each_segment_is_one_pipeline_call_with_voice_and_speed(self):
        pipe = FakePipeline([FakeResult(FakeTensor([0.1]))])
        synth = KokoroSynthesizer(KokoroSettings("bf_emma", 1.1), pipe)
        list(synth.synthesize([Segment("One."), Segment("Two.")]))
        assert [text for text, _ in pipe.calls] == ["One.", "Two."]
        assert pipe.calls[0][1] == {
            "voice": "bf_emma",
            "speed": 1.1,
            "split_pattern": r"\n+",
        }

    def test_segment_rate_and_voice_override_the_settings(self):
        pipe = FakePipeline([FakeResult(FakeTensor([0.1]))])
        synth = KokoroSynthesizer(KokoroSettings("af_heart", 1.0), pipe)
        list(synth.synthesize([Segment("Code.", rate=0.9, voice="am_puck")]))
        _, kwargs = pipe.calls[0]
        assert kwargs["voice"] == "am_puck"
        assert kwargs["speed"] == pytest.approx(0.9)

    def test_pause_before_is_the_whole_gap_between_segments(self):
        # 0.1 s of near-silence on both edges, then voice, then silence
        # again: the synthesizer trims the edges so the requested pause is
        # the entire gap the listener hears.
        voiced = np.full(2_400, 0.2, dtype=np.float32)
        edge = np.full(2_400, 0.001, dtype=np.float32)
        pipe = FakePipeline([FakeResult(np.concatenate([edge, voiced, edge]))])
        synth = KokoroSynthesizer(KokoroSettings(), pipe)
        out = list(
            synth.synthesize([Segment("a"), Segment("b", pause_before=0.5)])
        )
        # 50 ms margins (1200 samples) stay on both sides of the voice.
        assert [len(o) for o in out] == [4_800, 12_000, 4_800]
        assert not out[1].any() and out[0][1_200:-1_200].all()

    def test_no_silence_before_the_first_segment(self):
        pipe = FakePipeline([FakeResult(FakeTensor([0.1]))])
        synth = KokoroSynthesizer(KokoroSettings(), pipe)
        out = list(synth.synthesize([Segment("x", pause_before=0.5)]))
        assert len(out) == 1 and out[0].tolist() == pytest.approx([0.1])

    def test_trimming_keeps_a_short_margin_and_all_silent_audio(self):
        quiet = np.full(4_800, 0.001, dtype=np.float32)
        loud = np.full(240, 0.5, dtype=np.float32)
        pipe = FakePipeline([FakeResult(np.concatenate([quiet, loud, quiet]))])
        synth = KokoroSynthesizer(KokoroSettings(), pipe)
        (out,) = synth.synthesize([Segment("x")])
        # 50 ms (1200 samples) kept on each side of the 10 ms of voice.
        assert len(out) == 1_200 + 240 + 1_200
        pipe = FakePipeline([FakeResult(np.zeros(1_000, dtype=np.float32))])
        (out,) = KokoroSynthesizer(KokoroSettings(), pipe).synthesize(
            [Segment("x")]
        )
        assert len(out) == 1_000

    def test_yields_numpy_audio_and_skips_empty_results(self):
        pipe = FakePipeline(
            [
                FakeResult(FakeTensor([0.1, 0.2])),
                FakeResult(None),
                FakeResult(np.array([0.3], dtype=np.float32)),
            ]
        )
        synth = KokoroSynthesizer(KokoroSettings(), pipe)
        out = list(synth.synthesize([Segment("x")]))
        assert [a.tolist() for a in out] == [
            pytest.approx([0.1, 0.2]),
            pytest.approx([0.3]),
        ]

    def test_warm_up_runs_one_synthesis(self):
        pipe = FakePipeline([FakeResult(FakeTensor([0.0]))])
        KokoroSynthesizer(KokoroSettings(), pipe).warm_up()
        assert len(pipe.calls) == 1

    def test_load_builds_pipeline_for_voice_language(self):
        created: dict[str, str] = {}

        def factory(lang_code, repo_id):
            created.update(lang_code=lang_code, repo_id=repo_id)
            return FakePipeline([])

        KokoroSynthesizer.load(KokoroSettings("bm_george"), factory)
        assert created == {"lang_code": "b", "repo_id": "hexgrad/Kokoro-82M"}


class FakeSd:
    def __init__(self):
        self.opened = []
        self.written = []

    @contextmanager
    def OutputStream(self, **kwargs):
        self.opened.append(kwargs)
        yield self

    def write(self, data):
        self.written.append(data)


class TestSounddeviceSink:
    def test_opens_mono_float32_stream_at_kokoro_rate(self):
        sd = FakeSd()
        with SounddeviceSink(sd).open():
            pass
        assert sd.opened == [
            {
                "samplerate": KOKORO_SAMPLE_RATE,
                "channels": 1,
                "dtype": "float32",
            }
        ]

    def test_writes_column_shaped_float32(self):
        sd = FakeSd()
        with SounddeviceSink(sd).open() as stream:
            stream.write(np.array([0.5, -0.5], dtype=np.float64))
        (data,) = sd.written
        assert data.shape == (2, 1) and data.dtype == np.float32


class TestRealFactories:
    def test_kpipeline_factory_imports_kokoro_lazily(self, monkeypatch):
        import sys
        import types

        from natural_tts.kokoro_backend import _kpipeline

        fake = types.ModuleType("kokoro")
        fake.KPipeline = lambda **kw: ("pipeline", kw)  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "kokoro", fake)
        assert _kpipeline("a", "repo") == (
            "pipeline",
            {"lang_code": "a", "repo_id": "repo"},
        )

    def test_default_sink_uses_sounddevice(self, monkeypatch):
        import sys
        import types

        fake = types.ModuleType("sounddevice")
        monkeypatch.setitem(sys.modules, "sounddevice", fake)
        assert SounddeviceSink.default()._sd is fake
