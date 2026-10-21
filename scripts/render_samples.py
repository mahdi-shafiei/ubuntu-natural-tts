#!/usr/bin/env python3
"""Render one waveform video per engine from docs/samples/*.mp3.

Each video shows the sample's waveform: the part already spoken is lit,
the rest is dimmed, and a playhead tracks the audio. The videos land in
the ignored media/ directory because GitHub plays only videos uploaded
through its web editor: drag each one onto its line in README.md there.

Needs only ffmpeg: ``ffmpeg`` on PATH, ``--ffmpeg PATH``, or the binary
from the ``imageio-ffmpeg`` package.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "docs" / "samples"
MEDIA = ROOT / "media"

WIDTH, HEIGHT = 1280, 400
BACKGROUND = "#0f172a"
WAVE_COLOR = "#7dd3fc"
DIM = 0.72  # opacity of the veil over the part not yet spoken
TAIL = 0.6  # seconds of silence after the sample
SAMPLE_RATE = 48_000

MARGIN = 60
WAVE_Y, WAVE_W, WAVE_H = 130, WIDTH - 2 * MARGIN, 200


@dataclass(frozen=True)
class Engine:
    """One engine's sample and caption."""

    sample: str
    name: str
    role: str


ENGINES = (
    Engine("espeak", "espeak-ng", "what Linux uses out of the box"),
    Engine("piper", "Piper", "the natural-tts system voice"),
    Engine("kokoro", "Kokoro", "the natural-tts read-anything hotkey"),
)


def find_ffmpeg(explicit: str | None) -> str:
    """Locate an ffmpeg binary."""
    if explicit:
        return explicit
    on_path = shutil.which("ffmpeg")
    if on_path:
        return on_path
    try:
        import imageio_ffmpeg  # type: ignore[import-not-found]
    except ImportError as exc:
        raise SystemExit(
            "ffmpeg not found: install ffmpeg or `pip install imageio-ffmpeg`"
        ) from exc
    return str(imageio_ffmpeg.get_ffmpeg_exe())


def find_font() -> str:
    """Path of a bold sans-serif font for captions."""
    fc_match = shutil.which("fc-match")
    if fc_match:
        out = subprocess.run(
            [fc_match, "-f", "%{file}", "DejaVu Sans:bold"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        if out:
            return out
    return "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def duration(ffmpeg: str, path: Path) -> float:
    """Audio duration in seconds, measured by decoding (no ffprobe)."""
    pcm = subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-i",
            str(path),
            "-ac",
            "1",
            "-ar",
            str(SAMPLE_RATE),
            "-f",
            "s16le",
            "-",
        ],
        capture_output=True,
        check=True,
    ).stdout
    return len(pcm) / 2 / SAMPLE_RATE


def _escape(text: str) -> str:
    return text.replace(":", r"\:").replace("'", r"\'")


def filter_graph(engine: Engine, length: float, font: str) -> str:
    """Build the ffmpeg filter graph for one engine's video."""
    total = length + TAIL
    played = f"min(t/{length:.3f},1)"
    head = f"{MARGIN}+{WAVE_W}*{played}"
    return ";".join(
        [
            "[0:a]asplit=2[a][s]",
            f"[s]showwavespic=s={WAVE_W}x{WAVE_H}:colors={WAVE_COLOR}:"
            "scale=sqrt:draw=full,format=rgba,colorkey=black:0.05:0.0[w]",
            f"[a]apad=pad_dur={TAIL}[audio]",
            f"color=c={BACKGROUND}@{DIM}:s={WAVE_W + MARGIN}x{WAVE_H}:"
            "r=30,format=rgba[veil]",
            f"color=c=white:s=3x{WAVE_H + 16}:r=30[head]",
            f"color=c={BACKGROUND}:s={WIDTH}x{HEIGHT}:r=30:d={total:.2f}[bg]",
            f"[bg][w]overlay={MARGIN}:{WAVE_Y}[v0]",
            # Veil the part not yet spoken, then draw the playhead. Unlike
            # drawbox, overlay evaluates t (seconds) on every frame.
            f"[v0][veil]overlay=x='{head}':y={WAVE_Y}:eval=frame:"
            "shortest=1[v1]",
            f"[v1][head]overlay=x='{head}':y={WAVE_Y - 8}:eval=frame:"
            "shortest=1,"
            f"drawtext=fontfile={font}:text='{_escape(engine.name)}':"
            f"fontcolor=white:fontsize=40:x={MARGIN}:y=36,"
            f"drawtext=fontfile={font}:text='{_escape(engine.role)}':"
            f"fontcolor=#94a3b8:fontsize=24:x={MARGIN}:y=88,"
            f"drawtext=fontfile={font}:"
            "text='github.com/mahdi-shafiei/ubuntu-natural-tts':"
            f"fontcolor=#64748b:fontsize=18:x=w-text_w-{MARGIN}:y=50,"
            "format=yuv420p[v]",
        ]
    )


def render(ffmpeg: str, font: str, engine: Engine, out: Path) -> None:
    """Render one engine's waveform video."""
    source = SAMPLES / f"{engine.sample}.mp3"
    length = duration(ffmpeg, source)
    cmd = [
        ffmpeg,
        "-v",
        "error",
        "-y",
        "-i",
        str(source),
        "-filter_complex",
        filter_graph(engine, length, font),
        "-map",
        "[v]",
        "-map",
        "[audio]",
        "-t",
        f"{length + TAIL:.2f}",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "26",
        "-c:a",
        "aac",
        "-b:a",
        "96k",
        "-movflags",
        "+faststart",
        str(out),
    ]
    subprocess.run(cmd, check=True)


def main() -> None:
    """Render a video for every engine."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ffmpeg", help="path to an ffmpeg binary")
    args = parser.parse_args()
    ffmpeg = find_ffmpeg(args.ffmpeg)
    font = find_font()
    MEDIA.mkdir(exist_ok=True)
    for engine in ENGINES:
        out = MEDIA / f"{engine.sample}.mp4"
        render(ffmpeg, font, engine, out)
        print(f"Wrote {out}")


if __name__ == "__main__":
    main()
