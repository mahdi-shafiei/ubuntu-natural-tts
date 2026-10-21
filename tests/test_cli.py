import io
from dataclasses import replace
from pathlib import Path

import pytest

from natural_tts import __version__
from natural_tts.cli import Env, main
from natural_tts.config import (
    DEFAULT_SETTINGS_TOML,
    KOKORO_SERVICE,
    PIPER_SERVICE,
    SPEECHD_MODULE,
)
from natural_tts.hotkeys import MEDIA_KEYS_SCHEMA
from natural_tts.ipc import STOP_MESSAGE, DaemonNotRunningError
from natural_tts.selection import Source
from natural_tts.system import Result
from tests.fakes import LocalHTTPServer, RecordingRunner, make_settings

SYSTEM_CONF = "LogLevel 3\n"


class World:
    """Fakes for everything the CLI touches."""

    def __init__(self, tmp_path):
        self.settings = make_settings(tmp_path)
        self.paths = self.settings.paths
        self.sent: list[str] = []
        self.daemon_up = True
        self.selection = {
            Source.SELECTION: "highlighted",
            Source.CLIPBOARD: "copied",
        }
        self.execs: list[tuple[str, list[str]]] = []
        self.daemons: list[object] = []
        self.gsettings_ok = True
        self.runner = RecordingRunner(self.respond)
        self.stdout, self.stderr = io.StringIO(), io.StringIO()
        system_conf = tmp_path / "etc-speechd.conf"
        system_conf.write_text(SYSTEM_CONF)
        self.env = Env(
            paths=self.paths,
            runner=self.runner,
            stdin=io.StringIO(""),
            stdout=self.stdout,
            stderr=self.stderr,
            send=self.send,
            read=lambda source, runner: self.selection[source],
            execv=lambda path, argv: self.execs.append((path, list(argv))),
            run_daemon=self.daemons.append,
            speechd_system_conf=system_conf,
        )

    def respond(self, argv):
        if argv[0] == "gsettings":
            if not self.gsettings_ok:
                return Result(1, b"", b"No such schema")
            if argv[1] == "get" and argv[2] == MEDIA_KEYS_SCHEMA:
                return Result(0, b"@as []\n", b"")
            return Result(0, b"''\n", b"")
        if "piper.download_voices" in argv:
            voices = Path(argv[argv.index("--data-dir") + 1])
            voices.mkdir(parents=True, exist_ok=True)
            (voices / f"{argv[-1]}.onnx").write_bytes(b"onnx")
        return Result(0, b"", b"")

    def send(self, path, message):
        assert path == self.paths.kokoro_socket
        if not self.daemon_up:
            raise DaemonNotRunningError("not running or still starting")
        self.sent.append(message)

    def run(self, *argv, stdin=""):
        env = replace(self.env, stdin=io.StringIO(stdin))
        return main(list(argv), env)


@pytest.fixture
def world(tmp_path):
    return World(tmp_path)


class TestReadAloud:
    def test_read_selection_sends_highlighted_text(self, world):
        assert world.run("read", "selection") == 0
        assert world.sent == ["highlighted"]

    def test_read_clipboard_sends_clipboard(self, world):
        assert world.run("read", "clipboard") == 0
        assert world.sent == ["copied"]

    def test_nothing_selected_is_silent(self, world):
        world.selection[Source.SELECTION] = ""
        assert world.run("read", "selection") == 0
        assert world.sent == []

    def test_daemon_down_notifies_the_desktop(self, world):
        world.daemon_up = False
        assert world.run("read", "selection") == 1
        assert "still starting" in world.stderr.getvalue()
        notify = [a for a in world.runner.argvs if a[0] == "notify-send"]
        assert notify and "still starting" in notify[0][-1]

    def test_say_arguments_or_stdin(self, world):
        world.run("say", "Hello", "there.")
        world.run("say", stdin="From stdin.")
        assert world.sent == ["Hello there.", "From stdin."]

    def test_stop(self, world):
        assert world.run("stop") == 0
        assert world.sent == [STOP_MESSAGE]


class TestServices:
    def test_daemon_runs_with_loaded_settings(self, world):
        assert world.run("daemon") == 0
        assert world.daemons == [world.settings]

    def test_piper_server_execs_localhost_server(self, world):
        world.settings.piper_model.parent.mkdir(parents=True)
        world.settings.piper_model.write_bytes(b"onnx")
        world.run("piper-server")
        ((path, argv),) = world.execs
        assert path == str(world.paths.venv_python)
        assert argv[argv.index("--host") + 1] == "127.0.0.1"

    def test_piper_server_without_voice_explains_fix(self, world):
        assert world.run("piper-server") == 1
        assert "natural-tts apply" in world.stderr.getvalue()
        assert world.execs == []

    def test_piper_speak_plays_server_audio(self, world):
        with LocalHTTPServer(body=b"RIFFwav") as server:
            world.paths.settings_file.parent.mkdir(parents=True)
            world.paths.settings_file.write_text(
                f"[piper]\nport = {server.port}\n"
            )
            assert world.run("piper-speak", "40.00", stdin="Hi") == 0
            assert server.requests[0]["json"]["text"] == "Hi"
        (play,) = [c for c in world.runner.calls if c.argv[0] == "aplay"]
        assert play.stdin == b"RIFFwav"

    @pytest.mark.parametrize("rate", ["", "fast", "nan"])
    def test_piper_speak_tolerates_bad_rate(self, world, rate):
        with LocalHTTPServer(body=b"RIFF") as server:
            world.paths.settings_file.parent.mkdir(parents=True)
            world.paths.settings_file.write_text(
                f"[piper]\nport = {server.port}\n"
            )
            args = ["piper-speak", rate] if rate else ["piper-speak"]
            assert world.run(*args, stdin="x") == 0
            scale = server.requests[0]["json"]["length_scale"]
            assert scale == pytest.approx(1.05)

    def test_piper_speak_failure_is_reported(self, world):
        def respond(argv):
            return Result(1, b"", b"model missing")

        world.env = replace(world.env, runner=RecordingRunner(respond))
        world.paths.settings_file.parent.mkdir(parents=True)
        world.paths.settings_file.write_text("[piper]\nport = 1999\n")
        assert world.run("piper-speak", stdin="x") == 1
        assert "model missing" in world.stderr.getvalue()


class TestSetup:
    def test_setup_configures_everything(self, world):
        assert world.run("setup") == 0
        paths = world.paths
        assert paths.settings_file.read_text() == DEFAULT_SETTINGS_TOML
        assert world.settings.piper_model.exists()
        assert (paths.speechd_dir / f"modules/{SPEECHD_MODULE}.conf").exists()
        assert (
            f"DefaultModule {SPEECHD_MODULE}"
            in (paths.speechd_dir / "speechd.conf").read_text()
        )
        assert (paths.systemd_user_dir / PIPER_SERVICE).exists()
        argvs = world.runner.argvs
        assert any(
            a[:4] == ("systemctl", "--user", "enable", "--now") for a in argvs
        )
        assert any(a[:2] == ("gsettings", "set") for a in argvs)
        out = world.stdout.getvalue()
        assert "Super+Alt+R" in out and "natural-tts doctor" in out

    def test_setup_keeps_existing_settings(self, world):
        world.paths.settings_file.parent.mkdir(parents=True)
        world.paths.settings_file.write_text("[kokoro]\nspeed = 1.2\n")
        world.run("setup")
        assert world.paths.settings_file.read_text() == (
            "[kokoro]\nspeed = 1.2\n"
        )

    def test_setup_without_hotkeys(self, world):
        world.run("setup", "--no-hotkeys")
        assert not any(a[0] == "gsettings" for a in world.runner.argvs)

    def test_setup_outside_gnome_explains_manual_binding(self, world):
        world.gsettings_ok = False
        assert world.run("setup") == 0
        assert "bind" in world.stdout.getvalue().lower()

    def test_voice_download_is_skipped_when_present(self, world):
        world.settings.piper_model.parent.mkdir(parents=True)
        world.settings.piper_model.write_bytes(b"onnx")
        world.run("setup")
        assert not any(
            "download_voices" in " ".join(a) for a in world.runner.argvs
        )

    def test_failed_voice_download_stops_setup(self, world):
        world.env = replace(
            world.env,
            runner=RecordingRunner(
                lambda argv: Result(1, b"", b"network unreachable")
            ),
        )
        assert world.run("setup") == 1
        assert "network unreachable" in world.stderr.getvalue()

    def test_apply_rewrites_config_and_restarts(self, world):
        world.run("setup")
        world.paths.settings_file.write_text(
            '[piper]\nvoice = "en_GB-cori-high"\n'
        )
        assert world.run("apply") == 0
        module = world.paths.speechd_dir / f"modules/{SPEECHD_MODULE}.conf"
        assert "en_GB-cori-high" in module.read_text()
        assert (
            "systemctl",
            "--user",
            "restart",
            PIPER_SERVICE,
            KOKORO_SERVICE,
            "speech-dispatcher.service",
        ) in (world.runner.argvs)

    def test_teardown_reverts_setup(self, world):
        world.run("setup")
        assert world.run("teardown") == 0
        assert not (world.paths.systemd_user_dir / PIPER_SERVICE).exists()
        assert not (
            world.paths.speechd_dir / f"modules/{SPEECHD_MODULE}.conf"
        ).exists()
        assert world.paths.settings_file.exists()  # user data is kept


class TestSystemdFailure:
    def test_systemctl_failure_is_a_clear_error_not_a_traceback(self, world):
        def respond(argv):
            if argv[:2] == ("systemctl", "--user"):
                return Result(1, b"", b"Failed to connect to bus")
            return world.respond(argv)

        world.env = replace(world.env, runner=RecordingRunner(respond))
        assert world.run("setup") == 1
        err = world.stderr.getvalue()
        assert "Failed to connect to bus" in err
        assert "systemd user session" in err


class TestMisc:
    def test_invalid_settings_are_reported_with_exit_code_2(self, world):
        world.paths.settings_file.parent.mkdir(parents=True)
        world.paths.settings_file.write_text("[piper]\nport = 1\n")
        assert world.run("stop") == 2
        assert "piper.port" in world.stderr.getvalue()

    def test_doctor_exit_code_reflects_failures(self, world):
        assert world.run("doctor") == 1  # nothing installed in tmp home
        assert "[FAIL] Installation" in world.stdout.getvalue()

    def test_version(self, world, capsys):
        with pytest.raises(SystemExit) as exc:
            world.run("--version")
        assert exc.value.code == 0
        assert __version__ in capsys.readouterr().out

    def test_no_command_shows_help(self, world, capsys):
        with pytest.raises(SystemExit) as exc:
            world.run()
        assert exc.value.code == 2
