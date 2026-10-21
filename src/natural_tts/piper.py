"""Piper: the fast system voice used through Speech Dispatcher."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from natural_tts.audio import WavPlayer, play_wav
from natural_tts.config import Settings
from natural_tts.system import Runner, run

LOCALHOST = "127.0.0.1"
HTTP_TIMEOUT = 60.0
# Speech Dispatcher rates run from -100 (slowest) to +100 (fastest).
_RATE_LIMIT = 100.0


class PiperError(RuntimeError):
    """Raised when Piper cannot synthesize at all."""


class PiperUnavailableError(PiperError):
    """Raised when the local Piper server cannot synthesize."""


def length_scale_for_rate(rate: float, base: float) -> float:
    """Map a Speech Dispatcher rate to a Piper length scale.

    Rate 0 keeps ``base``; +100 halves the duration and -100 doubles it, with
    an exponential curve in between so each step sounds evenly spaced.
    """
    rate = max(-_RATE_LIMIT, min(_RATE_LIMIT, rate))
    return float(base * 2.0 ** (-rate / _RATE_LIMIT))


def server_command(settings: Settings) -> list[str]:
    """Command line for the Piper HTTP server, bound to localhost only.

    Piper's server listens on all interfaces by default and exposes a voice
    download endpoint, so the host is always pinned to 127.0.0.1.
    """
    piper = settings.piper
    return [
        str(settings.paths.venv_python),
        "-m",
        "piper.http_server",
        "--host",
        LOCALHOST,
        "--port",
        str(piper.port),
        "--data-dir",
        str(settings.paths.voices_dir),
        "-m",
        piper.voice,
        "--sentence-silence",
        str(piper.sentence_silence),
    ]


def cli_command(settings: Settings, length_scale: float) -> list[str]:
    """Command line for one-shot synthesis to WAV on stdout (fallback)."""
    return [
        str(settings.paths.venv / "bin/piper"),
        "-m",
        str(settings.piper_model),
        "-f",
        "-",
        "--length-scale",
        f"{length_scale:.3f}",
        "--sentence-silence",
        str(settings.piper.sentence_silence),
    ]


# Localhost traffic must never go through a desktop proxy setting.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class PiperClient:
    """Synthesizes with the local Piper server, falling back to the CLI."""

    def __init__(
        self,
        settings: Settings,
        player: WavPlayer = play_wav,
        cli_runner: Runner = run,
    ) -> None:
        """Create a client.

        Args:
            settings: natural-tts settings.
            player: Plays WAV bytes.
            cli_runner: Runs the Piper CLI for the fallback path.
        """
        self._settings = settings
        self._player = player
        self._cli_runner = cli_runner

    def synthesize(self, text: str, length_scale: float) -> bytes:
        """Return WAV bytes for ``text`` from the Piper server.

        Raises:
            PiperUnavailableError: if the server is down or fails.
        """
        piper = self._settings.piper
        body = json.dumps(
            {
                "text": text,
                "voice": piper.voice,
                "length_scale": length_scale,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"http://{LOCALHOST}:{piper.port}/synthesize",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        try:
            with _OPENER.open(request, timeout=HTTP_TIMEOUT) as response:
                data: bytes = response.read()
        except (urllib.error.URLError, OSError) as exc:
            raise PiperUnavailableError(str(exc)) from exc
        return data

    def speak(self, text: str, rate: float) -> None:
        """Speak ``text`` at a Speech Dispatcher ``rate`` (blocks).

        Raises:
            PiperError: if both the server and the CLI fallback fail.
        """
        if not text.strip():
            return
        scale = length_scale_for_rate(rate, self._settings.piper.length_scale)
        try:
            wav = self.synthesize(text, scale)
        except PiperUnavailableError:
            # Slower (reloads the model) but keeps speech working.
            wav = self._synthesize_with_cli(text, scale)
        self._player(wav)

    def _synthesize_with_cli(self, text: str, length_scale: float) -> bytes:
        argv = cli_command(self._settings, length_scale)
        result = self._cli_runner(argv, stdin=(text + "\n").encode("utf-8"))
        if not result.ok:
            raise PiperError(result.describe(argv))
        return result.stdout
