#!/usr/bin/env bash
# Regenerate the before/after audio samples in docs/samples/, then render
# the comparison image and video with render_comparison.py.
#
# Requires an installed natural-tts (./install.sh), espeak-ng and ffmpeg.
set -euo pipefail

TEXT="Linux can finally read to you in a natural voice. Highlight any text,\
 press a key, and listen: papers, web pages, and long emails, all spoken\
 locally on your own machine."
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/docs/samples"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}/natural-tts"
PY="$DATA/venv/bin/python"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

mkdir -p "$OUT"
espeak-ng -v en-us -w "$WORK/espeak.wav" "$TEXT"

"$PY" - "$TEXT" "$WORK" <<'PY'
import os
import subprocess
import sys

import numpy as np
import soundfile as sf

from natural_tts.config import (
    CHUNK_MAX_CHARS,
    FIRST_CHUNK_MIN_CHARS,
    Paths,
    load_settings,
)
from natural_tts.kokoro_backend import KokoroSynthesizer
from natural_tts.piper import cli_command
from natural_tts.text import chunk_text

text, work = sys.argv[1], sys.argv[2]
settings = load_settings(Paths.from_env(os.environ))
wav = subprocess.run(cli_command(settings, settings.piper.length_scale),
                     input=(text + "\n").encode(), capture_output=True,
                     check=True).stdout
with open(f"{work}/piper.wav", "wb") as f:
    f.write(wav)
synth = KokoroSynthesizer.load(settings.kokoro)
chunks = chunk_text(text, FIRST_CHUNK_MIN_CHARS, CHUNK_MAX_CHARS)
sf.write(f"{work}/kokoro.wav",
         np.concatenate(list(synth.synthesize(chunks))), 24000)
PY

for name in espeak piper kokoro; do
  ffmpeg -loglevel error -y -i "$WORK/$name.wav" -ac 1 -ar 24000 -b:a 64k \
    "$OUT/$name.mp3"
done
echo "Wrote $OUT/{espeak,piper,kokoro}.mp3"
python3 "$ROOT/scripts/render_comparison.py"
