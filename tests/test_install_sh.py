"""Tests for the testable parts of install.sh (sourced, not executed)."""

import subprocess
from pathlib import Path

import pytest

INSTALL_SH = Path(__file__).resolve().parent.parent / "install.sh"


def fake_bin(tmp_path, pactl_output=None, running=()):
    """Stub pactl and pgrep so detection runs without a sound server."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    pactl = bin_dir / "pactl"
    if pactl_output is None:
        pactl.write_text("#!/bin/sh\nexit 1\n")
    else:
        pactl.write_text(f"#!/bin/sh\nprintf '%s\\n' '{pactl_output}'\n")
    pgrep = bin_dir / "pgrep"
    names = " ".join(running)
    # The process name is pgrep's last argument (pgrep -u UID -x NAME).
    pgrep.write_text(
        "#!/bin/sh\nfor last; do :; done\nfor n in "
        + (names or "''")
        + '; do\n  [ "$last" = "$n" ] && exit 0\ndone\nexit 1\n'
    )
    for f in (pactl, pgrep):
        f.chmod(0o755)
    return bin_dir


def audio_package(bin_dir):
    script = f'source "{INSTALL_SH}"; audio_package'
    result = subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        env={"PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": "/nonexistent"},
        check=True,
    )
    return result.stdout.strip()


@pytest.mark.parametrize(
    ("pactl", "running", "expected"),
    [
        ("Server Name: PulseAudio (on PipeWire 1.0.5)", (), "pipewire-alsa"),
        ("Server Name: pulseaudio", (), "libasound2-plugins"),
        (None, ("pipewire",), "pipewire-alsa"),
        (None, ("pulseaudio",), "libasound2-plugins"),
        (None, (), ""),
    ],
)
def test_audio_package_matches_running_sound_server(
    tmp_path, pactl, running, expected
):
    assert audio_package(fake_bin(tmp_path, pactl, running)) == expected


def test_sourcing_does_not_run_the_installer(tmp_path):
    result = subprocess.run(
        ["bash", "-c", f'source "{INSTALL_SH}"; echo sourced'],
        capture_output=True,
        text=True,
        check=True,
        env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)},
    )
    assert result.stdout == "sourced\n"


def test_unknown_option_is_rejected():
    result = subprocess.run(
        ["bash", str(INSTALL_SH), "--bogus"], capture_output=True, text=True
    )
    assert result.returncode == 2 and "unknown option" in result.stderr


def test_help_lists_every_option():
    out = subprocess.run(
        ["bash", str(INSTALL_SH), "--help"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    for option in ("--gpu", "--no-hotkeys", "--no-setup", "--uninstall"):
        assert option in out
    assert "set -euo" not in out
