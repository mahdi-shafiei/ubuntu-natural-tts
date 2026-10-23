"""The ``natural-tts`` command.

Per-sentence commands (``piper-speak``, ``read``, ``stop``) import only the
standard library; heavier modules are imported inside the commands that
need them.
"""

from __future__ import annotations

import argparse
import hashlib
import math
import os
import platform
import shutil
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, TextIO

from natural_tts import __version__
from natural_tts.config import (
    DEFAULT_SETTINGS_TOML,
    HELPER_VERSION,
    RELEASE_DOWNLOADS,
    Paths,
    Settings,
    SettingsError,
    load_settings,
)
from natural_tts.ipc import (
    HTML_FORMAT,
    STOP_MESSAGE,
    DaemonNotRunningError,
    frame,
    send_message,
)
from natural_tts.selection import Selection, Source, read_selection
from natural_tts.system import Runner, run
from natural_tts.systemd import SystemdError
from natural_tts.text import decode_text

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


def fetch_url(url: str, timeout: float = 60.0) -> bytes:
    """Download ``url`` (release assets; the desktop proxy applies)."""
    with urllib.request.urlopen(url, timeout=timeout) as response:
        data: bytes = response.read()
    return data


@dataclass
class Env:
    """Everything a command interacts with (replaced by fakes in tests)."""

    paths: Paths = field(default_factory=_default_paths)
    runner: Runner = run
    stdin: BinaryIO = field(default_factory=lambda: sys.stdin.buffer)
    stdout: TextIO = field(default_factory=lambda: sys.stdout)
    stderr: TextIO = field(default_factory=lambda: sys.stderr)
    send: Callable[[Path, str], None] = send_message
    read: Callable[[Source, Runner], Selection] = read_selection
    execv: Callable[[str, Sequence[str]], object] = _execv
    run_daemon: Callable[[Settings], object] = _run_kokoro_daemon
    speechd_system_conf: Path = SYSTEM_SPEECHD_CONF
    fetch: Callable[[str], bytes] = fetch_url
    machine: str = field(default_factory=platform.machine)
    which: Callable[[str], str | None] = shutil.which


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
    selection = env.read(Source(args.source), env.runner)
    if selection.text.strip():
        if selection.html is not None:
            _send(env, settings, frame(selection.html, HTML_FORMAT))
        else:
            _send(env, settings, selection.text)
    return 0


def cmd_say(args: argparse.Namespace, env: Env, settings: Settings) -> int:
    """Read the given text (or stdin) aloud."""
    text = " ".join(args.text) if args.text else decode_text(env.stdin.read())
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
        client.speak(decode_text(env.stdin.read()), _parse_rate(args.rate))
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


_HELPER_NAME = "natural-tts-mathcat"
_NO_HELPER = (
    "warning: MathCAT helper not installed; formulas are read as words. "
    "Run natural-tts apply when online to retry."
)


def _mathcat_is_current(env: Env, helper: Path) -> bool:
    if not helper.exists():
        return False
    result = env.runner((str(helper), "--version"))
    return result.ok and result.text.split()[-1:] == [HELPER_VERSION]


def _download_mathcat(env: Env) -> bytes | None:
    asset = f"{_HELPER_NAME}-linux-{env.machine}"
    url = f"{RELEASE_DOWNLOADS}/v{HELPER_VERSION}/{asset}"
    try:
        binary = env.fetch(url)
        digest = env.fetch(url + ".sha256")
    except (urllib.error.URLError, OSError) as exc:
        print(
            f"warning: could not download the MathCAT helper: {exc}",
            file=env.stderr,
        )
        return None
    expected = digest.decode("ascii", "replace").split()[:1]
    if expected != [hashlib.sha256(binary).hexdigest()]:
        raise CommandError(
            f"MathCAT helper checksum mismatch for {url}; not installed"
        )
    return binary


def _build_mathcat(env: Env, source: Path | None) -> bytes | None:
    if source is None or not (source / "Cargo.toml").exists():
        return None
    if env.which("cargo") is None:
        print(
            "warning: cargo not found; cannot build the helper", file=env.stderr
        )
        return None
    print(
        "Building the MathCAT helper with cargo (a few minutes) ...",
        file=env.stdout,
    )
    argv = (
        "cargo",
        "build",
        "--release",
        "--manifest-path",
        str(source / "Cargo.toml"),
    )
    result = env.runner(argv)
    built = source / "target/release" / _HELPER_NAME
    if not result.ok or not built.exists():
        print(f"warning: {result.describe(argv)}", file=env.stderr)
        return None
    return built.read_bytes()


def _ensure_mathcat(env: Env, settings: Settings, source: Path | None) -> None:
    """Install the release's helper binary, or build it; warn if neither."""
    helper = settings.paths.mathcat_helper
    if _mathcat_is_current(env, helper):
        return
    print("Installing the MathCAT helper ...", file=env.stdout)
    binary = _download_mathcat(env)
    if binary is None:
        binary = _build_mathcat(env, source)
    if binary is None:
        print(_NO_HELPER, file=env.stderr)
        return
    helper.parent.mkdir(parents=True, exist_ok=True)
    staged = helper.with_name(helper.name + ".new")
    staged.write_bytes(binary)
    staged.chmod(0o755)
    staged.replace(helper)


def _configure(
    env: Env, settings: Settings, helper_source: Path | None = None
) -> None:
    from natural_tts.speechd import install_speechd
    from natural_tts.systemd import install_units

    _ensure_voice(env, settings)
    _ensure_mathcat(env, settings, helper_source)
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
    _configure(env, settings, args.helper_source)
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
    p.add_argument(
        "--helper-source",
        type=Path,
        default=None,
        metavar="DIR",
        help="Cargo project to build the MathCAT helper from when the "
        "release download fails (install.sh passes helper/mathcat)",
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
    except SystemdError as exc:
        print(
            f"natural-tts: {exc}\n"
            "natural-tts needs a systemd user session (a normal desktop "
            "login); check: systemctl --user status",
            file=env.stderr,
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
