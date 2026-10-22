# Changelog

All notable changes are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

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

[Unreleased]: https://github.com/mahdi-shafiei/ubuntu-natural-tts/compare/v0.1.2...HEAD
[0.1.2]: https://github.com/mahdi-shafiei/ubuntu-natural-tts/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/mahdi-shafiei/ubuntu-natural-tts/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/mahdi-shafiei/ubuntu-natural-tts/releases/tag/v0.1.0
