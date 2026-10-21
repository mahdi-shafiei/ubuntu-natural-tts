"""``natural-tts doctor``: check every component and suggest fixes."""

from __future__ import annotations

import shutil
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass

from natural_tts.config import (
    KOKORO_SERVICE,
    PIPER_SERVICE,
    SPEECHD_MODULE,
    Settings,
)
from natural_tts.hotkeys import CUSTOM_LIST_KEY, HOTKEYS, MEDIA_KEYS_SCHEMA
from natural_tts.piper import LOCALHOST
from natural_tts.system import Runner, run
from natural_tts.systemd import SPEECHD_SOCKET

_NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def http_ok(url: str) -> bool:
    """True if ``url`` answers with HTTP 200 within two seconds."""
    try:
        with _NO_PROXY.open(url, timeout=2) as response:
            return bool(response.status == 200)
    except (urllib.error.URLError, OSError):
        return False


@dataclass(frozen=True)
class Check:
    """Result of one diagnostic check."""

    name: str
    ok: bool
    detail: str
    fix: str = ""


@dataclass
class Context:
    """Everything the checks inspect (injectable for tests)."""

    settings: Settings
    runner: Runner = run
    which: Callable[[str], str | None] = shutil.which
    http_ok: Callable[[str], bool] = http_ok


def _service(ctx: Context, name: str, unit: str) -> Check:
    state = ctx.runner(("systemctl", "--user", "is-active", unit)).text.strip()
    return Check(
        name,
        state == "active",
        f"{unit} is {state or 'unknown'}",
        f"systemctl --user restart {unit}; journalctl --user -u {unit} -n 30",
    )


def _installation(ctx: Context) -> Check:
    cli = ctx.settings.paths.cli
    return Check(
        "Installation",
        cli.exists(),
        str(cli),
        "run ./install.sh from a clone of the repository",
    )


def _piper_voice(ctx: Context) -> Check:
    model = ctx.settings.piper_model
    return Check(
        "Piper voice",
        model.exists(),
        str(model),
        "natural-tts apply  (downloads the configured voice)",
    )


def _piper_service(ctx: Context) -> Check:
    return _service(ctx, "Piper service", PIPER_SERVICE)


def _piper_server(ctx: Context) -> Check:
    address = f"{LOCALHOST}:{ctx.settings.piper.port}"
    ok = ctx.http_ok(f"http://{address}/voices")
    return Check(
        "Piper server",
        ok,
        f"{'answering' if ok else 'no answer'} on {address}",
        f"check that nothing else uses port {ctx.settings.piper.port}: "
        f"ss -ltnp | grep {ctx.settings.piper.port}",
    )


def _kokoro_service(ctx: Context) -> Check:
    return _service(ctx, "Kokoro service", KOKORO_SERVICE)


def _kokoro_daemon(ctx: Context) -> Check:
    socket = ctx.settings.paths.kokoro_socket
    ok = socket.exists()
    return Check(
        "Kokoro daemon",
        ok,
        "ready" if ok else "not ready (still loading, or crashed)",
        f"wait ~15 s after start-up; else journalctl --user -u "
        f"{KOKORO_SERVICE} -n 30",
    )


def _speechd_socket(ctx: Context) -> Check:
    return _service(ctx, "Speech Dispatcher socket", SPEECHD_SOCKET)


def _speechd_module(ctx: Context) -> Check:
    lines = ctx.runner(("spd-say", "-O")).text.splitlines()
    modules = [m.strip() for m in lines[1:] if m.strip()]
    if SPEECHD_MODULE not in modules:
        return Check(
            "Speech Dispatcher module",
            False,
            f"{SPEECHD_MODULE} not listed ({', '.join(modules)})",
            "natural-tts apply; then systemctl --user restart "
            "speech-dispatcher.service",
        )
    if modules == [SPEECHD_MODULE]:
        return Check(
            "Speech Dispatcher module",
            False,
            "only piper-generic is listed",
            "remove active AddModule lines from "
            "~/.config/speech-dispatcher/speechd.conf",
        )
    return Check("Speech Dispatcher module", True, ", ".join(modules))


def _default_voice(ctx: Context) -> Check:
    conf = ctx.settings.paths.speechd_dir / "speechd.conf"
    text = conf.read_text() if conf.exists() else ""
    ok = any(
        line.split() == ["DefaultModule", SPEECHD_MODULE]
        for line in text.splitlines()
    )
    return Check(
        "Default voice",
        ok,
        f"DefaultModule {SPEECHD_MODULE} in {conf}"
        if ok
        else f"{SPEECHD_MODULE} is not the default in {conf}",
        "natural-tts apply",
    )


def _audio_routing(ctx: Context) -> Check:
    devices = ctx.runner(("aplay", "-L")).text.split()
    ok = "pipewire" in devices
    return Check(
        "Audio routing",
        ok,
        "ALSA routes through PipeWire" if ok else "no 'pipewire' ALSA device",
        "sudo apt install pipewire-alsa",
    )


def _clipboard_tools(ctx: Context) -> Check:
    found = [tool for tool in ("xclip", "wl-paste") if ctx.which(tool)]
    return Check(
        "Clipboard tools",
        "xclip" in found,
        ", ".join(found) or "none found",
        "sudo apt install xclip wl-clipboard",
    )


def _hotkeys(ctx: Context) -> Check:
    result = ctx.runner(
        ("gsettings", "get", MEDIA_KEYS_SCHEMA, CUSTOM_LIST_KEY)
    )
    if not result.ok:
        return Check("Hotkeys", True, "not GNOME; bind keys in your desktop")
    missing = [h.name for h in HOTKEYS if h.path not in result.text]
    return Check(
        "Hotkeys",
        not missing,
        f"missing: {', '.join(missing)}" if missing else "Super+Alt+R / C / S",
        "natural-tts setup",
    )


CHECKS: tuple[Callable[[Context], Check], ...] = (
    _installation,
    _piper_voice,
    _piper_service,
    _piper_server,
    _kokoro_service,
    _kokoro_daemon,
    _speechd_socket,
    _speechd_module,
    _default_voice,
    _audio_routing,
    _clipboard_tools,
    _hotkeys,
)


def run_checks(ctx: Context) -> list[Check]:
    """Run every check in order."""
    return [check(ctx) for check in CHECKS]


def format_report(checks: list[Check]) -> str:
    """Render checks as a plain-text report."""
    lines = []
    for check in checks:
        lines.append(
            f"[{' ok ' if check.ok else 'FAIL'}] {check.name}: {check.detail}"
        )
        if not check.ok and check.fix:
            lines.append(f"       fix: {check.fix}")
    return "\n".join(lines)
