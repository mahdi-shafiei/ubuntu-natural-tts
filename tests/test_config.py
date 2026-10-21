import re
from pathlib import Path

import pytest

from natural_tts.config import (
    DEFAULT_SETTINGS_TOML,
    KokoroSettings,
    Paths,
    PiperSettings,
    Settings,
    SettingsError,
    load_settings,
)


def make_paths(tmp_path: Path) -> Paths:
    return Paths.from_env(
        {"XDG_RUNTIME_DIR": str(tmp_path / "run")}, home=tmp_path
    )


class TestPaths:
    def test_defaults_follow_xdg_layout(self, tmp_path):
        paths = make_paths(tmp_path)
        assert paths.data_dir == tmp_path / ".local/share/natural-tts"
        assert paths.config_dir == tmp_path / ".config/natural-tts"
        assert paths.venv == paths.data_dir / "venv"
        assert paths.voices_dir == paths.data_dir / "voices"
        assert paths.settings_file == paths.config_dir / "settings.toml"
        assert paths.kokoro_socket == tmp_path / "run/natural-tts/kokoro.sock"

    def test_xdg_overrides_are_honoured(self, tmp_path):
        env = {
            "XDG_DATA_HOME": str(tmp_path / "data"),
            "XDG_CONFIG_HOME": str(tmp_path / "cfg"),
            "XDG_RUNTIME_DIR": str(tmp_path / "run"),
        }
        paths = Paths.from_env(env, home=tmp_path)
        assert paths.data_dir == tmp_path / "data/natural-tts"
        assert paths.config_dir == tmp_path / "cfg/natural-tts"
        assert paths.systemd_user_dir == tmp_path / "cfg/systemd/user"
        assert paths.speechd_dir == tmp_path / "cfg/speech-dispatcher"

    def test_runtime_dir_falls_back_to_private_tmp(self, tmp_path):
        paths = Paths.from_env({}, home=tmp_path, uid=1234)
        assert paths.runtime_dir == Path("/tmp/natural-tts-1234")
        assert paths.kokoro_socket == Path("/tmp/natural-tts-1234/kokoro.sock")

    def test_venv_executables(self, tmp_path):
        paths = make_paths(tmp_path)
        assert paths.venv_python == paths.venv / "bin/python"
        assert paths.cli == paths.venv / "bin/natural-tts"


class TestLoadSettings:
    def test_missing_file_gives_defaults(self, tmp_path):
        settings = load_settings(make_paths(tmp_path))
        assert settings.piper == PiperSettings()
        assert settings.kokoro == KokoroSettings()

    def test_defaults(self):
        assert PiperSettings().voice == "en_US-lessac-high"
        assert PiperSettings().port == 5150
        assert KokoroSettings().voice == "af_heart"
        assert KokoroSettings().speed == 1.0

    def test_file_overrides_selected_values(self, tmp_path):
        paths = make_paths(tmp_path)
        paths.settings_file.parent.mkdir(parents=True)
        paths.settings_file.write_text(
            '[piper]\nvoice = "en_GB-cori-high"\nlength_scale = 1.2\n'
            '[kokoro]\nvoice = "bf_emma"\nspeed = 1.1\n'
        )
        settings = load_settings(paths)
        assert settings.piper.voice == "en_GB-cori-high"
        assert settings.piper.length_scale == 1.2
        assert settings.piper.port == 5150  # untouched default
        assert settings.kokoro.voice == "bf_emma"
        assert settings.kokoro.speed == 1.1

    def test_default_template_parses_to_defaults(self, tmp_path):
        paths = make_paths(tmp_path)
        paths.settings_file.parent.mkdir(parents=True)
        paths.settings_file.write_text(DEFAULT_SETTINGS_TOML)
        settings = load_settings(paths)
        assert settings == Settings(paths=paths)

    @pytest.mark.parametrize(
        ("toml", "message"),
        [
            ("[piper]\nvoyce = 'x'\n", "unknown key 'piper.voyce'"),
            ("[espeak]\n", "unknown section 'espeak'"),
            ("[piper]\nport = 'abc'\n", "piper.port must be int"),
            ("[piper]\nport = 80\n", "piper.port must be in 1024..65535"),
            ("[piper]\nlength_scale = 0\n", "piper.length_scale must be > 0"),
            ("[piper]\nvoice = 'lessac'\n", "piper.voice 'lessac'"),
            ("[kokoro]\nvoice = 'heart'\n", "kokoro.voice 'heart'"),
            ("[kokoro]\nvoice = 'xf_heart'\n", "kokoro.voice 'xf_heart'"),
            ("[kokoro]\nspeed = 9\n", "kokoro.speed must be in 0.5..2.0"),
            (
                "[piper]\nsentence_silence = -1\n",
                "piper.sentence_silence must be >= 0",
            ),
            ("not toml = = =", "invalid TOML"),
        ],
    )
    def test_invalid_files_are_rejected_with_clear_messages(
        self, tmp_path, toml, message
    ):
        paths = make_paths(tmp_path)
        paths.settings_file.parent.mkdir(parents=True)
        paths.settings_file.write_text(toml)
        with pytest.raises(SettingsError, match=re.escape(message)):
            load_settings(paths)

    def test_integers_are_accepted_for_float_fields(self, tmp_path):
        paths = make_paths(tmp_path)
        paths.settings_file.parent.mkdir(parents=True)
        paths.settings_file.write_text("[kokoro]\nspeed = 1\n")
        assert load_settings(paths).kokoro.speed == 1.0

    def test_booleans_are_not_numbers(self, tmp_path):
        paths = make_paths(tmp_path)
        paths.settings_file.parent.mkdir(parents=True)
        paths.settings_file.write_text("[piper]\nport = true\n")
        with pytest.raises(
            SettingsError, match=re.escape("piper.port must be int")
        ):
            load_settings(paths)


class TestDerivedValues:
    def test_kokoro_lang_code_comes_from_voice_prefix(self):
        assert KokoroSettings(voice="af_heart").lang_code == "a"
        assert KokoroSettings(voice="bm_george").lang_code == "b"

    def test_piper_model_path(self, tmp_path):
        settings = Settings(paths=make_paths(tmp_path))
        assert settings.piper_model == (
            settings.paths.voices_dir / "en_US-lessac-high.onnx"
        )
