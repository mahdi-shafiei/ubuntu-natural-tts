import pytest

from natural_tts.config import PiperSettings
from natural_tts.piper import (
    PiperClient,
    PiperError,
    PiperUnavailableError,
    cli_command,
    length_scale_for_rate,
    server_command,
)
from natural_tts.system import Result
from tests.fakes import LocalHTTPServer, unused_port
from tests.fakes import make_settings as base_settings

WAV = b"RIFF....WAVEfake"


def make_settings(tmp_path, port=5150):
    return base_settings(tmp_path, piper=PiperSettings(port=port))


def FakePiperServer(status=200):
    """A stand-in for `python -m piper.http_server`."""
    return LocalHTTPServer(status=status, body=WAV)


@pytest.fixture
def fake_server():
    server = FakePiperServer()
    yield server
    server.close()


class TestLengthScaleForRate:
    @pytest.mark.parametrize(
        ("rate", "expected"),
        [(0, 1.0), (100, 0.5), (-100, 2.0), (50, 2**-0.5)],
    )
    def test_maps_speechd_rate_exponentially(self, rate, expected):
        assert length_scale_for_rate(rate, base=1.0) == pytest.approx(expected)

    def test_scales_from_base(self):
        assert length_scale_for_rate(0, base=1.05) == pytest.approx(1.05)

    @pytest.mark.parametrize(("rate", "clamped"), [(500, 100), (-500, -100)])
    def test_out_of_range_rates_are_clamped(self, rate, clamped):
        assert length_scale_for_rate(rate, 1.0) == length_scale_for_rate(
            clamped, 1.0
        )


class TestCommands:
    def test_server_binds_localhost_only(self, tmp_path):
        s = make_settings(tmp_path)
        cmd = server_command(s)
        assert cmd[:3] == [str(s.paths.venv_python), "-m", "piper.http_server"]
        assert cmd[cmd.index("--host") + 1] == "127.0.0.1"
        assert cmd[cmd.index("--port") + 1] == "5150"
        assert cmd[cmd.index("-m", 3) + 1] == s.piper.voice
        assert cmd[cmd.index("--data-dir") + 1] == str(s.paths.voices_dir)
        assert cmd[cmd.index("--sentence-silence") + 1] == "0.25"

    def test_cli_writes_wav_to_stdout(self, tmp_path):
        s = make_settings(tmp_path)
        cmd = cli_command(s, length_scale=1.2)
        assert cmd[0] == str(s.paths.venv / "bin/piper")
        assert cmd[cmd.index("-m") + 1] == str(s.piper_model)
        assert cmd[cmd.index("-f") + 1] == "-"
        assert cmd[cmd.index("--length-scale") + 1] == "1.200"


class TestPiperClient:
    def test_speaks_through_server(self, tmp_path, fake_server):
        played: list[bytes] = []
        client = PiperClient(
            make_settings(tmp_path, fake_server.port), player=played.append
        )
        client.speak("Café — don't stop", rate=0)
        assert played == [WAV]
        (req,) = fake_server.requests
        assert req["path"] == "/synthesize"
        assert req["json"]["text"] == "Café — don't stop"
        assert req["json"]["voice"] == PiperSettings().voice
        assert req["json"]["length_scale"] == pytest.approx(1.05)

    def test_rate_reaches_server(self, tmp_path, fake_server):
        client = PiperClient(
            make_settings(tmp_path, fake_server.port), player=lambda wav: None
        )
        client.speak("fast", rate=100)
        assert fake_server.requests[0]["json"]["length_scale"] == (
            pytest.approx(0.525)
        )

    def test_blank_text_does_nothing(self, tmp_path, fake_server):
        played: list[bytes] = []
        client = PiperClient(
            make_settings(tmp_path, fake_server.port), player=played.append
        )
        client.speak(" \n ", rate=0)
        assert played == [] and fake_server.requests == []

    def test_falls_back_to_cli_when_server_is_down(self, tmp_path):
        calls: list[tuple[list[str], bytes]] = []

        def cli_runner(argv, *, stdin=None, timeout=None):
            calls.append((argv, stdin))
            return Result(0, b"RIFFcli", b"")

        played: list[bytes] = []
        client = PiperClient(
            make_settings(tmp_path, port=unused_port()),
            player=played.append,
            cli_runner=cli_runner,
        )
        client.speak("hello", rate=0)
        assert played == [b"RIFFcli"]
        argv, stdin = calls[0]
        assert "-f" in argv and stdin == b"hello\n"

    def test_server_error_status_also_falls_back(self, tmp_path):
        server = FakePiperServer(status=500)
        try:
            played: list[bytes] = []
            client = PiperClient(
                make_settings(tmp_path, server.port),
                player=played.append,
                cli_runner=lambda argv, **kw: Result(0, b"RIFFcli", b""),
            )
            client.speak("x", rate=0)
            assert played == [b"RIFFcli"]
        finally:
            server.close()

    def test_synthesize_raises_when_unreachable(self, tmp_path):
        client = PiperClient(
            make_settings(tmp_path, port=unused_port()), player=lambda wav: None
        )
        with pytest.raises(PiperUnavailableError):
            client.synthesize("x", length_scale=1.0)

    def test_ignores_http_proxy_environment(
        self, tmp_path, fake_server, monkeypatch
    ):
        # A desktop proxy setting must never capture localhost traffic.
        monkeypatch.setenv("http_proxy", "http://127.0.0.1:1")
        monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
        monkeypatch.delenv("no_proxy", raising=False)
        monkeypatch.delenv("NO_PROXY", raising=False)
        played: list[bytes] = []
        client = PiperClient(
            make_settings(tmp_path, fake_server.port), player=played.append
        )
        client.speak("hi", rate=0)
        assert played == [WAV]


def test_cli_fallback_failure_raises_with_reason(tmp_path):
    client = PiperClient(
        make_settings(tmp_path, port=unused_port()),
        player=lambda wav: None,
        cli_runner=lambda argv, **kw: Result(1, b"", b"model not found"),
    )
    with pytest.raises(PiperError, match="model not found"):
        client.speak("x", rate=0)
