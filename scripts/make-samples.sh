#!/usr/bin/env bash
# Regenerate the before/after audio samples in docs/samples/ and, in
# media/, one waveform video per engine plus a combined comparison.
#
# GitHub READMEs cannot play audio inline, only videos uploaded through the
# web editor, so the videos are not committed: drag each one onto its line
# in README.md on github.com.
#
# Requires an installed natural-tts (./install.sh), espeak-ng and ffmpeg.
set -euo pipefail

TEXT="Linux can finally read to you in a natural voice. Highlight any text,\
 press a key, and listen: papers, web pages, and long emails, all spoken\
 locally on your own machine."
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/docs/samples"
MEDIA="$ROOT/media"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}/natural-tts"
PY="$DATA/venv/bin/python"
FONT="$(fc-match -f '%{file}' 'DejaVu Sans:bold')"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

mkdir -p "$OUT" "$MEDIA"
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

labels=(
  "espeak|1. espeak-ng  -  the default Linux voice today"
  "piper|2. Piper  -  natural-tts system voice (Firefox, screen readers)"
  "kokoro|3. Kokoro  -  natural-tts read-anything hotkey"
)
: >"$WORK/list.txt"
for spec in "${labels[@]}"; do
  name=${spec%%|*} label=${spec#*|}
  ffmpeg -loglevel error -y -i "$WORK/$name.wav" -ac 1 -ar 24000 -b:a 64k \
    "$OUT/$name.mp3"
  ffmpeg -loglevel error -y -i "$WORK/$name.wav" -filter_complex \
    "[0:a]aresample=48000,apad=pad_dur=0.8[a];\
[0:a]aresample=48000,showwaves=s=1200x300:mode=cline:colors=#7dd3fc:\
scale=sqrt:draw=full:rate=30,format=rgba,colorkey=black:0.05:0.0[w];\
color=c=#0f172a:s=1280x720:r=30[bg];[bg][w]overlay=40:240:shortest=1,\
drawtext=fontfile=$FONT:text='$label':fontcolor=white:fontsize=34:\
x=(w-text_w)/2:y=110,drawtext=fontfile=$FONT:\
text='github.com/mahdi-shafiei/ubuntu-natural-tts':fontcolor=#94a3b8:\
fontsize=24:x=(w-text_w)/2:y=640,format=yuv420p[v]" \
    -map "[v]" -map "[a]" -c:v libx264 -preset veryfast -crf 28 \
    -c:a aac -b:a 96k -shortest "$MEDIA/$name.mp4"
  echo "file '$MEDIA/$name.mp4'" >>"$WORK/list.txt"
done
ffmpeg -loglevel error -y -f concat -safe 0 -i "$WORK/list.txt" -c copy \
  "$MEDIA/comparison.mp4"
echo "Wrote $OUT/{espeak,piper,kokoro}.mp3"
echo "Wrote $MEDIA/{espeak,piper,kokoro,comparison}.mp4"
