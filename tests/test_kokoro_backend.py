from contextlib import contextmanager

import numpy as np
import pytest

from natural_tts.config import KOKORO_SAMPLE_RATE, KokoroSettings
from natural_tts.kokoro_backend import KokoroSynthesizer, SounddeviceSink


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
    def test_passes_chunks_voice_and_speed_to_the_pipeline(self):
        pipe = FakePipeline([FakeResult(FakeTensor([0.1]))])
        synth = KokoroSynthesizer(KokoroSettings("bf_emma", 1.1), pipe)
        list(synth.synthesize(["One.", "Two."]))
        text, kwargs = pipe.calls[0]
        assert text == "One.\nTwo."
        assert kwargs == {
            "voice": "bf_emma",
            "speed": 1.1,
            "split_pattern": r"\n+",
        }

    def test_yields_numpy_audio_and_skips_empty_results(self):
        pipe = FakePipeline(
            [
                FakeResult(FakeTensor([0.1, 0.2])),
                FakeResult(None),
                FakeResult(np.array([0.3], dtype=np.float32)),
            ]
        )
        synth = KokoroSynthesizer(KokoroSettings(), pipe)
        out = list(synth.synthesize(["x"]))
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
