from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import wave
from dataclasses import dataclass
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent
LOCAL_VOICEVOX_DIR = APP_DIR / "vendor" / "VOICEVOX"
SYSTEM_VOICEVOX_DIR = Path.home() / "AppData/Local/Programs/VOICEVOX"
VOICEVOX_URL = "http://127.0.0.1:50021"
SUBPROCESS_CREATIONFLAGS = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def voicevox_engine_path() -> Path:
    for folder in (LOCAL_VOICEVOX_DIR, SYSTEM_VOICEVOX_DIR):
        engine = folder / "vv-engine" / "run.exe"
        if engine.is_file():
            return engine
    return LOCAL_VOICEVOX_DIR / "vv-engine" / "run.exe"


@dataclass
class VoicevoxSettings:
    speaker: int = 13
    pause_ms: int = 300
    speed: float = 1.0
    pitch: float = 0.0
    volume: float = 1.0
    intonation: float = 1.5


def _request(method: str, path: str, *, params: dict | None = None, data: bytes | None = None, timeout: int = 60):
    url = VOICEVOX_URL + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read()
        content_type = response.headers.get("Content-Type", "")
    if "application/json" in content_type:
        return json.loads(body.decode("utf-8"))
    return body


def ensure_engine() -> subprocess.Popen | None:
    try:
        _request("GET", "/version", timeout=2)
        return None
    except Exception:
        pass
    engine = voicevox_engine_path()
    if not engine.is_file():
        raise RuntimeError(f"Khong tim thay VOICEVOX engine: {engine}")
    for use_gpu in (True, False):
        command = [str(engine), "--host", "127.0.0.1", "--port", "50021"]
        if use_gpu:
            command.append("--use_gpu")
        print("VOICEVOX engine:", " ".join(command), flush=True)
        process = subprocess.Popen(command, cwd=str(engine.parent), creationflags=SUBPROCESS_CREATIONFLAGS)
        deadline = time.time() + 45
        while time.time() < deadline:
            if process.poll() is not None:
                break
            try:
                _request("GET", "/version", timeout=2)
                print("VOICEVOX engine san sang" + (" voi GPU." if use_gpu else "."), flush=True)
                return process
            except Exception:
                time.sleep(0.5)
        if process.poll() is None:
            process.terminate()
        if use_gpu:
            print("VOICEVOX GPU khong khoi dong duoc, thu lai bang CPU.", flush=True)
    raise RuntimeError("VOICEVOX engine khong khoi dong duoc tren port 50021.")


def speakers() -> list[dict]:
    ensure_engine()
    return _request("GET", "/speakers")


def split_text(text: str) -> list[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) > 1:
        return lines
    parts = re.split(r"(?<=[.!?。！？])\s+", text.strip())
    return [part.strip() for part in parts if part.strip()]


def _wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as handle:
        return handle.getnframes() / float(handle.getframerate())


def _srt_time(seconds: float) -> str:
    millis_total = max(0, int(round(seconds * 1000)))
    millis = millis_total % 1000
    total_seconds = millis_total // 1000
    sec = total_seconds % 60
    minutes_total = total_seconds // 60
    minute = minutes_total % 60
    hour = minutes_total // 60
    return f"{hour:02d}:{minute:02d}:{sec:02d},{millis:03d}"


def outputs_are_current(text_path: Path, wav_path: Path, srt_path: Path) -> bool:
    if not text_path.is_file() or not wav_path.is_file() or not srt_path.is_file():
        return False
    text_mtime = text_path.stat().st_mtime
    return wav_path.stat().st_size > 0 and srt_path.stat().st_size > 0 and min(
        wav_path.stat().st_mtime,
        srt_path.stat().st_mtime,
    ) >= text_mtime


def synthesize_text_file(
    text_path: Path,
    wav_path: Path,
    srt_path: Path,
    settings: VoicevoxSettings,
    *,
    progress=None,
) -> tuple[Path, Path]:
    if outputs_are_current(text_path, wav_path, srt_path):
        message = f"VOICEVOX bo qua, da co san: {wav_path.name}, {srt_path.name}"
        print(message, flush=True)
        if progress:
            progress(message)
        return wav_path, srt_path
    ensure_engine()
    text = text_path.read_text(encoding="utf-8-sig", errors="replace")
    cues = split_text(text)
    if not cues:
        raise RuntimeError(f"File text rong: {text_path}")

    temp_dir = wav_path.parent / f".voicevox_parts_{wav_path.stem}"
    temp_dir.mkdir(parents=True, exist_ok=True)
    part_paths: list[Path] = []
    srt_entries: list[str] = []
    cursor = 0.0
    pause = max(0, settings.pause_ms) / 1000.0

    for index, cue in enumerate(cues, start=1):
        message = f"VOICEVOX dang tao cau {index}/{len(cues)}"
        print(message, flush=True)
        if progress:
            progress(message)
        query = _request("POST", "/audio_query", params={"text": cue, "speaker": settings.speaker})
        query["speedScale"] = settings.speed
        query["pitchScale"] = settings.pitch
        query["volumeScale"] = settings.volume
        query["intonationScale"] = settings.intonation
        query["prePhonemeLength"] = 0.1
        query["postPhonemeLength"] = pause
        wav_bytes = _request(
            "POST",
            "/synthesis",
            params={"speaker": settings.speaker},
            data=json.dumps(query, ensure_ascii=False).encode("utf-8"),
            timeout=120,
        )
        part = temp_dir / f"part_{index:04d}.wav"
        part.write_bytes(wav_bytes)
        duration = _wav_duration(part)
        part_paths.append(part)
        start = cursor
        end = cursor + duration
        srt_entries.append(f"{index}\n{_srt_time(start)} --> {_srt_time(end)}\n{cue}\n")
        cursor = end

    list_file = temp_dir / "list.txt"
    with list_file.open("w", encoding="utf-8") as handle:
        for part in part_paths:
            safe_part = str(part.resolve()).replace("\\", "/").replace("'", "'\\''")
            handle.write(f"file '{safe_part}'\n")
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", str(wav_path)],
        check=True,
        creationflags=SUBPROCESS_CREATIONFLAGS,
    )
    srt_path.write_text("\n".join(srt_entries), encoding="utf-8")
    message = f"VOICEVOX xong: {wav_path}"
    print(message, flush=True)
    if progress:
        progress(message)
    return wav_path, srt_path
