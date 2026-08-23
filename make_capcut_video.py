#!/usr/bin/env python3
"""
Create a 16:9 MP4 from an SRT file and a folder of videos.

The tool reads the SRT duration, randomly picks 3-second clips from videos in
the given folder, normalizes them to 16:9, concatenates them, and optionally
burns the SRT subtitles into the final video.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}
APP_DIR = Path(__file__).resolve().parent
APP_BIN = APP_DIR / "bin"
SUBPROCESS_CREATIONFLAGS = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
_ENCODER_PROBE_CACHE: dict[str, bool] = {}

if (APP_BIN / "ffmpeg.exe").is_file() and (APP_BIN / "ffprobe.exe").is_file():
    os.environ["PATH"] = str(APP_BIN) + os.pathsep + os.environ.get("PATH", "")


def available_ffmpeg_encoders() -> set[str]:
    try:
        result = run(["ffmpeg", "-hide_banner", "-encoders"], capture=True)
    except Exception:
        return set()
    encoders = set()
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            encoders.add(parts[1])
    return encoders


def choose_h264_encoder(use_gpu: bool = True) -> str:
    if not use_gpu:
        return "libx264"
    encoders = available_ffmpeg_encoders()
    for encoder in ("h264_nvenc", "h264_amf", "h264_qsv"):
        if encoder in encoders and encoder_is_runtime_available(encoder):
            return encoder
    return "libx264"


def encoder_is_runtime_available(encoder: str) -> bool:
    if encoder == "libx264":
        return True
    if encoder in _ENCODER_PROBE_CACHE:
        return _ENCODER_PROBE_CACHE[encoder]
    try:
        run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "testsrc2=size=128x72:rate=30",
                "-t",
                "0.25",
                "-an",
                *encoder_args(encoder),
                "-f",
                "null",
                os.devnull,
            ],
            capture=True,
        )
        available = True
    except Exception:
        available = False
    _ENCODER_PROBE_CACHE[encoder] = available
    return available


def encoder_args(encoder: str) -> list[str]:
    if encoder == "h264_nvenc":
        return ["-c:v", encoder, "-preset", "fast", "-cq", "21"]
    if encoder == "h264_amf":
        return ["-c:v", encoder, "-quality", "speed", "-qp_i", "21", "-qp_p", "23"]
    if encoder == "h264_qsv":
        return ["-c:v", encoder, "-preset", "veryfast", "-global_quality", "23"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]


def run(command: list[str], *, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        check=True,
        text=True,
        creationflags=SUBPROCESS_CREATIONFLAGS,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def require_binary(name: str) -> None:
    if shutil.which(name) is None:
        raise SystemExit(f"Missing required program: {name}. Please install FFmpeg first.")


def parse_srt_timestamp(value: str) -> float:
    time_part, millis = value.strip().split(",")
    hours, minutes, seconds = [int(part) for part in time_part.split(":")]
    return hours * 3600 + minutes * 60 + seconds + int(millis) / 1000


def read_srt_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "utf-16", "big5", "cp950", "cp932", "shift_jis", "cp1252"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8-sig", errors="replace")


def srt_duration(path: Path) -> float:
    latest = 0.0
    for line in read_srt_text(path).splitlines():
        if "-->" not in line:
            continue
        _, end = line.split("-->", 1)
        end_time = end.strip().split()[0]
        latest = max(latest, parse_srt_timestamp(end_time))
    if latest <= 0:
        raise SystemExit(f"Could not read subtitle duration from {path}")
    return latest


def ffprobe_json(path: Path, entries: str) -> dict:
    result = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            entries,
            "-of",
            "json",
            str(path),
        ],
        capture=True,
    )
    return json.loads(result.stdout)


def ffprobe_duration(path: Path) -> float:
    data = ffprobe_json(path, "format=duration:stream=duration")
    format_duration = data.get("format", {}).get("duration")
    if format_duration not in (None, "N/A"):
        return float(format_duration)
    for stream in data.get("streams", []):
        stream_duration = stream.get("duration")
        if stream_duration not in (None, "N/A"):
            return float(stream_duration)
    raise RuntimeError(f"Could not read duration: {path}")


def ffprobe_video_size(path: Path) -> tuple[int, int]:
    data = ffprobe_json(path, "stream=width,height")
    for stream in data.get("streams", []):
        width = stream.get("width")
        height = stream.get("height")
        if width and height:
            return int(width), int(height)
    raise RuntimeError(f"Could not read video size: {path}")


def validate_video_file(path: Path) -> tuple[float, int, int]:
    if not path.is_file() or path.stat().st_size < 1024:
        raise RuntimeError(f"Invalid or empty video file: {path}")
    duration = ffprobe_duration(path)
    width, height = ffprobe_video_size(path)
    if duration <= 0 or width <= 0 or height <= 0:
        raise RuntimeError(f"Invalid video metadata: {path}")
    return duration, width, height


def is_16x9(path: Path, tolerance: float = 0.03) -> bool:
    width, height = ffprobe_video_size(path)
    if height <= 0:
        return False
    ratio = width / height
    return width > height and abs(ratio - (16 / 9)) <= tolerance


def collect_videos(folder: Path, *, only_16x9: bool = True, progress=None) -> list[Path]:
    candidates = [
        item
        for item in folder.iterdir()
        if item.is_file() and item.suffix.lower() in VIDEO_EXTENSIONS
    ]

    skipped: list[str] = []
    videos = []
    for index, item in enumerate(candidates, start=1):
        if progress:
            progress(index, len(candidates), item)
        if not only_16x9 or _keep_16x9(item, skipped):
            videos.append(item)
    if not videos:
        if only_16x9:
            raise SystemExit(f"No 16:9 horizontal videos found in {folder}")
        raise SystemExit(f"No supported videos found in {folder}")
    for name in skipped:
        print(f"Skip non-16:9: {name}")
    return videos


def _keep_16x9(path: Path, skipped: list[str]) -> bool:
    try:
        keep = is_16x9(path)
    except Exception:
        keep = False
    if not keep:
        skipped.append(path.name)
    return keep


def ffmpeg_filter(width: int, height: int, burn_subtitles: Path | None) -> str:
    filters = [
        f"scale={width}:{height}:force_original_aspect_ratio=increase",
        f"crop={width}:{height}",
        "setsar=1",
        "fps=30",
        "format=yuv420p",
    ]
    if burn_subtitles:
        escaped = str(burn_subtitles).replace("\\", "/").replace(":", "\\:")
        filters.append(f"subtitles='{escaped}'")
    return ",".join(filters)


def create_clip(
    source: Path,
    output: Path,
    *,
    clip_length: float,
    width: int,
    height: int,
    encoder: str = "libx264",
) -> None:
    duration = ffprobe_duration(source)
    if duration <= 0:
        raise RuntimeError(f"Could not read duration: {source}")

    max_start = max(0.0, duration - clip_length)
    start = random.uniform(0, max_start) if max_start > 0 else 0

    run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            f"{start:.3f}",
            "-t",
            f"{clip_length:.3f}",
            "-i",
            str(source),
            "-vf",
            ffmpeg_filter(width, height, None),
            "-an",
        ]
        + encoder_args(encoder)
        + [str(output)]
    )


def concat_clips(clips: list[Path], output: Path, duration: float | None) -> None:
    list_file = output.with_suffix(".txt")
    with list_file.open("w", encoding="utf-8") as handle:
        for clip in clips:
            safe_path = str(clip).replace("\\", "/").replace("'", "'\\''")
            handle.write(f"file '{safe_path}'\n")

    command = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_file),
        "-c",
        "copy",
    ]
    if duration:
        command.extend(["-t", f"{duration:.3f}"])
    command.append(str(output))
    run(command)
    list_file.unlink(missing_ok=True)


def mux_audio(video: Path, audio: Path, output: Path, duration: float | None = None) -> None:
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(video),
        "-i",
        str(audio),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
    ]
    if duration:
        command.extend(["-t", f"{duration:.3f}"])
    command.append(str(output))
    run(command)


def burn_subtitles(
    input_video: Path,
    srt: Path,
    output: Path,
    width: int,
    height: int,
    encoder: str = "libx264",
) -> None:
    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(input_video),
            "-vf",
            ffmpeg_filter(width, height, srt),
            *encoder_args(encoder),
            "-an",
            str(output),
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Randomly combine 3-second clips into a 16:9 video based on SRT length."
    )
    parser.add_argument("srt", type=Path, help="Input .srt file")
    parser.add_argument("video_folder", type=Path, help="Folder containing source videos")
    parser.add_argument("-o", "--output", type=Path, default=Path("capcut_video.mp4"))
    parser.add_argument("--clip-length", type=float, default=3.0, help="Clip length in seconds")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--seed", type=int, help="Random seed for repeatable results")
    parser.add_argument("--no-gpu", action="store_true", help="Disable GPU H.264 encoder")
    parser.add_argument(
        "--burn-subtitles",
        action="store_true",
        help="Burn the SRT subtitles into the video.",
    )
    args = parser.parse_args()

    require_binary("ffmpeg")
    require_binary("ffprobe")

    if args.seed is not None:
        random.seed(args.seed)
    encoder = choose_h264_encoder(not args.no_gpu)
    print(f"Encoder: {encoder}")

    srt = args.srt.resolve()
    video_folder = args.video_folder.resolve()
    output = args.output.resolve()

    if not srt.is_file():
        raise SystemExit(f"SRT file does not exist: {srt}")
    if not video_folder.is_dir():
        raise SystemExit(f"Video folder does not exist: {video_folder}")

    target_duration = srt_duration(srt)
    clip_count = math.ceil(target_duration / args.clip_length)
    videos = collect_videos(video_folder)

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="capcut_clips_") as temp_dir:
        temp_path = Path(temp_dir)
        clips: list[Path] = []
        for index in range(clip_count):
            start_time = index * args.clip_length
            remaining = target_duration - start_time
            current_clip_length = min(args.clip_length, remaining)
            if current_clip_length <= 0:
                break
            source = random.choice(videos)
            clip_path = temp_path / f"clip_{index:04d}.mp4"
            print(f"[{index + 1}/{clip_count}] {source.name} ({current_clip_length:.3f}s)")
            create_clip(
                source,
                clip_path,
                clip_length=current_clip_length,
                width=args.width,
                height=args.height,
                encoder=encoder,
            )
            clips.append(clip_path)

        if args.burn_subtitles:
            raw_output = temp_path / "joined_without_subtitles.mp4"
            concat_clips(clips, raw_output, target_duration)
            burn_subtitles(raw_output, srt, output, args.width, args.height, encoder)
        else:
            concat_clips(clips, output, target_duration)

    print(f"Done: {output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        if exc.stderr:
            print(exc.stderr, file=sys.stderr)
        raise SystemExit(exc.returncode)
