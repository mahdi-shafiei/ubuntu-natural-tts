# Contributing

Thanks for helping make Linux speak better. Bug reports, voice
recommendations, distribution support and code are all welcome.

## Reporting a problem

Please include the output of `natural-tts doctor`, your distribution and
version, your desktop (GNOME, KDE, ...) and session type
(`echo $XDG_SESSION_TYPE`). The bug-report template asks for these.

## Development setup

```bash
git clone https://github.com/mahdi-shafiei/ubuntu-natural-tts.git
cd ubuntu-natural-tts
uv venv --python 3.12
uv pip install -e ".[dev]"
uv run pre-commit install
```

Run the checks:

```bash
uv run pre-commit run --all-files                  # everything CI runs
uv run pytest                                      # unit tests + coverage gate
dbus-run-session -- uv run pytest -m integration   # real gsettings/GNOME schemas
```

The unit tests need no audio hardware, Kokoro model or desktop session.

## How the code is organised

| Module | Responsibility |
|---|---|
| `config.py` | Settings file, validation, XDG paths, shared constants |
| `text.py` | Decoding and chunking text for synthesis |
| `system.py` | The one place external programs are run |
| `selection.py` | Reading the highlighted text or the clipboard |
| `ipc.py` | Private Unix-socket messaging with the daemon |
| `piper.py`, `audio.py` | Piper client and WAV playback |
| `engine.py` | Cancellable, self-healing playback engine |
| `kokoro_backend.py` | Thin adapters for Kokoro and sounddevice |
| `daemon.py` | The read-aloud daemon loop |
| `speechd.py`, `systemd.py`, `hotkeys.py` | Desktop integration |
| `doctor.py` | Diagnostics |
| `cli.py` | The `natural-tts` command |

## Guidelines

- **Tests first.** Write a failing test that describes the behavior, then
  make it pass. Do not change a test to fit a flawed implementation.
- **Inject system access.** Anything that touches processes, files outside
  a temporary directory, sockets or audio takes a parameter (for example a
  `Runner`) so tests can pass a fake; shared fakes live in `tests/fakes.py`.
- **Keep it typed and documented.** mypy runs in strict mode, public
  functions have docstrings, lines stay within 80 columns (ruff).
- **Keep the per-sentence path light.** `natural-tts piper-speak`, `read`,
  `say` and `stop` must import only the standard library.
- **One source of truth.** Settings belong in `config.py` and
  `settings.toml`; generated files (units, Speech Dispatcher module) are
  derived from them.

## Commits and pull requests

- One logical change per commit; every commit passes the checks.
- Messages follow [Conventional Commits](https://www.conventionalcommits.org/):
  `feat(hotkeys): ...`, `fix(speechd): ...`, `docs: ...`, `test: ...`,
  with a body explaining why for anything non-trivial.
- Update tests and documentation in the same commit as the behavior.
- Add a line to `CHANGELOG.md` under "Unreleased" for user-visible changes.
