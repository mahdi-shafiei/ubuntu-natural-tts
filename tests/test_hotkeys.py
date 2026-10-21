import pytest

from natural_tts.hotkeys import (
    CUSTOM_LIST_KEY,
    CUSTOM_SCHEMA,
    MEDIA_KEYS_SCHEMA,
    PATH_PREFIX,
    HotkeysUnavailableError,
    gvariant_string,
    install_hotkeys,
    parse_string_list,
    uninstall_hotkeys,
)
from natural_tts.system import Result

CLI = "/home/u/.local/share/natural-tts/venv/bin/natural-tts"
USER_PATH = f"{PATH_PREFIX}custom0/"


class FakeGsettings:
    """In-memory gsettings that speaks the real CLI's argument formats."""

    def __init__(self, gnome=True):
        self.gnome = gnome
        self.values: dict[tuple[str, str], str] = {}
        self.calls = []

    def __call__(self, argv, *, stdin=None, timeout=None):
        self.calls.append(tuple(argv))
        assert argv[0] == "gsettings"
        op, rest = argv[1], argv[2:]
        if not self.gnome:
            return Result(1, b"", b"No such schema")
        if op == "get":
            schema, key = rest
            default = "@as []" if key == CUSTOM_LIST_KEY else "''"
            value = self.values.get((schema, key), default)
            return Result(0, (value + "\n").encode(), b"")
        if op == "set":
            schema, key, value = rest
            self.values[(schema, key)] = value
            return Result(0, b"", b"")
        if op == "reset":
            schema, key = rest
            self.values.pop((schema, key), None)
            return Result(0, b"", b"")
        raise AssertionError(argv)

    def custom(self, path, key):
        return self.values.get((f"{CUSTOM_SCHEMA}:{path}", key))

    def paths(self):
        raw = self.values.get((MEDIA_KEYS_SCHEMA, CUSTOM_LIST_KEY), "@as []")
        return parse_string_list(raw)

    def add_user_shortcut(self, binding):
        self.values[(MEDIA_KEYS_SCHEMA, CUSTOM_LIST_KEY)] = f"['{USER_PATH}']"
        schema = f"{CUSTOM_SCHEMA}:{USER_PATH}"
        self.values[(schema, "name")] = "'Terminal'"
        self.values[(schema, "binding")] = f"'{binding}'"


class TestGvariant:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("@as []", []),
            ("[]", []),
            ("['/a/', '/b/']", ["/a/", "/b/"]),
            ("['/it\\'s/']", ["/it's/"]),
        ],
    )
    def test_parse_string_list(self, raw, expected):
        assert parse_string_list(raw) == expected

    def test_parse_rejects_garbage(self):
        with pytest.raises(ValueError):
            parse_string_list("not a list")

    def test_string_quoting_round_trips(self):
        assert gvariant_string("it's \\ ok") == "'it\\'s \\\\ ok'"


class TestInstall:
    def test_adds_three_shortcuts(self):
        g = FakeGsettings()
        warnings = install_hotkeys(CLI, g)
        assert warnings == []
        paths = g.paths()
        assert len(paths) == 3 and all(p.startswith(PATH_PREFIX) for p in paths)
        commands = sorted(g.custom(p, "command") for p in paths)
        assert commands == sorted(
            [
                f"'{CLI} read clipboard'",
                f"'{CLI} read selection'",
                f"'{CLI} stop'",
            ]
        )
        bindings = {g.custom(p, "binding") for p in paths}
        assert bindings == {
            "'<Super><Alt>r'",
            "'<Super><Alt>c'",
            "'<Super><Alt>s'",
        }

    def test_keeps_existing_user_shortcuts(self):
        g = FakeGsettings()
        g.add_user_shortcut("<Primary><Alt>t")
        install_hotkeys(CLI, g)
        assert g.paths()[0] == USER_PATH and len(g.paths()) == 4

    def test_is_idempotent(self):
        g = FakeGsettings()
        install_hotkeys(CLI, g)
        install_hotkeys(CLI, g)
        assert len(g.paths()) == 3

    def test_conflicting_binding_is_left_unset_with_warning(self):
        g = FakeGsettings()
        g.add_user_shortcut("<Super><Alt>R")  # case-insensitive clash
        warnings = install_hotkeys(CLI, g)
        assert len(warnings) == 1
        assert "Super+Alt+R" in warnings[0] and "Terminal" in warnings[0]
        read = next(p for p in g.paths() if p.endswith("read-selection/"))
        assert g.custom(read, "binding") is None

    def test_not_gnome_raises(self):
        with pytest.raises(HotkeysUnavailableError, match="GNOME"):
            install_hotkeys(CLI, FakeGsettings(gnome=False))

    def test_commands_with_unsafe_paths_are_rejected(self):
        with pytest.raises(ValueError, match="cannot contain"):
            install_hotkeys("/home/a b/natural-tts", FakeGsettings())


class TestUninstall:
    def test_removes_only_ours(self):
        g = FakeGsettings()
        g.add_user_shortcut("<Primary><Alt>t")
        install_hotkeys(CLI, g)
        uninstall_hotkeys(g)
        assert g.paths() == [USER_PATH]
        assert all(
            PATH_PREFIX + "natural-tts" not in schema for schema, _ in g.values
        )

    def test_not_gnome_is_a_no_op(self):
        uninstall_hotkeys(FakeGsettings(gnome=False))
