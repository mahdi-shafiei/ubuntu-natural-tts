import pytest

from natural_tts.config import KOKORO_SERVICE, PIPER_SERVICE, Paths, Settings
from natural_tts.doctor import Check, Context, format_report, run_checks
from natural_tts.hotkeys import HOTKEYS, MEDIA_KEYS_SCHEMA
from natural_tts.speechd import DEFAULT_MARKER
from natural_tts.system import Result


class FakeSystem:
    """A healthy machine; individual tests break one thing at a time."""

    def __init__(self):
        self.inactive: set[str] = set()
        self.modules = "OUTPUT MODULES\nespeak-ng\npiper-generic\n"
        self.aplay = "default\npipewire\n"
        self.hotkeys = "[" + ", ".join(f"'{h.path}'" for h in HOTKEYS) + "]"

    def __call__(self, argv, *, stdin=None, timeout=None):
        argv = tuple(argv)
        if argv[:3] == ("systemctl", "--user", "is-active"):
            unit = argv[3]
            state = "inactive" if unit in self.inactive else "active"
            return Result(
                0 if state == "active" else 3, f"{state}\n".encode(), b""
            )
        if argv == ("spd-say", "-O"):
            return Result(0, self.modules.encode(), b"")
        if argv == ("aplay", "-L"):
            return Result(0, self.aplay.encode(), b"")
        if argv[:2] == ("gsettings", "get") and argv[2] == MEDIA_KEYS_SCHEMA:
            return Result(0, self.hotkeys.encode(), b"")
        raise AssertionError(argv)


@pytest.fixture
def ctx(tmp_path):
    paths = Paths.from_env(
        {"XDG_RUNTIME_DIR": str(tmp_path / "run")}, home=tmp_path
    )
    settings = Settings(paths=paths)
    paths.cli.parent.mkdir(parents=True)
    paths.cli.write_text("#!/bin/sh\n")
    settings.piper_model.parent.mkdir(parents=True)
    settings.piper_model.write_bytes(b"onnx")
    sd = paths.speechd_dir
    (sd / "modules").mkdir(parents=True)
    (sd / "speechd.conf").write_text(
        f"{DEFAULT_MARKER}\nDefaultModule piper-generic\n"
    )
    (sd / "modules/piper-generic.conf").write_text("x")
    paths.kokoro_socket.parent.mkdir(parents=True)
    paths.kokoro_socket.write_text("")
    return Context(
        settings=settings,
        runner=FakeSystem(),
        which=lambda name: f"/usr/bin/{name}",
        http_ok=lambda url: True,
    )


def by_name(checks: list[Check]) -> dict[str, Check]:
    return {c.name: c for c in checks}


def failed(ctx) -> dict[str, Check]:
    return {n: c for n, c in by_name(run_checks(ctx)).items() if not c.ok}


class TestRunChecks:
    def test_healthy_system_passes_everything(self, ctx):
        assert failed(ctx) == {}

    def test_every_check_has_a_fix_hint(self, ctx):
        ctx.runner.inactive = {
            PIPER_SERVICE,
            KOKORO_SERVICE,
            "speech-dispatcher.socket",
        }
        ctx.runner.modules = "OUTPUT MODULES\nespeak-ng\n"
        ctx.runner.aplay = "default\n"
        ctx.runner.hotkeys = "@as []"
        for check in run_checks(ctx):
            if not check.ok:
                assert check.fix, check.name

    def test_piper_service_down(self, ctx):
        ctx.runner.inactive = {PIPER_SERVICE}
        bad = failed(ctx)
        assert "Piper service" in bad
        assert (
            f"journalctl --user -u {PIPER_SERVICE}" in bad["Piper service"].fix
        )

    def test_piper_server_not_answering(self, ctx):
        ctx.http_ok = lambda url: False
        bad = failed(ctx)
        assert (
            "Piper server" in bad
            and "127.0.0.1:5150" in bad["Piper server"].detail
        )

    def test_kokoro_still_starting(self, ctx):
        ctx.settings.paths.kokoro_socket.unlink()
        assert "Kokoro daemon" in failed(ctx)

    def test_missing_voice(self, ctx):
        ctx.settings.piper_model.unlink()
        assert "natural-tts apply" in failed(ctx)["Piper voice"].fix

    def test_speechd_module_missing(self, ctx):
        ctx.runner.modules = "OUTPUT MODULES\nespeak-ng\n"
        assert "Speech Dispatcher module" in failed(ctx)

    def test_only_piper_listed_means_addmodule_problem(self, ctx):
        ctx.runner.modules = "OUTPUT MODULES\npiper-generic\n"
        bad = failed(ctx)
        assert "AddModule" in bad["Speech Dispatcher module"].fix

    def test_default_module_not_set(self, ctx):
        (ctx.settings.paths.speechd_dir / "speechd.conf").write_text("")
        assert "Default voice" in failed(ctx)

    def test_pipewire_alsa_missing(self, ctx):
        ctx.runner.aplay = "default\nsysdefault\n"
        assert "pipewire-alsa" in failed(ctx)["Audio routing"].fix

    def test_clipboard_tools_missing(self, ctx):
        ctx.which = lambda name: None
        bad = failed(ctx)
        assert "xclip" in bad["Clipboard tools"].fix

    def test_hotkeys_missing(self, ctx):
        ctx.runner.hotkeys = "@as []"
        assert "natural-tts setup" in failed(ctx)["Hotkeys"].fix

    def test_outside_gnome_hotkeys_are_skipped_not_failed(self, ctx):
        runner = ctx.runner

        def no_gsettings(argv, **kw):
            if argv[0] == "gsettings":
                return Result(1, b"", b"No such schema")
            return runner(argv, **kw)

        ctx.runner = no_gsettings
        check = by_name(run_checks(ctx))["Hotkeys"]
        assert check.ok and "not GNOME" in check.detail

    def test_not_installed_at_all(self, ctx):
        ctx.settings.paths.cli.unlink()
        assert "install.sh" in failed(ctx)["Installation"].fix


class TestFormat:
    def test_report_marks_passes_and_failures(self):
        report = format_report(
            [
                Check("Piper voice", True, "en_US-lessac-high"),
                Check(
                    "Hotkeys", False, "not installed", "run natural-tts setup"
                ),
            ]
        )
        assert report.splitlines() == [
            "[ ok ] Piper voice: en_US-lessac-high",
            "[FAIL] Hotkeys: not installed",
            "       fix: run natural-tts setup",
        ]


class TestHttpOk:
    def test_real_server(self):
        import socket
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer

        from natural_tts.doctor import http_ok

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()

            def log_message(self, *args):
                pass

        httpd = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(
            target=httpd.serve_forever, args=(0.05,), daemon=True
        ).start()
        try:
            port = httpd.server_address[1]
            assert http_ok(f"http://127.0.0.1:{port}/voices")
        finally:
            httpd.shutdown()
            httpd.server_close()
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            free = s.getsockname()[1]
        assert not http_ok(f"http://127.0.0.1:{free}/voices")
