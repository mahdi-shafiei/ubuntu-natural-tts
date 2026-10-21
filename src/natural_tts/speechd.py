"""Speech Dispatcher integration: makes Piper the system-wide voice.

Three details matter, all verified against Speech Dispatcher's source:

* The module file is named ``piper-generic.conf`` and *no* ``AddModule``
  line is added: any ``AddModule`` disables auto-detection and would hide
  every other installed voice.
* A user ``speechd.conf`` replaces the system one entirely, so it starts as
  a full copy of ``/etc/speech-dispatcher/speechd.conf``.
* The generic module re-encodes text to ISO-8859-1 unless a language is
  declared UTF-8, which would turn accents and dashes into "?".
"""

from __future__ import annotations

import contextlib
from pathlib import Path

from natural_tts.config import SPEECHD_MODULE, Settings
from natural_tts.system import plain_argument

SYSTEM_CONF = Path("/etc/speech-dispatcher/speechd.conf")
DEFAULT_MARKER = "# natural-tts: use Piper as the default voice"
VOICE_TYPES = (
    "MALE1",
    "MALE2",
    "MALE3",
    "FEMALE1",
    "FEMALE2",
    "FEMALE3",
    "CHILD_MALE",
    "CHILD_FEMALE",
)
# Languages declared UTF-8 regardless of the voice: requests in any other
# language are recoded to ISO-8859-1 (e.g. Firefox reading a French page).
# "c" is what Speech Dispatcher reports for the C/POSIX locale.
UTF8_LANGUAGES = (
    "c",
    "en",
    "en-US",
    "en-GB",
    "fr",
    "de",
    "es",
    "it",
    "pt",
    "nl",
    "sv",
    "da",
    "no",
    "nb",
    "fi",
    "is",
    "pl",
    "cs",
    "sk",
    "hu",
    "ro",
    "bg",
    "el",
    "ru",
    "uk",
    "be",
    "sr",
    "hr",
    "sl",
    "et",
    "lv",
    "lt",
    "tr",
    "ca",
    "eu",
    "gl",
    "ga",
    "cy",
    "ar",
    "fa",
    "he",
    "hi",
    "bn",
    "ur",
    "ta",
    "te",
    "zh",
    "ja",
    "ko",
    "vi",
    "th",
    "id",
    "ms",
    "sw",
)


def _languages(voice: str) -> tuple[str, str]:
    locale = voice.split("-", 1)[0]  # e.g. "de_DE"
    language, region = locale.split("_")
    return language, f"{language}-{region}"


def render_module_conf(settings: Settings, cli: str) -> str:
    """Render ``piper-generic.conf`` for the configured Piper voice.

    Args:
        settings: natural-tts settings.
        cli: Absolute path of the ``natural-tts`` command.

    Raises:
        ValueError: if ``cli`` contains whitespace or quotes.
    """
    cli = plain_argument(cli)
    voice = settings.piper.voice
    language, locale = _languages(voice)
    lines = [
        "# Managed by natural-tts; regenerate with: natural-tts apply",
        "Debug 0",
        # \' is dotconf's escaped quote; Speech Dispatcher itself escapes
        # apostrophes inside $DATA, so "don't" arrives intact.
        f"GenericExecuteSynth \"printf %s \\'$DATA\\' | {cli} "
        'piper-speak $RATE"',
        f'GenericCmdDependency "{cli}"',
    ]
    for code in dict.fromkeys((language, locale, *UTF8_LANGUAGES)):
        lines.append(f'GenericLanguage "{code}" "{code}" "utf-8"')
    lines += [
        f'AddVoice "{language}" "{kind}" "{voice}"' for kind in VOICE_TYPES
    ]
    return "\n".join(lines) + "\n"


def _is_active(line: str, keyword: str) -> bool:
    return line.lstrip().startswith(keyword)


def remove_default_module(text: str) -> str:
    """Remove the DefaultModule block that natural-tts added (if any)."""
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    skip_next = False
    for line in lines:
        if skip_next:
            skip_next = False
            continue
        if line.rstrip("\n") == DEFAULT_MARKER:
            skip_next = True
            continue
        out.append(line)
    return "".join(out)


def set_default_module(text: str) -> tuple[str, list[str]]:
    """Make Piper the default module in a ``speechd.conf`` text.

    Other active ``DefaultModule`` lines are removed; comments are kept.

    Returns:
        The new text and a list of warnings for the user.
    """
    text = remove_default_module(text)
    kept = [
        line
        for line in text.splitlines(keepends=True)
        if not _is_active(line, "DefaultModule")
    ]
    warnings = []
    if any(_is_active(line, "AddModule") for line in kept):
        warnings.append(
            "speechd.conf has active AddModule lines; they disable module "
            "auto-detection, so piper-generic and other voices may be "
            "missing. Comment them out unless you added them on purpose."
        )
    body = "".join(kept)
    if body and not body.endswith("\n"):
        body += "\n"
    return f"{body}{DEFAULT_MARKER}\nDefaultModule {SPEECHD_MODULE}\n", warnings


def _module_file(settings: Settings) -> Path:
    return settings.paths.speechd_dir / "modules" / f"{SPEECHD_MODULE}.conf"


def install_speechd(
    settings: Settings, cli: str, system_conf: Path = SYSTEM_CONF
) -> list[str]:
    """Install the Piper module and make it the default voice.

    Returns:
        Warnings for the user.

    Raises:
        FileNotFoundError: if there is no user config yet and the system
            config is missing (speech-dispatcher not installed).
    """
    user_conf = settings.paths.speechd_dir / "speechd.conf"
    if user_conf.exists():
        original = user_conf.read_text()
    else:
        original = system_conf.read_text()
    module = _module_file(settings)
    module.parent.mkdir(parents=True, exist_ok=True)
    module.write_text(render_module_conf(settings, cli))
    patched, warnings = set_default_module(original)
    user_conf.write_text(patched)
    return warnings


def uninstall_speechd(settings: Settings) -> None:
    """Undo ``install_speechd``, leaving the user's other settings intact."""
    with contextlib.suppress(FileNotFoundError):
        _module_file(settings).unlink()
    user_conf = settings.paths.speechd_dir / "speechd.conf"
    if user_conf.exists():
        user_conf.write_text(remove_default_module(user_conf.read_text()))
