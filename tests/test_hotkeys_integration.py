"""Exercise the hotkey code against real gsettings and GNOME schemas.

The work happens on a **private** D-Bus session with a **private** dconf
database (``dbus-run-session`` plus a temporary ``XDG_CONFIG_HOME``), so the
desktop's own shortcuts are never read or written. Before 0.4.1 this test
ran on the developer's session bus and its cleanup reset the user's whole
custom-shortcut list; the positive control below fails if that isolation
is ever lost. Skipped where gsettings, the media-keys schema or
``dbus-run-session`` are missing.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from natural_tts.hotkeys import MEDIA_KEYS_SCHEMA
from natural_tts.system import run

CLI = "/opt/natural-tts/bin/natural-tts"
_TOOLS = ("gsettings", "dbus-run-session")


def _gnome_available() -> bool:
    if not all(shutil.which(tool) for tool in _TOOLS):
        return False
    schemas = run(["gsettings", "list-schemas"])
    return schemas.ok and MEDIA_KEYS_SCHEMA in schemas.text.split()


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _gnome_available(),
        reason="needs gsettings, the GNOME media-keys schema and dbus-run-session",
    ),
]

# Runs inside the private session: the user's bus and dconf are not reachable.
_SCRIPT = f'''
import sys
from natural_tts.hotkeys import (
    CUSTOM_LIST_KEY, HOTKEYS, MEDIA_KEYS_SCHEMA, install_hotkeys, uninstall_hotkeys,
)
from natural_tts.system import run

def get(schema, key):
    return run(["gsettings", "get", schema, key]).text.strip()

user_path = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom0/"
custom = f"{{MEDIA_KEYS_SCHEMA}}.custom-keybinding:{{user_path}}"
assert get(MEDIA_KEYS_SCHEMA, CUSTOM_LIST_KEY) == "@as []", "dconf is not private"
run(["gsettings", "set", MEDIA_KEYS_SCHEMA, CUSTOM_LIST_KEY, f"['{{user_path}}']"])
run(["gsettings", "set", custom, "name", "'Terminal'"])
run(["gsettings", "set", custom, "binding", "'<Super><Alt>s'"])
warnings = install_hotkeys({CLI!r})
assert len(warnings) == 1 and "Super+Alt+S" in warnings[0], warnings
listed = get(MEDIA_KEYS_SCHEMA, CUSTOM_LIST_KEY)
for hotkey in HOTKEYS:
    assert hotkey.path in listed, (hotkey.path, listed)
schema = f"{{MEDIA_KEYS_SCHEMA}}.custom-keybinding:{{HOTKEYS[0].path}}"
assert get(schema, "command") == "'{CLI} read selection'"
assert get(schema, "binding") == "'<Super><Alt>r'"
uninstall_hotkeys()
assert get(MEDIA_KEYS_SCHEMA, CUSTOM_LIST_KEY) == f"['{{user_path}}']"
assert get(schema, "command") == "''"
print("ok")
'''


def _private_session(script: str, config_home: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, XDG_CONFIG_HOME=str(config_home))
    env.pop("DBUS_SESSION_BUS_ADDRESS", None)
    return subprocess.run(
        ["dbus-run-session", "--", sys.executable, "-c", script],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def _desktop_list() -> str | None:
    if "DBUS_SESSION_BUS_ADDRESS" not in os.environ:
        return None
    result = run(["gsettings", "get", MEDIA_KEYS_SCHEMA, "custom-keybindings"])
    return result.text.strip() if result.ok else None


def test_install_and_uninstall_with_real_gsettings(tmp_path):
    before = _desktop_list()
    result = _private_session(_SCRIPT, tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"
    # Positive control for the isolation: the desktop's list is untouched.
    assert _desktop_list() == before


def test_private_session_is_really_private(tmp_path):
    marker = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/probe/"
    script = (
        "from natural_tts.system import run\n"
        f"run(['gsettings', 'set', {MEDIA_KEYS_SCHEMA!r}, 'custom-keybindings', \"['{marker}']\"])\n"
        f"print(run(['gsettings', 'get', {MEDIA_KEYS_SCHEMA!r}, 'custom-keybindings']).text.strip())\n"
    )
    before = _desktop_list()
    result = _private_session(script, tmp_path)
    assert result.returncode == 0, result.stderr
    assert marker in result.stdout
    assert (tmp_path / "dconf" / "user").exists()
    assert _desktop_list() == before
