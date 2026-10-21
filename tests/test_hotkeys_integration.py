"""Exercise the hotkey code against the real gsettings and GNOME schemas.

Runs only where GNOME's media-keys schema and a D-Bus session are present,
e.g. ``dbus-run-session -- pytest -m integration`` with dconf installed.
"""

import os
import shutil

import pytest

from natural_tts.hotkeys import (
    CUSTOM_LIST_KEY,
    HOTKEYS,
    MEDIA_KEYS_SCHEMA,
    install_hotkeys,
    uninstall_hotkeys,
)
from natural_tts.system import run

CLI = "/opt/natural-tts/bin/natural-tts"


def _gnome_available() -> bool:
    if not shutil.which("gsettings") or "DBUS_SESSION_BUS_ADDRESS" not in (
        os.environ
    ):
        return False
    schemas = run(["gsettings", "list-schemas"])
    return schemas.ok and MEDIA_KEYS_SCHEMA in schemas.text.split()


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _gnome_available(),
        reason="needs gsettings, GNOME schemas and D-Bus",
    ),
]


def _get(schema: str, key: str) -> str:
    return run(["gsettings", "get", schema, key]).text.strip()


def test_install_and_uninstall_with_real_gsettings():
    user_path = (
        "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/"
        "custom0/"
    )
    custom = f"{MEDIA_KEYS_SCHEMA}.custom-keybinding:{user_path}"
    run(
        [
            "gsettings",
            "set",
            MEDIA_KEYS_SCHEMA,
            CUSTOM_LIST_KEY,
            f"['{user_path}']",
        ]
    )
    run(["gsettings", "set", custom, "name", "'Terminal'"])
    run(["gsettings", "set", custom, "binding", "'<Super><Alt>s'"])
    try:
        warnings = install_hotkeys(CLI)
        assert len(warnings) == 1 and "Super+Alt+S" in warnings[0]
        listed = _get(MEDIA_KEYS_SCHEMA, CUSTOM_LIST_KEY)
        for hotkey in HOTKEYS:
            assert hotkey.path in listed
        read = HOTKEYS[0]
        schema = f"{MEDIA_KEYS_SCHEMA}.custom-keybinding:{read.path}"
        assert _get(schema, "command") == f"'{CLI} read selection'"
        assert _get(schema, "binding") == "'<Super><Alt>r'"

        uninstall_hotkeys()
        assert _get(MEDIA_KEYS_SCHEMA, CUSTOM_LIST_KEY) == f"['{user_path}']"
        assert _get(schema, "command") == "''"
    finally:
        run(["gsettings", "reset", MEDIA_KEYS_SCHEMA, CUSTOM_LIST_KEY])
        for key in ("name", "binding"):
            run(["gsettings", "reset", custom, key])
