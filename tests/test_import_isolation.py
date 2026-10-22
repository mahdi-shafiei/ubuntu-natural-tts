"""The Speech Dispatcher path must import without the hotkey path's extras.

`piper-speak` runs once per spoken sentence, so `natural_tts.piper`,
`natural_tts.cli` and `natural_tts.speechd` must load with only the
standard library: no Kokoro, no markdown-it-py, no Pygments.
"""

import subprocess
import sys

import pytest

BLOCKED = ("kokoro", "markdown_it", "pygments", "sounddevice", "numpy")
_SCRIPT = """
import importlib, sys
class Blocker:
    def __init__(self, names): self.names = names
    def find_spec(self, name, path=None, target=None):
        for blocked in self.names:
            if name == blocked or name.startswith(blocked + "."):
                raise ImportError(f"blocked: {name}")
        return None
sys.meta_path.insert(0, Blocker(set(sys.argv[2:])))
importlib.import_module(sys.argv[1])
print("ok")
"""


def try_import(
    module: str, blocked: tuple[str, ...]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", _SCRIPT, module, *blocked],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    "module", ["natural_tts.piper", "natural_tts.cli", "natural_tts.speechd"]
)
def test_system_voice_modules_import_without_the_extras(module):
    result = try_import(module, BLOCKED)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


def test_the_blocker_itself_works():
    # Positive control: blocking a module the CLI needs must fail the import.
    result = try_import("natural_tts.cli", ("natural_tts.text",))
    assert result.returncode != 0
    assert "blocked: natural_tts.text" in result.stderr
