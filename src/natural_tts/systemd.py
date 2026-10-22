"""systemd user services for the Piper server and the Kokoro daemon."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass

from natural_tts.config import KOKORO_SERVICE, PIPER_SERVICE, SERVICES, Settings
from natural_tts.system import Runner, plain_argument, run

SPEECHD_SOCKET = "speech-dispatcher.socket"
SPEECHD_SERVICE = "speech-dispatcher.service"
_SYSTEMCTL = ("systemctl", "--user")


class SystemdError(RuntimeError):
    """Raised when a required ``systemctl --user`` call fails."""


@dataclass(frozen=True)
class Unit:
    """A minimal long-running systemd user service."""

    description: str
    exec_start: tuple[str, ...]
    after: tuple[str, ...] = ()

    def render(self) -> str:
        """Render the unit file.

        Raises:
            ValueError: if an argument would need quoting.
        """
        command = " ".join(plain_argument(arg) for arg in self.exec_start)
        lines = ["[Unit]", f"Description={self.description}"]
        if self.after:
            lines.append(f"After={' '.join(self.after)}")
        lines += [
            "",
            "[Service]",
            f"ExecStart={command}",
            "Restart=on-failure",
            "RestartSec=2",
            "",
            "[Install]",
            "WantedBy=default.target",
        ]
        return "\n".join(lines) + "\n"


def render_units(settings: Settings) -> dict[str, str]:
    """Render both services.

    The units only run ``natural-tts``; voices, ports and speeds are read
    from settings.toml at start-up, so they live in exactly one place.
    """
    cli = str(settings.paths.cli)
    units = {
        PIPER_SERVICE: Unit(
            description="natural-tts: Piper TTS server (localhost only)",
            exec_start=(cli, "piper-server"),
        ),
        KOKORO_SERVICE: Unit(
            description="natural-tts: Kokoro read-aloud daemon",
            exec_start=(cli, "daemon"),
            after=("pipewire.service", "pipewire-pulse.service"),
        ),
    }
    return {name: unit.render() for name, unit in units.items()}


def _systemctl(runner: Runner, *args: str, check: bool = True) -> None:
    argv = (*_SYSTEMCTL, *args)
    result = runner(argv)
    if check and not result.ok:
        raise SystemdError(result.describe(argv))


def install_units(settings: Settings, runner: Runner = run) -> None:
    """Write the unit files and reload systemd."""
    unit_dir = settings.paths.systemd_user_dir
    unit_dir.mkdir(parents=True, exist_ok=True)
    for name, text in render_units(settings).items():
        (unit_dir / name).write_text(text)
    _systemctl(runner, "daemon-reload")


def activate(runner: Runner = run) -> None:
    """Enable the services and the Speech Dispatcher socket, then (re)start.

    The socket lets sandboxed apps (e.g. the Firefox snap) reach Speech
    Dispatcher, which then picks up the new default module on restart.
    The services are restarted rather than started so that an upgrade
    replaces a daemon still running the old code; enabling them without
    ``--now`` avoids loading Kokoro twice on a fresh install.
    """
    _systemctl(runner, "enable", "--now", SPEECHD_SOCKET)
    _systemctl(runner, "enable", *SERVICES)
    restart_services(runner)


def restart_services(runner: Runner = run) -> None:
    """Restart everything so new code and settings take effect.

    Speech Dispatcher may not be running yet (its socket starts it on
    demand), so only the natural-tts services are required to restart.

    Raises:
        SystemdError: if a natural-tts service fails to restart.
    """
    _systemctl(runner, "restart", *SERVICES)
    _systemctl(runner, "restart", SPEECHD_SERVICE, check=False)


def deactivate(runner: Runner = run) -> None:
    """Stop and disable the natural-tts services (if present)."""
    _systemctl(runner, "disable", "--now", *SERVICES, check=False)


def uninstall_units(settings: Settings, runner: Runner = run) -> None:
    """Remove the unit files and reload systemd."""
    for name in SERVICES:
        with contextlib.suppress(FileNotFoundError):
            (settings.paths.systemd_user_dir / name).unlink()
    _systemctl(runner, "daemon-reload", check=False)
