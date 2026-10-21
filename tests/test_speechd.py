import pytest

from natural_tts.config import SPEECHD_MODULE, PiperSettings
from natural_tts.speechd import (
    DEFAULT_MARKER,
    install_speechd,
    remove_default_module,
    render_module_conf,
    set_default_module,
    uninstall_speechd,
)
from tests.fakes import make_settings as base_settings

CLI = "/home/u/.local/share/natural-tts/venv/bin/natural-tts"
SYSTEM_CONF = (
    "# system config\n"
    "LogLevel 3\n"
    '#AddModule "espeak-ng" "sd_espeak-ng" "espeak-ng.conf"\n'
    "# DefaultModule espeak-ng\n"
    'Include "clients/*.conf"\n'
)


def make_settings(tmp_path, voice="en_US-lessac-high"):
    return base_settings(tmp_path, piper=PiperSettings(voice=voice))


class TestRenderModuleConf:
    def test_synth_command_quotes_data_and_passes_rate(self, tmp_path):
        conf = render_module_conf(make_settings(tmp_path), CLI)
        assert (
            f"GenericExecuteSynth \"printf %s \\'$DATA\\' | {CLI} "
            'piper-speak $RATE"' in conf
        )

    def test_declares_dependency_on_the_cli(self, tmp_path):
        conf = render_module_conf(make_settings(tmp_path), CLI)
        assert f'GenericCmdDependency "{CLI}"' in conf

    def test_utf8_for_voice_language_and_english(self, tmp_path):
        conf = render_module_conf(
            make_settings(tmp_path, "de_DE-thorsten-high"), CLI
        )
        for code in ("de", "de-DE", "en", "en-US", "en-GB"):
            assert f'GenericLanguage "{code}" "{code}" "utf-8"' in conf
        # Piper has one voice; register it for every voice type so apps that
        # ask for e.g. MALE1 don't fall back to espeak.
        for kind in ("MALE1", "FEMALE1", "CHILD_MALE"):
            assert f'AddVoice "de" "{kind}" "de_DE-thorsten-high"' in conf

    @pytest.mark.parametrize(
        "code",
        ["fr", "de", "es", "it", "pt", "ru", "zh", "ja", "ar", "fa", "hi", "c"],
    )
    def test_common_languages_are_declared_utf8(self, tmp_path, code):
        # Undeclared languages are recoded to ISO-8859-1, which turns
        # dashes and non-Latin scripts into "?" (e.g. Firefox reading a
        # French page with an English voice).
        conf = render_module_conf(make_settings(tmp_path), CLI)
        assert f'GenericLanguage "{code}" "{code}" "utf-8"' in conf

    def test_language_lines_are_not_duplicated(self, tmp_path):
        conf = render_module_conf(make_settings(tmp_path), CLI)
        assert conf.count('GenericLanguage "en-US"') == 1

    def test_no_unsupported_charset_option(self, tmp_path):
        # GenericDefaultCharset does not exist in Ubuntu 24.04's
        # speech-dispatcher (0.12.0~rc2) and would break the module there.
        conf = render_module_conf(make_settings(tmp_path), CLI)
        assert "GenericDefaultCharset" not in conf

    @pytest.mark.parametrize("bad", ["/home/a b/cli", "/x'y/cli", '/x"y'])
    def test_rejects_paths_that_cannot_be_quoted_safely(self, tmp_path, bad):
        with pytest.raises(ValueError, match="cannot contain"):
            render_module_conf(make_settings(tmp_path), bad)


class TestDefaultModule:
    def test_appends_marked_default(self):
        text, warnings = set_default_module(SYSTEM_CONF)
        assert text.endswith(
            f"{DEFAULT_MARKER}\nDefaultModule {SPEECHD_MODULE}\n"
        )
        assert warnings == []

    def test_is_idempotent(self):
        once, _ = set_default_module(SYSTEM_CONF)
        twice, _ = set_default_module(once)
        assert once == twice

    def test_replaces_other_active_default(self):
        text, _ = set_default_module(SYSTEM_CONF + "DefaultModule espeak-ng\n")
        active = [
            line
            for line in text.splitlines()
            if line.startswith("DefaultModule")
        ]
        assert active == [f"DefaultModule {SPEECHD_MODULE}"]
        assert "# DefaultModule espeak-ng" in text  # comments untouched

    def test_warns_about_addmodule_lines(self):
        conf = SYSTEM_CONF + 'AddModule "espeak-ng" "sd_espeak-ng" "x.conf"\n'
        _, warnings = set_default_module(conf)
        assert len(warnings) == 1 and "AddModule" in warnings[0]
        assert "auto-detection" in warnings[0]

    def test_remove_restores_original(self):
        text, _ = set_default_module(SYSTEM_CONF)
        assert remove_default_module(text) == SYSTEM_CONF

    def test_handles_missing_trailing_newline(self):
        text, _ = set_default_module("LogLevel 3")
        assert text == (
            f"LogLevel 3\n{DEFAULT_MARKER}\nDefaultModule {SPEECHD_MODULE}\n"
        )


class TestInstall:
    def test_installs_module_and_user_config(self, tmp_path):
        settings = make_settings(tmp_path)
        system = tmp_path / "etc/speechd.conf"
        system.parent.mkdir()
        system.write_text(SYSTEM_CONF)
        warnings = install_speechd(settings, CLI, system_conf=system)
        sd = settings.paths.speechd_dir
        assert warnings == []
        module = sd / f"modules/{SPEECHD_MODULE}.conf"
        assert module.name == "piper-generic.conf"  # auto-detected name
        assert "piper-speak" in module.read_text()
        user = (sd / "speechd.conf").read_text()
        assert user.startswith(SYSTEM_CONF)  # full copy: it replaces /etc
        assert f"DefaultModule {SPEECHD_MODULE}" in user

    def test_keeps_existing_user_config(self, tmp_path):
        settings = make_settings(tmp_path)
        sd = settings.paths.speechd_dir
        sd.mkdir(parents=True)
        (sd / "speechd.conf").write_text("LogLevel 5\n")
        install_speechd(settings, CLI, system_conf=tmp_path / "missing")
        assert (sd / "speechd.conf").read_text().startswith("LogLevel 5\n")

    def test_missing_system_config_is_an_error(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            install_speechd(
                make_settings(tmp_path), CLI, system_conf=tmp_path / "missing"
            )

    def test_uninstall_reverts_only_our_changes(self, tmp_path):
        settings = make_settings(tmp_path)
        sd = settings.paths.speechd_dir
        sd.mkdir(parents=True)
        (sd / "speechd.conf").write_text("LogLevel 5\n")
        install_speechd(settings, CLI, system_conf=tmp_path / "missing")
        uninstall_speechd(settings)
        assert (sd / "speechd.conf").read_text() == "LogLevel 5\n"
        assert not (sd / f"modules/{SPEECHD_MODULE}.conf").exists()

    def test_uninstall_when_nothing_installed(self, tmp_path):
        uninstall_speechd(make_settings(tmp_path))  # no error
