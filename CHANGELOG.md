# Changelog

All notable changes are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

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

[Unreleased]: https://github.com/mahdi-shafiei/ubuntu-natural-tts/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/mahdi-shafiei/ubuntu-natural-tts/releases/tag/v0.1.0
