"""GNOME custom keyboard shortcuts for the read-aloud commands.

Shortcuts are stored through ``gsettings`` as relocatable
``custom-keybinding`` entries. Existing user shortcuts are never modified:
a clashing key combination is left unset and reported instead.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

from natural_tts.system import Runner, plain_argument, run

MEDIA_KEYS_SCHEMA = "org.gnome.settings-daemon.plugins.media-keys"
CUSTOM_SCHEMA = f"{MEDIA_KEYS_SCHEMA}.custom-keybinding"
CUSTOM_LIST_KEY = "custom-keybindings"
PATH_PREFIX = (
    "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/"
)
_FIELDS = ("name", "command", "binding")


class HotkeysUnavailableError(RuntimeError):
    """Raised when GNOME's shortcut settings are not available."""


@dataclass(frozen=True)
class Hotkey:
    """One shortcut that runs a ``natural-tts`` subcommand."""

    slug: str
    name: str
    args: tuple[str, ...]
    binding: str

    @property
    def path(self) -> str:
        """The dconf path of this shortcut."""
        return f"{PATH_PREFIX}natural-tts-{self.slug}/"

    def command(self, cli: str) -> str:
        """Command line GNOME runs (GNOME does not expand ``~``)."""
        return " ".join((plain_argument(cli), *self.args))


HOTKEYS = (
    Hotkey(
        "read-selection",
        "Read selection aloud",
        ("read", "selection"),
        "<Super><Alt>r",
    ),
    Hotkey(
        "read-clipboard",
        "Read clipboard aloud",
        ("read", "clipboard"),
        "<Super><Alt>c",
    ),
    Hotkey("stop", "Stop reading aloud", ("stop",), "<Super><Alt>s"),
)


def gvariant_string(value: str) -> str:
    """Quote ``value`` as a GVariant string literal."""
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def _gvariant_list(values: list[str]) -> str:
    if not values:
        return "@as []"
    return "[" + ", ".join(gvariant_string(v) for v in values) + "]"


def parse_string_list(raw: str) -> list[str]:
    """Parse gsettings' printed form of a string array.

    Raises:
        ValueError: if ``raw`` is not a string array.
    """
    raw = raw.strip().removeprefix("@as ")
    try:
        value = ast.literal_eval(raw)
    except (ValueError, SyntaxError) as exc:
        raise ValueError(f"not a gsettings string list: {raw!r}") from exc
    if not isinstance(value, list) or not all(
        isinstance(v, str) for v in value
    ):
        raise ValueError(f"not a gsettings string list: {raw!r}")
    return value


def _pretty(binding: str) -> str:
    """'<Super><Alt>r' -> 'Super+Alt+R'."""
    parts = binding.replace(">", "> ").split()
    return "+".join(
        p.strip("<>").capitalize() if p.startswith("<") else p.upper()
        for p in parts
    )


class _Gsettings:
    def __init__(self, runner: Runner) -> None:
        self._runner = runner

    def _call(self, *args: str) -> str:
        argv = ("gsettings", *args)
        result = self._runner(argv)
        if not result.ok:
            raise HotkeysUnavailableError(
                "GNOME custom shortcuts are not available "
                f"({result.describe(argv)})"
            )
        return result.text.strip()

    def paths(self) -> list[str]:
        return parse_string_list(
            self._call("get", MEDIA_KEYS_SCHEMA, CUSTOM_LIST_KEY)
        )

    def set_paths(self, paths: list[str]) -> None:
        self._call(
            "set", MEDIA_KEYS_SCHEMA, CUSTOM_LIST_KEY, _gvariant_list(paths)
        )

    def get(self, path: str, key: str) -> str:
        raw = self._call("get", f"{CUSTOM_SCHEMA}:{path}", key)
        value = ast.literal_eval(raw) if raw else ""
        return value if isinstance(value, str) else ""

    def set(self, path: str, key: str, value: str) -> None:
        self._call(
            "set", f"{CUSTOM_SCHEMA}:{path}", key, gvariant_string(value)
        )

    def reset(self, path: str, key: str) -> None:
        self._call("reset", f"{CUSTOM_SCHEMA}:{path}", key)


def install_hotkeys(cli: str, runner: Runner = run) -> list[str]:
    """Add (or refresh) the natural-tts shortcuts.

    Returns:
        Warnings about key combinations already used by other shortcuts.

    Raises:
        HotkeysUnavailableError: if not running GNOME.
        ValueError: if ``cli`` would need quoting.
    """
    commands = {hotkey.slug: hotkey.command(cli) for hotkey in HOTKEYS}
    gs = _Gsettings(runner)
    ours = {hotkey.path for hotkey in HOTKEYS}
    existing = gs.paths()
    taken = {
        gs.get(path, "binding").lower(): gs.get(path, "name") or path
        for path in existing
        if path not in ours
    }
    warnings = []
    for hotkey in HOTKEYS:
        gs.set(hotkey.path, "name", hotkey.name)
        gs.set(hotkey.path, "command", commands[hotkey.slug])
        owner = taken.get(hotkey.binding.lower())
        if owner is None:
            gs.set(hotkey.path, "binding", hotkey.binding)
        else:
            gs.reset(hotkey.path, "binding")
            warnings.append(
                f"{_pretty(hotkey.binding)} is already used by '{owner}'; "
                f"set a key for '{hotkey.name}' in Settings > Keyboard."
            )
    gs.set_paths(
        existing + [p for p in (h.path for h in HOTKEYS) if p not in existing]
    )
    return warnings


def uninstall_hotkeys(runner: Runner = run) -> None:
    """Remove the natural-tts shortcuts; a no-op outside GNOME."""
    gs = _Gsettings(runner)
    try:
        existing = gs.paths()
    except HotkeysUnavailableError:
        return
    ours = {hotkey.path for hotkey in HOTKEYS}
    gs.set_paths([p for p in existing if p not in ours])
    for hotkey in HOTKEYS:
        for key in _FIELDS:
            gs.reset(hotkey.path, key)
