"""Central settings, paths and constants.

Every other module reads its configuration from here, so changing a voice or
a port is a one-line edit in ``~/.config/natural-tts/settings.toml``.
"""

from __future__ import annotations

import dataclasses
import os
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar, get_type_hints

APP_NAME = "natural-tts"

# Kokoro always produces 24 kHz mono audio.
KOKORO_SAMPLE_RATE = 24_000
KOKORO_REPO_ID = "hexgrad/Kokoro-82M"

# Kokoro is weakest on very short inputs and rushes on very long ones (its
# VOICES.md recommends roughly 100-200 phoneme tokens), so text is chunked to
# a short-but-not-tiny first piece followed by pieces of a few sentences.
FIRST_CHUNK_MIN_CHARS = 60
CHUNK_MAX_CHARS = 300

# Speech Dispatcher names an auto-detected generic module after its file.
SPEECHD_MODULE = "piper-generic"
PIPER_SERVICE = "natural-tts-piper.service"
KOKORO_SERVICE = "natural-tts-kokoro.service"
SERVICES = (PIPER_SERVICE, KOKORO_SERVICE)

_PIPER_VOICE_RE = re.compile(
    r"^[a-z]{2,3}_[A-Z]{2}-[A-Za-z0-9_]+-(x_low|low|medium|high)$"
)
# Kokoro voice ids: <language letter><f|m>_<name>, e.g. af_heart, bm_george.
_KOKORO_VOICE_RE = re.compile(r"^[abefhijpz][fm]_[a-z]+$")


class SettingsError(ValueError):
    """Raised when settings.toml contains an invalid value."""


@dataclass(frozen=True)
class Paths:
    """Filesystem locations used by natural-tts (XDG layout)."""

    home: Path
    data_dir: Path
    config_dir: Path
    xdg_config_home: Path
    runtime_dir: Path

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str],
        home: Path | None = None,
        uid: int | None = None,
    ) -> Paths:
        """Resolve paths from XDG environment variables.

        Args:
            env: Environment mapping (normally ``os.environ``).
            home: Home directory; defaults to ``Path.home()``.
            uid: User id for the runtime-dir fallback; defaults to the
                current user.
        """
        home = home if home is not None else Path.home()
        data_home = Path(env.get("XDG_DATA_HOME") or home / ".local/share")
        config_home = Path(env.get("XDG_CONFIG_HOME") or home / ".config")
        runtime = env.get("XDG_RUNTIME_DIR")
        if runtime:
            runtime_dir = Path(runtime) / APP_NAME
        else:
            uid = os.getuid() if uid is None else uid
            runtime_dir = Path(f"/tmp/{APP_NAME}-{uid}")
        return cls(
            home=home,
            data_dir=data_home / APP_NAME,
            config_dir=config_home / APP_NAME,
            xdg_config_home=config_home,
            runtime_dir=runtime_dir,
        )

    @property
    def venv(self) -> Path:
        """Virtual environment holding Piper, Kokoro and this package."""
        return self.data_dir / "venv"

    @property
    def venv_python(self) -> Path:
        """Python interpreter inside the virtual environment."""
        return self.venv / "bin/python"

    @property
    def cli(self) -> Path:
        """The ``natural-tts`` command inside the virtual environment."""
        return self.venv / "bin/natural-tts"

    @property
    def voices_dir(self) -> Path:
        """Directory holding downloaded Piper voices."""
        return self.data_dir / "voices"

    @property
    def settings_file(self) -> Path:
        """User settings file."""
        return self.config_dir / "settings.toml"

    @property
    def kokoro_socket(self) -> Path:
        """Unix socket the Kokoro daemon listens on."""
        return self.runtime_dir / "kokoro.sock"

    @property
    def systemd_user_dir(self) -> Path:
        """Directory for systemd user units."""
        return self.xdg_config_home / "systemd/user"

    @property
    def speechd_dir(self) -> Path:
        """Per-user Speech Dispatcher configuration directory."""
        return self.xdg_config_home / "speech-dispatcher"


def _type_error(qualified: str, kind: type) -> SettingsError:
    return SettingsError(f"{qualified} must be {kind.__name__}")


@dataclass(frozen=True)
class PiperSettings:
    """Piper (system voice) settings."""

    # LJ Speech is public domain; voices such as en_US-lessac are trained on
    # research-only datasets, so they are opt-in.
    voice: str = "en_US-ljspeech-high"
    port: int = 5150
    length_scale: float = 1.05
    sentence_silence: float = 0.25

    def __post_init__(self) -> None:
        """Validate values."""
        if not _PIPER_VOICE_RE.match(self.voice):
            raise SettingsError(
                f"piper.voice {self.voice!r} is not a Piper voice name "
                "like 'en_US-ljspeech-high'"
            )
        if not 1024 <= self.port <= 65535:
            raise SettingsError("piper.port must be in 1024..65535")
        if self.length_scale <= 0:
            raise SettingsError("piper.length_scale must be > 0")
        if self.sentence_silence < 0:
            raise SettingsError("piper.sentence_silence must be >= 0")


@dataclass(frozen=True)
class KokoroSettings:
    """Kokoro (read-anything hotkey voice) settings."""

    voice: str = "af_heart"
    speed: float = 1.0

    def __post_init__(self) -> None:
        """Validate values."""
        if not _KOKORO_VOICE_RE.match(self.voice):
            raise SettingsError(
                f"kokoro.voice {self.voice!r} is not a Kokoro voice id "
                "like 'af_heart'"
            )
        if not 0.5 <= self.speed <= 2.0:
            raise SettingsError("kokoro.speed must be in 0.5..2.0")

    @property
    def lang_code(self) -> str:
        """Kokoro pipeline language code (first letter of the voice id)."""
        return self.voice[0]


@dataclass(frozen=True)
class Settings:
    """All natural-tts settings."""

    paths: Paths
    piper: PiperSettings = field(default_factory=PiperSettings)
    kokoro: KokoroSettings = field(default_factory=KokoroSettings)

    @property
    def piper_model(self) -> Path:
        """Path of the selected Piper voice model."""
        return self.paths.voices_dir / f"{self.piper.voice}.onnx"


_SECTIONS: dict[str, type[PiperSettings] | type[KokoroSettings]] = {
    "piper": PiperSettings,
    "kokoro": KokoroSettings,
}
_SectionT = TypeVar("_SectionT", PiperSettings, KokoroSettings)


def _coerce(qualified: str, value: Any, kind: type) -> Any:
    # bool is a subclass of int; reject it explicitly for numeric fields.
    if isinstance(value, bool) and kind is not bool:
        raise _type_error(qualified, kind)
    if kind is float and isinstance(value, int):
        return float(value)
    if not isinstance(value, kind):
        raise _type_error(qualified, kind)
    return value


def _build_section(
    name: str, cls: type[_SectionT], data: Mapping[str, Any]
) -> _SectionT:
    kinds = get_type_hints(cls)
    values: dict[str, Any] = {}
    for key, value in data.items():
        qualified = f"{name}.{key}"
        if key not in kinds:
            raise SettingsError(f"unknown key {qualified!r}")
        values[key] = _coerce(qualified, value, kinds[key])
    return cls(**values)


def load_settings(paths: Paths) -> Settings:
    """Load settings.toml (if present) on top of the defaults.

    Raises:
        SettingsError: if the file is not valid TOML or a value is invalid.
    """
    if not paths.settings_file.exists():
        return Settings(paths=paths)
    try:
        data = tomllib.loads(paths.settings_file.read_text())
    except tomllib.TOMLDecodeError as exc:
        raise SettingsError(
            f"invalid TOML in {paths.settings_file}: {exc}"
        ) from exc
    for section in data:
        if section not in _SECTIONS:
            raise SettingsError(f"unknown section {section!r}")
    return Settings(
        paths=paths,
        piper=_build_section("piper", PiperSettings, data.get("piper", {})),
        kokoro=_build_section("kokoro", KokoroSettings, data.get("kokoro", {})),
    )


_FIELD_HELP = {
    "piper.voice": "Piper voice, see https://rhasspy.github.io/piper-samples/",
    "piper.port": "local port of the Piper server (bound to 127.0.0.1)",
    "piper.length_scale": "speed: higher is slower (1.0 = voice default)",
    "piper.sentence_silence": "pause after each sentence, in seconds",
    "kokoro.voice": "af_heart, af_bella, af_nicole, bf_emma, am_michael, ...",
    "kokoro.speed": "0.5 .. 2.0 (1.0 = normal)",
}


def _render_settings_toml() -> str:
    lines = [
        "# natural-tts settings. Apply changes with: natural-tts apply",
        "",
    ]
    for name, cls in _SECTIONS.items():
        lines.append(f"[{name}]")
        for f in dataclasses.fields(cls):
            value = f.default
            literal = f'"{value}"' if isinstance(value, str) else repr(value)
            lines.append(f"# {_FIELD_HELP[f'{name}.{f.name}']}")
            lines.append(f"{f.name} = {literal}")
        lines.append("")
    return "\n".join(lines)


DEFAULT_SETTINGS_TOML = _render_settings_toml()
