"""The ``natural-tts`` command.

Per-sentence commands (``piper-speak``, ``read``, ``stop``) import only the
standard library; heavier modules are imported inside the commands that
need them.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

from natural_tts import __version__
from natural_tts.config import (
    DEFAULT_SETTINGS_TOML,
    Paths,
    Settings,
    SettingsError,
    load_settings,
)
from natural_tts.ipc import STOP_MESSAGE, DaemonNotRunningError, send_message
from natural_tts.selection import Source, read_text
from natural_tts.system import Runner, run

SYSTEM_SPEECHD_CONF = Path("/etc/speech-dispatcher/speechd.conf")


def _run_kokoro_daemon(settings: Settings) -> None:
    from natural_tts.daemon import run as run_daemon
    from natural_tts.kokoro_backend import KokoroSynthesizer, SounddeviceSink

    run_daemon(
        settings,
        KokoroSynthesizer.load(settings.kokoro),
        SounddeviceSink.default(),
    )


def _execv(path: str, argv: Sequence[str]) -> None:
    os.execv(path, list(argv))


def _default_paths() -> Paths:
    return Paths.from_env(os.environ)


@dataclass
class Env:
    """Everything a command interacts with (replaced by fakes in tests)."""

    paths: Paths = field(default_factory=_default_paths)
    runner: Runner = run
    stdin: TextIO = field(default_factory=lambda: sys.stdin)
    stdout: TextIO = field(default_factory=lambda: sys.stdout)
    stderr: TextIO = field(default_factory=lambda: sys.stderr)
    send: Callable[[Path, str], None] = send_message
    read: Callable[[Source, Runner], str] = read_text
    execv: Callable[[str, Sequence[str]], object] = _execv
    run_daemon: Callable[[Settings], object] = _run_kokoro_daemon
    speechd_system_conf: Path = SYSTEM_SPEECHD_CONF


class CommandError(Exception):
    """A user-facing failure; printed without a traceback."""


Command = Callable[[argparse.Namespace, Env, Settings], int]


# -- read-aloud -----------------------------------------------------------


def _send(env: Env, settings: Settings, message: str) -> None:
    try:
        env.send(settings.paths.kokoro_socket, message)
    except DaemonNotRunningError as exc:
        # Hotkeys have no terminal, so also tell the user on the desktop.
        env.runner(
            ("notify-send", "--app-name=natural-tts", "natural-tts", str(exc))
        )
        raise CommandError(str(exc)) from exc


def cmd_read(args: argparse.Namespace, env: Env, settings: Settings) -> int:
    """Read the highlighted text or the clipboard aloud."""
    text = env.read(Source(args.source), env.runner)
    if text.strip():
        _send(env, settings, text)
    return 0


def cmd_say(args: argparse.Namespace, env: Env, settings: Settings) -> int:
    """Read the given text (or stdin) aloud."""
    text = " ".join(args.text) if args.text else env.stdin.read()
    if text.strip():
        _send(env, settings, text)
    return 0


def cmd_stop(args: argparse.Namespace, env: Env, settings: Settings) -> int:
    """Stop reading aloud."""
    _send(env, settings, STOP_MESSAGE)
    return 0


# -- services ---------------------------------------------------------------


def _parse_rate(raw: str) -> float:
    try:
        rate = float(raw)
    except ValueError:
        return 0.0
    return rate if math.isfinite(rate) else 0.0


def cmd_piper_speak(
    args: argparse.Namespace, env: Env, settings: Settings
) -> int:
    """Speak stdin with Piper (Speech Dispatcher's synth command)."""
    from natural_tts.audio import AudioError, play_wav
    from natural_tts.piper import PiperClient, PiperError

    client = PiperClient(
        settings,
        player=lambda wav: play_wav(wav, env.runner),
        cli_runner=env.runner,
    )
    try:
        client.speak(env.stdin.read(), _parse_rate(args.rate))
    except (PiperError, AudioError) as exc:
        raise CommandError(str(exc)) from exc
    return 0


def cmd_piper_server(
    args: argparse.Namespace, env: Env, settings: Settings
) -> int:
    """Replace this process with the localhost-only Piper server."""
    from natural_tts.piper import server_command

    if not settings.piper_model.exists():
        raise CommandError(
            f"voice {settings.piper.voice} is not downloaded; run: "
            "natural-tts apply"
        )
    argv = server_command(settings)
    env.execv(argv[0], argv)
    return 0


def cmd_daemon(args: argparse.Namespace, env: Env, settings: Settings) -> int:
    """Run the Kokoro read-aloud daemon."""
    env.run_daemon(settings)
    return 0


# -- installation -----------------------------------------------------------


def _ensure_voice(env: Env, settings: Settings) -> None:
    if settings.piper_model.exists():
        return
    paths = settings.paths
    argv = (
        str(paths.venv_python),
        "-m",
        "piper.download_voices",
        "--data-dir",
        str(paths.voices_dir),
        settings.piper.voice,
    )
    print(
        f"Downloading Piper voice {settings.piper.voice} ...", file=env.stdout
    )
    paths.voices_dir.mkdir(parents=True, exist_ok=True)
    result = env.runner(argv)
    if not result.ok or not settings.piper_model.exists():
        raise CommandError(f"voice download failed: {result.describe(argv)}")


def _configure(env: Env, settings: Settings) -> None:
    from natural_tts.speechd import install_speechd
    from natural_tts.systemd import install_units

    _ensure_voice(env, settings)
    cli = str(settings.paths.cli)
    for warning in install_speechd(settings, cli, env.speechd_system_conf):
        print(f"warning: {warning}", file=env.stderr)
    install_units(settings, env.runner)


def _install_hotkeys(env: Env, settings: Settings) -> None:
    from natural_tts.hotkeys import (
        HOTKEYS,
        HotkeysUnavailableError,
        install_hotkeys,
    )

    try:
        warnings = install_hotkeys(str(settings.paths.cli), env.runner)
    except HotkeysUnavailableError:
        print(
            "GNOME shortcuts are not available here; bind these "
            "commands in your desktop's keyboard settings:",
            file=env.stdout,
        )
        for hotkey in HOTKEYS:
            print(
                f"  {hotkey.command(str(settings.paths.cli))}", file=env.stdout
            )
        return
    for warning in warnings:
        print(f"warning: {warning}", file=env.stderr)


_NEXT_STEPS = """
natural-tts is set up.
  * Highlight text anywhere and press Super+Alt+R (Super+Alt+C reads the
    clipboard, Super+Alt+S stops). Kokoro needs ~10-20 s to load at login.
  * Firefox Reader View, Foliate and Orca now use Piper. Restart Firefox.
  * Change voices or speeds in {settings}, then run: natural-tts apply
  * If anything is silent, run: natural-tts doctor
"""


def cmd_setup(args: argparse.Namespace, env: Env, settings: Settings) -> int:
    """Install configuration, services and hotkeys."""
    from natural_tts.systemd import activate

    settings_file = settings.paths.settings_file
    if not settings_file.exists():
        settings_file.parent.mkdir(parents=True, exist_ok=True)
        settings_file.write_text(DEFAULT_SETTINGS_TOML)
    _configure(env, settings)
    activate(env.runner)
    if not args.no_hotkeys:
        _install_hotkeys(env, settings)
    print(_NEXT_STEPS.format(settings=settings_file), file=env.stdout)
    return 0


def cmd_apply(args: argparse.Namespace, env: Env, settings: Settings) -> int:
    """Apply changed settings and restart the services."""
    from natural_tts.systemd import restart_services

    _configure(env, settings)
    restart_services(env.runner)
    print("Settings applied.", file=env.stdout)
    return 0


def cmd_teardown(args: argparse.Namespace, env: Env, settings: Settings) -> int:
    """Remove services, Speech Dispatcher config and hotkeys."""
    from natural_tts.hotkeys import uninstall_hotkeys
    from natural_tts.speechd import uninstall_speechd
    from natural_tts.systemd import deactivate, uninstall_units

    deactivate(env.runner)
    uninstall_units(settings, env.runner)
    uninstall_speechd(settings)
    uninstall_hotkeys(env.runner)
    print(
        "Removed services, Speech Dispatcher config and hotkeys. "
        f"Settings and voices are kept in {settings.paths.config_dir} "
        f"and {settings.paths.data_dir}.",
        file=env.stdout,
    )
    return 0


def cmd_doctor(args: argparse.Namespace, env: Env, settings: Settings) -> int:
    """Check every component and print fixes."""
    from natural_tts.doctor import Context, format_report, run_checks

    checks = run_checks(Context(settings=settings, runner=env.runner))
    print(format_report(checks), file=env.stdout)
    return 0 if all(check.ok for check in checks) else 1


# -- argument parsing -------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        prog="natural-tts",
        description="Natural-sounding text-to-speech for the Linux desktop.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    sub = parser.add_subparsers(
        dest="command", required=True, metavar="COMMAND"
    )

    def add(
        name: str, func: Command, help_text: str
    ) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help_text, description=help_text)
        p.set_defaults(func=func)
        return p

    p = add("read", cmd_read, "read the highlighted text or the clipboard")
    p.add_argument("source", choices=[s.value for s in Source])
    p = add("say", cmd_say, "read TEXT (or stdin) aloud")
    p.add_argument("text", nargs="*")
    add("stop", cmd_stop, "stop reading aloud")
    p = add("setup", cmd_setup, "install config, services and hotkeys")
    p.add_argument(
        "--no-hotkeys",
        action="store_true",
        help="do not add GNOME keyboard shortcuts",
    )
    add("apply", cmd_apply, "apply settings.toml and restart services")
    add("doctor", cmd_doctor, "diagnose problems and suggest fixes")
    add("teardown", cmd_teardown, "remove services, config and hotkeys")
    p = add(
        "piper-speak",
        cmd_piper_speak,
        "speak stdin with Piper (used by Speech Dispatcher)",
    )
    p.add_argument("rate", nargs="?", default="0")
    add("piper-server", cmd_piper_server, "run the Piper server (service)")
    add("daemon", cmd_daemon, "run the Kokoro daemon (service)")
    return parser


def main(argv: Sequence[str] | None = None, env: Env | None = None) -> int:
    """Entry point; returns the process exit code."""
    args = build_parser().parse_args(argv)
    env = env if env is not None else Env()
    try:
        settings = load_settings(env.paths)
    except SettingsError as exc:
        print(f"natural-tts: {env.paths.settings_file}: {exc}", file=env.stderr)
        return 2
    func: Command = args.func
    try:
        return func(args, env, settings)
    except CommandError as exc:
        print(f"natural-tts: {exc}", file=env.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
