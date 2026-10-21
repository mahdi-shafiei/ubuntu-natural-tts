#!/usr/bin/env python3
"""Render the README comparison from docs/samples/*.mp3.

Outputs:
    docs/samples/comparison.png  three waveform lanes (committed)
    media/comparison.mp4         the lanes with sound; the speaking lane is
                                 lit and a playhead moves across it (not
                                 committed: GitHub only plays videos
                                 uploaded through its web editor)

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

WIDTH, HEIGHT = 1280, 720
BACKGROUND = "#0f172a"
WAVE_COLOR = "#7dd3fc"
DIM_ALPHA = 0.28
GAP = 0.8  # seconds of silence between lanes
SAMPLE_RATE = 48_000

TITLE_Y = 36
LANE_TOP, LANE_HEIGHT = 120, 180
WAVE_X, WAVE_W, WAVE_H = 380, 840, 120
LABEL_X = 60


@dataclass(frozen=True)
class Lane:
    """One engine in the comparison."""

    sample: str
    name: str
    role: str


LANES = (
    Lane("espeak", "espeak-ng", "Linux default"),
    Lane("piper", "Piper", "system voice"),
    Lane("kokoro", "Kokoro", "read-anything hotkey"),
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
    """Path of a bold sans-serif font for labels."""
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


def lane_y(index: int) -> int:
    """Top of a lane's waveform."""
    return LANE_TOP + index * LANE_HEIGHT


def _escape(text: str) -> str:
    return text.replace(":", r"\:").replace("'", r"\'")


def _labels(font: str) -> list[str]:
    title = (
        f"drawtext=fontfile={font}:text='The same sentence, three engines':"
        f"fontcolor=white:fontsize=34:x=(w-text_w)/2:y={TITLE_Y}"
    )
    parts = [title]
    for i, lane in enumerate(LANES):
        y = lane_y(i)
        parts += [
            f"drawtext=fontfile={font}:text='{_escape(lane.name)}':"
            f"fontcolor=white:fontsize=34:x={LABEL_X}:y={y + 30}",
            f"drawtext=fontfile={font}:text='{_escape(lane.role)}':"
            f"fontcolor=#94a3b8:fontsize=22:x={LABEL_X}:y={y + 76}",
        ]
    return parts


def render_png(ffmpeg: str, font: str, out: Path) -> None:
    """Render the static three-lane image."""
    chains = [
        f"[{i}:a]showwavespic=s={WAVE_W}x{WAVE_H}:colors={WAVE_COLOR}:"
        f"scale=sqrt:draw=full,format=rgba,colorkey=black:0.05:0.0[w{i}]"
        for i in range(len(LANES))
    ]
    chains.append(f"color=c={BACKGROUND}:s={WIDTH}x{HEIGHT}[bg0]")
    for i in range(len(LANES)):
        chains.append(f"[bg{i}][w{i}]overlay={WAVE_X}:{lane_y(i)}[bg{i + 1}]")
    chains.append(f"[bg{len(LANES)}]" + ",".join(_labels(font)) + "[v]")
    cmd = [ffmpeg, "-v", "error", "-y"]
    for lane in LANES:
        cmd += ["-i", str(SAMPLES / f"{lane.sample}.mp3")]
    cmd += [
        "-filter_complex",
        ";".join(chains),
        "-map",
        "[v]",
        "-frames:v",
        "1",
        str(out),
    ]
    subprocess.run(cmd, check=True)


def render_video(ffmpeg: str, font: str, out: Path) -> None:
    """Render the comparison video with the lanes speaking in turn."""
    lengths = [
        duration(ffmpeg, SAMPLES / f"{lane.sample}.mp3") for lane in LANES
    ]
    starts = [sum(lengths[:i]) + GAP * i for i in range(len(LANES))]
    total = starts[-1] + lengths[-1] + GAP

    chains: list[str] = []
    for i in range(len(LANES)):
        chains.append(f"[{i}:a]asplit=3[a{i}][s{i}][d{i}]")
        for tag, alpha in (("s", 1.0), ("d", DIM_ALPHA)):
            # A still image: overlay repeats its only frame for the whole
            # video (eof_action=repeat is the default).
            chains.append(
                f"[{tag}{i}]showwavespic=s={WAVE_W}x{WAVE_H}:"
                f"colors={WAVE_COLOR}:scale=sqrt:draw=full,format=rgba,"
                f"colorkey=black:0.05:0.0,colorchannelmixer=aa={alpha}"
                f"[{tag}w{i}]"
            )
        chains.append(f"[a{i}]apad=pad_dur={GAP}[p{i}]")
    padded = "".join(f"[p{i}]" for i in range(len(LANES)))
    chains.append(f"{padded}concat=n={len(LANES)}:v=0:a=1[audio]")

    chains.append(
        f"color=c={BACKGROUND}:s={WIDTH}x{HEIGHT}:r=30:d={total:.2f}[bg0]"
    )
    layer = 0
    for i in range(len(LANES)):
        y = lane_y(i)
        window = f"between(t,{starts[i]:.3f},{starts[i] + lengths[i]:.3f})"
        playhead = f"{WAVE_X}+{WAVE_W}*(t-{starts[i]:.3f})/{lengths[i]:.3f}"
        chains += [
            f"[bg{layer}][dw{i}]overlay={WAVE_X}:{y}[bg{layer + 1}]",
            f"[bg{layer + 1}][sw{i}]overlay={WAVE_X}:{y}:"
            f"enable='{window}'[bg{layer + 2}]",
            f"[bg{layer + 2}]drawbox=x='{playhead}':y={y - 6}:w=3:"
            f"h={WAVE_H + 12}:color=white@0.9:t=fill:enable='{window}',"
            f"drawbox=x={LABEL_X - 24}:y={y + 34}:w=8:h=30:"
            f"color={WAVE_COLOR}:t=fill:enable='{window}'[bg{layer + 3}]",
        ]
        layer += 3
    footer = (
        f"drawtext=fontfile={font}:"
        f"text='github.com/mahdi-shafiei/ubuntu-natural-tts':"
        f"fontcolor=#64748b:fontsize=22:x=(w-text_w)/2:y={HEIGHT - 44}"
    )
    chains.append(
        f"[bg{layer}]"
        + ",".join([*_labels(font), footer])
        + ",format=yuv420p[v]"
    )

    cmd = [ffmpeg, "-v", "error", "-y"]
    for lane in LANES:
        cmd += ["-i", str(SAMPLES / f"{lane.sample}.mp3")]
    cmd += [
        "-filter_complex",
        ";".join(chains),
        "-map",
        "[v]",
        "-map",
        "[audio]",
        "-t",
        f"{total:.2f}",
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
    """Render both outputs."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ffmpeg", help="path to an ffmpeg binary")
    args = parser.parse_args()
    ffmpeg = find_ffmpeg(args.ffmpeg)
    font = find_font()
    MEDIA.mkdir(exist_ok=True)
    render_png(ffmpeg, font, SAMPLES / "comparison.png")
    render_video(ffmpeg, font, MEDIA / "comparison.mp4")
    print(f"Wrote {SAMPLES / 'comparison.png'} and {MEDIA / 'comparison.mp4'}")


if __name__ == "__main__":
    main()
