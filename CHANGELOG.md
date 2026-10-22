# Changelog

All notable changes are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

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

[Unreleased]: https://github.com/mahdi-shafiei/ubuntu-natural-tts/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/mahdi-shafiei/ubuntu-natural-tts/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/mahdi-shafiei/ubuntu-natural-tts/compare/v0.1.2...v0.2.0
[0.1.2]: https://github.com/mahdi-shafiei/ubuntu-natural-tts/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/mahdi-shafiei/ubuntu-natural-tts/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/mahdi-shafiei/ubuntu-natural-tts/releases/tag/v0.1.0
