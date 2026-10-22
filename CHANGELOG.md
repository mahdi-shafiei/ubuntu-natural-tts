# Changelog

All notable changes are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.3.0] - 2026-10-22

### Added

- Structure on the hotkey path: headings, list items (numbered when the
  list is), quotes and tables are spoken as their own segments with
  pauses and a slower heading rate; tables announce their shape first.
  Markdown is read from its block structure, and the selection's HTML is
  used when the application offers it (Firefox does; Chromium offers
  plain text), parsed with the standard library and never fetched.
- Code blocks are read aloud at `reading.code_level` 1, 2 or 3:
  identifiers split into words, numbers spoken, strings and comments read
  as words, operators by name, brackets and indentation from level 2.
  Code is recognised in Markdown fences and indented blocks, HTML `pre`,
  reStructuredText literal blocks and code directives, LaTeX verbatim,
  lstlisting and minted, Org mode and AsciiDoc source blocks, Python and
  IPython prompts, terminal transcripts, unified diffs, a shebang, and
  dense unmarked code. Inline code is read the same way inside prose.
- Messages between the hotkey and the daemon carry their format.

### Changed

- Non-English Kokoro voices now get the structure (segments, pauses,
  code reading) while the English word rules stay English-only.
- `markdown-it-py` and `Pygments`, already present through Kokoro's
  dependencies, are declared in the `kokoro` and `dev` extras. The core
  package and the Speech Dispatcher path stay standard-library only,
  which a test now proves.
- The code voice is the reading voice; there is no `code_voice` setting.

## [0.2.1] - 2026-10-22

### Fixed

- The first segment of a long selection no longer waits for the whole
  text to be cleaned: windows are cut on the raw text and cleaned one at
  a time, and the built-in lexicon is compiled once. On a slow machine
  the 1 MiB case took 76 ms before the first word; it now takes about
  5 ms.

## [0.2.0] - 2026-10-22

### Added

- Content-aware reading on the Kokoro hotkey path (`[reading]` in
  `settings.toml`, on by default for English voices): numbers, dates,
  times, versions, currency, units with SI prefixes, ranges, scientific
  notation, scholarly and general abbreviations (`Fig. 3` is "Figure
  three", `et al.` stays "et al", `St. Louis` is "Saint Louis"), math
  symbols and Greek letters, chemical formulas and gene-style tokens are
  spoken as words; URLs read as their domain and path; citation markers
  such as `[12]` are skipped (`citations = "read"` says them). Markdown
  links no longer vanish into Kokoro's pronunciation syntax.
- A pronunciation lexicon for species names, Latin phrases and gene or
  method names (`E. coli`, `in vitro`, `Cas9`), with a user file at
  `~/.config/natural-tts/lexicon.toml` merged on top.
- Segments: the engine speaks typed segments with their own pause, speed
  and voice, prepared lazily so a long selection starts as fast as a
  short one.

### Changed

- `natural-tts setup` writes booleans as TOML literals in the settings
  template.

## [0.1.2] - 2026-10-21

### Fixed

- `natural-tts setup` (and so `./install.sh`) restarts the Piper and
  Kokoro services instead of only enabling them, so an upgrade with
  `git pull && ./install.sh` takes effect without a reboot. A service
  that fails to restart is now reported instead of ignored.
- The Kokoro chunker no longer ends a chunk after English
  abbreviations such as `Dr.`, `Fig.`, `Eq.` and `et al.`, after a
  single-letter initial, or at punctuation inside matched brackets, so
  `(n = 3; p < 0.05)` is read in one breath.

## [0.1.1] - 2026-10-21

### Changed

- README: each engine's sample now plays inline as a waveform video
  that lights up as it is spoken, followed by a table comparing the
  engines' sound, role, hardware, model size and license.
- `scripts/make-samples.sh` regenerates the MP3 samples and calls the
  new `scripts/render_samples.py`, which renders the three videos with
  ffmpeg alone (from PATH, `--ffmpeg`, or the `imageio-ffmpeg` package).

## [0.1.0] - 2026-10-21

### Added

- `install.sh`: one-command installation on Ubuntu with CPU or CUDA
  PyTorch; the ALSA plugin package is chosen to match the running sound
  server (PipeWire or PulseAudio).
- Piper as the system-wide Speech Dispatcher voice, served from a
  localhost-only HTTP server so each sentence starts quickly; the
  speed slider in Firefox Reader View controls Piper's speed.
- Kokoro read-aloud daemon with GNOME hotkeys: Super+Alt+R (highlighted
  text), Super+Alt+C (clipboard) and Super+Alt+S (stop).
- PDF-aware text chunking: hyphenated line breaks are re-joined and
  chunks are sized for natural Kokoro prosody.
- `natural-tts doctor`: checks every component and prints fixes.
- `natural-tts setup`, `apply` and `teardown`, driven by a single
  `~/.config/natural-tts/settings.toml`.

[Unreleased]: https://github.com/mahdi-shafiei/ubuntu-natural-tts/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/mahdi-shafiei/ubuntu-natural-tts/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/mahdi-shafiei/ubuntu-natural-tts/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/mahdi-shafiei/ubuntu-natural-tts/compare/v0.1.2...v0.2.0
[0.1.2]: https://github.com/mahdi-shafiei/ubuntu-natural-tts/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/mahdi-shafiei/ubuntu-natural-tts/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/mahdi-shafiei/ubuntu-natural-tts/releases/tag/v0.1.0
