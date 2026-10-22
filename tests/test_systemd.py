import pytest

from natural_tts.config import (
    KOKORO_SERVICE,
    PIPER_SERVICE,
    KokoroSettings,
    PiperSettings,
)
from natural_tts.system import Result
from natural_tts.systemd import (
    SPEECHD_SERVICE,
    SPEECHD_SOCKET,
    SystemdError,
    Unit,
    activate,
    deactivate,
    install_units,
    render_units,
    restart_services,
    uninstall_units,
)
from tests.fakes import RecordingRunner, make_settings


def FakeSystemctl(fail=()):
    """systemctl that fails any call containing one of ``fail``."""

    def respond(argv):
        if any(f in argv for f in fail):
            return Result(1, b"", b"unit not found")
        return Result(0, b"", b"")

    return RecordingRunner(respond)


class TestUnit:
    def test_render(self):
        unit = Unit(
            description="Demo",
            exec_start=("/bin/x", "serve"),
            after=("a.service",),
        )
        assert unit.render() == (
            "[Unit]\n"
            "Description=Demo\n"
            "After=a.service\n"
            "\n"
            "[Service]\n"
            "ExecStart=/bin/x serve\n"
            "Restart=on-failure\n"
            "RestartSec=2\n"
            "\n"
            "[Install]\n"
            "WantedBy=default.target\n"
        )

    def test_render_without_after(self):
        assert "After=" not in Unit("D", ("/bin/x",)).render()

    def test_rejects_unquotable_arguments(self):
        with pytest.raises(ValueError, match="cannot contain"):
            Unit("D", ("/home/a b/x",)).render()


class TestRenderUnits:
    def test_both_services_run_the_cli(self, tmp_path):
        settings = make_settings(tmp_path)
        units = render_units(settings)
        cli = settings.paths.cli
        assert set(units) == {PIPER_SERVICE, KOKORO_SERVICE}
        assert f"ExecStart={cli} piper-server\n" in units[PIPER_SERVICE]
        assert f"ExecStart={cli} daemon\n" in units[KOKORO_SERVICE]
        assert "pipewire" in units[KOKORO_SERVICE]

    def test_units_carry_no_voice_settings(self, tmp_path):
        # Settings live only in settings.toml (read at start-up).
        units = render_units(make_settings(tmp_path))
        assert all(
            PiperSettings().voice not in u and KokoroSettings().voice not in u
            for u in units.values()
        )


class TestInstall:
    def test_install_writes_units_and_reloads(self, tmp_path):
        settings = make_settings(tmp_path)
        runner = FakeSystemctl()
        install_units(settings, runner)
        for name in (PIPER_SERVICE, KOKORO_SERVICE):
            assert (settings.paths.systemd_user_dir / name).is_file()
        assert runner.argvs == [("systemctl", "--user", "daemon-reload")]

    def test_activate_enables_then_restarts_running_services(self):
        # `enable --now` leaves a running service on old code, so an upgrade
        # (`git pull && ./install.sh`) must restart the natural-tts services.
        runner = FakeSystemctl()
        activate(runner)
        assert runner.argvs == [
            ("systemctl", "--user", "enable", "--now", SPEECHD_SOCKET),
            ("systemctl", "--user", "enable", PIPER_SERVICE, KOKORO_SERVICE),
            ("systemctl", "--user", "restart", PIPER_SERVICE, KOKORO_SERVICE),
            ("systemctl", "--user", "restart", SPEECHD_SERVICE),
        ]

    def test_activate_raises_when_enable_fails(self):
        with pytest.raises(SystemdError, match="unit not found"):
            activate(FakeSystemctl(fail={"enable"}))

    def test_activate_raises_when_a_service_restart_fails(self):
        with pytest.raises(SystemdError, match="unit not found"):
            activate(FakeSystemctl(fail={KOKORO_SERVICE}))

    def test_speechd_restart_failure_is_tolerated(self):
        # speech-dispatcher.service may not be running yet; the socket
        # starts it on demand.
        activate(FakeSystemctl(fail={SPEECHD_SERVICE}))

    def test_restart_services(self):
        runner = FakeSystemctl()
        restart_services(runner)
        assert runner.argvs == [
            ("systemctl", "--user", "restart", PIPER_SERVICE, KOKORO_SERVICE),
            ("systemctl", "--user", "restart", SPEECHD_SERVICE),
        ]

    def test_restart_services_raises_when_a_service_fails(self):
        with pytest.raises(SystemdError, match="unit not found"):
            restart_services(FakeSystemctl(fail={PIPER_SERVICE}))

    def test_restart_services_tolerates_missing_speechd(self):
        restart_services(FakeSystemctl(fail={SPEECHD_SERVICE}))

    def test_deactivate_and_uninstall(self, tmp_path):
        settings = make_settings(tmp_path)
        runner = FakeSystemctl()
        install_units(settings, runner)
        deactivate(runner)
        uninstall_units(settings, runner)
        assert (
            "systemctl",
            "--user",
            "disable",
            "--now",
            PIPER_SERVICE,
            KOKORO_SERVICE,
        ) in runner.argvs
        assert not (settings.paths.systemd_user_dir / PIPER_SERVICE).exists()
        assert runner.argvs[-1] == ("systemctl", "--user", "daemon-reload")

    def test_deactivate_tolerates_missing_units(self):
        deactivate(FakeSystemctl(fail={"disable"}))
