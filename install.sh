#!/usr/bin/env bash
# Install natural-tts: natural-sounding, system-wide text-to-speech for
# Ubuntu (Piper for the system voice, Kokoro for read-anything hotkeys).
#
# Usage: ./install.sh [--gpu] [--no-hotkeys] [--no-setup] [--uninstall]
#   --gpu         install the CUDA build of PyTorch (NVIDIA GPUs); default CPU
#   --no-hotkeys  do not add GNOME keyboard shortcuts
#   --no-setup    install files only; skip services, Speech Dispatcher, hotkeys
#   --uninstall   remove services, config changes and installed files

PYTHON_VERSION="3.12" # Kokoro requires Python < 3.13
TORCH_CPU_INDEX="https://download.pytorch.org/whl/cpu"
APT_PACKAGES=(espeak-ng speech-dispatcher alsa-utils libportaudio2
  xclip wl-clipboard libnotify-bin)

# Must match natural_tts.config.Paths (checked after installation).
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/natural-tts"
VENV="$DATA_DIR/venv"
CLI="$VENV/bin/natural-tts"
LINK="$HOME/.local/bin/natural-tts"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[33mwarning:\033[0m %s\n' "$*" >&2; }
die() {
  printf '\033[31merror:\033[0m %s\n' "$*" >&2
  exit 1
}

# Print the ALSA plugin package that routes plain-ALSA audio (aplay,
# PortAudio) to the running sound server, or nothing if none is running.
# pipewire-alsa conflicts with pulseaudio, so it must never be installed on
# a PulseAudio system: apt would remove PulseAudio.
audio_package() {
  local info
  if info="$(pactl info 2>/dev/null)"; then
    if [[ "$info" == *"on PipeWire"* ]]; then
      echo pipewire-alsa
    else
      echo libasound2-plugins
    fi
  elif pgrep -u "$(id -u)" -x pipewire >/dev/null 2>&1; then
    echo pipewire-alsa
  elif pgrep -u "$(id -u)" -x pulseaudio >/dev/null 2>&1; then
    echo libasound2-plugins
  fi
}

usage() { sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; }

uninstall() {
  step "Removing natural-tts"
  if [[ -x "$CLI" ]]; then "$CLI" teardown || true; fi
  rm -rf "$DATA_DIR"
  if [[ -L "$LINK" ]]; then rm -f "$LINK"; fi
  echo "Done. Settings remain in ${XDG_CONFIG_HOME:-$HOME/.config}/natural-tts"
}

install_system_packages() {
  local packages=("${APT_PACKAGES[@]}") audio
  audio="$(audio_package)"
  if [[ -n "$audio" ]]; then
    packages+=("$audio")
  else
    warn "no running PipeWire or PulseAudio found; install pipewire-alsa" \
      "(PipeWire) or libasound2-plugins (PulseAudio) yourself"
  fi
  if command -v apt-get >/dev/null; then
    sudo apt-get update -qq
    sudo apt-get install -y "${packages[@]}"
  else
    warn "apt-get not found; install the equivalents of: ${packages[*]}"
  fi
}

install_python_env() {
  local gpu=$1
  step "Installing uv (Python environment manager)"
  if ! command -v uv >/dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
  fi
  uv --version

  step "Creating the Python $PYTHON_VERSION environment in $VENV"
  # --seed adds pip, which Kokoro's phonemizer uses to fetch a spaCy model.
  uv venv --quiet --allow-existing --seed --python "$PYTHON_VERSION" "$VENV"

  if [[ $gpu -eq 1 ]]; then
    step "Installing PyTorch (CUDA)"
    uv pip install --python "$VENV" torch
  else
    step "Installing PyTorch (CPU)"
    uv pip install --python "$VENV" --extra-index-url "$TORCH_CPU_INDEX" torch
  fi

  step "Installing natural-tts with Piper and Kokoro"
  uv pip install --python "$VENV" "${SRC_DIR}[piper,kokoro]"

  local expected
  expected="$("$VENV/bin/python" -c 'import os
from natural_tts.config import Paths
print(Paths.from_env(os.environ).venv)')"
  [[ "$expected" == "$VENV" ]] || die "path mismatch: $expected != $VENV"
}

prefetch_kokoro() {
  step "Downloading the Kokoro model and checking it runs"
  "$VENV/bin/python" - <<'PY'
import os

from natural_tts.config import Paths, load_settings
from natural_tts.kokoro_backend import KokoroSynthesizer

settings = load_settings(Paths.from_env(os.environ))
KokoroSynthesizer.load(settings.kokoro).warm_up()
print(f"Kokoro OK (voice {settings.kokoro.voice})")
PY
}

main() {
  set -euo pipefail
  local gpu=0 hotkeys=1 setup=1
  for arg in "$@"; do
    case "$arg" in
    --gpu) gpu=1 ;;
    --no-hotkeys) hotkeys=0 ;;
    --no-setup) setup=0 ;;
    --uninstall)
      uninstall
      return 0
      ;;
    -h | --help)
      usage
      return 0
      ;;
    *)
      echo "unknown option: $arg (see --help)" >&2
      return 2
      ;;
    esac
  done

  [[ "$(uname -s)" == Linux ]] || die "natural-tts supports Linux only"
  [[ $EUID -ne 0 ]] || die "run as your normal user (sudo is used for apt)"

  step "Installing system packages"
  install_system_packages
  install_python_env "$gpu"
  prefetch_kokoro

  mkdir -p "$(dirname "$LINK")"
  ln -sf "$CLI" "$LINK"

  if [[ $setup -eq 1 ]]; then
    step "Configuring services, Speech Dispatcher and hotkeys"
    if [[ $hotkeys -eq 1 ]]; then "$CLI" setup; else "$CLI" setup --no-hotkeys; fi
  else
    echo "Installed. Run 'natural-tts setup' to configure the desktop."
  fi
}

# Run only when executed, so tests can source the functions.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
