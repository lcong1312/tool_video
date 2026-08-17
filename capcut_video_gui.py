#!/usr/bin/env python3
"""
Small Windows GUI for make_capcut_video.py.
"""

from __future__ import annotations

import math
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from make_capcut_video import (
    burn_subtitles,
    collect_videos,
    concat_clips,
    create_clip,
    choose_h264_encoder,
    mux_audio,
    require_binary,
    srt_duration,
    validate_video_file,
)
from capcut_draft import (
    create_capcut_project_from_clips,
    prepare_capcut_project,
)
from pexels_downloader import download_pexels_videos
from voicevox_tts import VoicevoxSettings, synthesize_text_file


APP_CONFIG = Path(__file__).with_name("config.json")
COMMON_CAPCUT_PATHS = [
    Path(os.environ.get("LOCALAPPDATA", "")) / "CapCut" / "Apps" / "CapCut.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "CapCut" / "CapCut.exe",
    Path(os.environ.get("PROGRAMFILES", "")) / "CapCut" / "CapCut.exe",
    Path(os.environ.get("PROGRAMFILES(X86)", "")) / "CapCut" / "CapCut.exe",
]


def load_app_config() -> dict:
    if not APP_CONFIG.is_file():
        return {}
    try:
        with APP_CONFIG.open("r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_app_config(data: dict) -> None:
    with APP_CONFIG.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


def find_capcut() -> Path | None:
    for path in COMMON_CAPCUT_PATHS:
        if path.is_file():
            return path
    return None


class CapCutVideoApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("SRT to CapCut Video")
        self.geometry("860x760")
        self.minsize(820, 720)
        self.config_data = load_app_config()

        self.srt_var = tk.StringVar()
        self.text_var = tk.StringVar(value=str(Path.cwd() / "index.txt"))
        self.voice_output_var = tk.StringVar(
            value=str(self.config_data.get("voicevox_output") or Path.cwd() / "voicevox_output" / "voice.wav")
        )
        self.use_voicevox_var = tk.BooleanVar(value=False)
        self.voice_speaker_var = tk.StringVar(value=str(self.config_data.get("voicevox_speaker") or "1"))
        self.voice_pause_var = tk.StringVar(value=str(self.config_data.get("voicevox_pause_ms") or "300"))
        self.voice_speed_var = tk.StringVar(value=str(self.config_data.get("voicevox_speed") or "1.0"))
        self.voice_pitch_var = tk.StringVar(value=str(self.config_data.get("voicevox_pitch") or "0.0"))
        self.voice_volume_var = tk.StringVar(value=str(self.config_data.get("voicevox_volume") or "1.0"))
        self.voice_intonation_var = tk.StringVar(value=str(self.config_data.get("voicevox_intonation") or "1.0"))
        self.folder_var = tk.StringVar()
        self.output_var = tk.StringVar(value=str(Path.cwd() / "output.mp4"))
        self.clip_length_var = tk.StringVar(value="3")
        self.width_var = tk.StringVar(value="1920")
        self.height_var = tk.StringVar(value="1080")
        self.seed_var = tk.StringVar()
        self.burn_subtitles_var = tk.BooleanVar(value=False)
        self.use_gpu_var = tk.BooleanVar(value=True)
        self.only_16x9_var = tk.BooleanVar(value=True)
        self.import_srt_var = tk.BooleanVar(value=True)
        self.resume_project_var = tk.BooleanVar(value=True)
        self.create_capcut_project_var = tk.BooleanVar(value=True)
        self.open_capcut_var = tk.BooleanVar(value=True)
        self.use_pexels_var = tk.BooleanVar(value=False)
        self.source_var = tk.StringVar(value="local")
        self.pexels_query_var = tk.StringVar(value=str(self.config_data.get("pexels_query") or "nature"))
        self.pexels_threads_var = tk.StringVar(value=str(self.config_data.get("pexels_threads") or "10"))
        self.pexels_api_key_var = tk.StringVar(
            value=str(self.config_data.get("pexels_api_key") or os.environ.get("PEXELS_API_KEY", ""))
        )
        self.status_var = tk.StringVar(value="Sẵn sàng")
        self.percent_var = tk.StringVar(value="0%")
        capcut = find_capcut()
        self.capcut_var = tk.StringVar(value=str(capcut) if capcut else "")

        self.worker: threading.Thread | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=18)
        root.pack(fill="both", expand=True)
        root.columnconfigure(1, weight=1)

        voice = ttk.LabelFrame(root, text="VOICEVOX")
        voice.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        for index in range(8):
            voice.columnconfigure(index, weight=1)
        ttk.Checkbutton(
            voice,
            text="Tạo voice + SRT từ text",
            variable=self.use_voicevox_var,
            command=self.update_voicevox_ui,
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=6, pady=5)
        ttk.Label(voice, text="Giọng").grid(row=0, column=2, sticky="e", padx=(8, 4))
        ttk.Entry(voice, textvariable=self.voice_speaker_var, width=8).grid(row=0, column=3, sticky="w")
        ttk.Label(voice, text="Nghỉ ms").grid(row=0, column=4, sticky="e", padx=(8, 4))
        ttk.Entry(voice, textvariable=self.voice_pause_var, width=8).grid(row=0, column=5, sticky="w")
        ttk.Label(voice, text="Tốc độ").grid(row=1, column=0, sticky="e", padx=(6, 4), pady=5)
        ttk.Entry(voice, textvariable=self.voice_speed_var, width=8).grid(row=1, column=1, sticky="w")
        ttk.Label(voice, text="Độ cao").grid(row=1, column=2, sticky="e", padx=(8, 4))
        ttk.Entry(voice, textvariable=self.voice_pitch_var, width=8).grid(row=1, column=3, sticky="w")
        ttk.Label(voice, text="Âm lượng").grid(row=1, column=4, sticky="e", padx=(8, 4))
        ttk.Entry(voice, textvariable=self.voice_volume_var, width=8).grid(row=1, column=5, sticky="w")
        ttk.Label(voice, text="Độ nhấn").grid(row=1, column=6, sticky="e", padx=(8, 4))
        ttk.Entry(voice, textvariable=self.voice_intonation_var, width=8).grid(row=1, column=7, sticky="w")
        self.voice_output_row = ttk.Frame(voice)
        self.voice_output_row.grid(row=2, column=0, columnspan=8, sticky="ew", padx=6, pady=(4, 2))
        self.voice_output_row.columnconfigure(1, weight=1)
        ttk.Label(self.voice_output_row, text="Lưu voice/SRT").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(self.voice_output_row, textvariable=self.voice_output_var).grid(row=0, column=1, sticky="ew", padx=(0, 8))
        ttk.Button(self.voice_output_row, text="Chọn", command=self.pick_voice_output).grid(row=0, column=2, sticky="ew")
        self.voice_text_frame = ttk.Frame(voice)
        self.voice_text_frame.grid(row=3, column=0, columnspan=8, sticky="ew", padx=6, pady=(4, 6))
        self.voice_text_frame.columnconfigure(0, weight=1)
        ttk.Label(self.voice_text_frame, text="Nội dung đọc").grid(row=0, column=0, sticky="w", pady=(0, 4))
        self.voice_text = tk.Text(self.voice_text_frame, height=5, wrap="word")
        self.voice_text.grid(row=1, column=0, sticky="ew")

        source = ttk.Frame(root)
        source.grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 8))
        ttk.Label(source, text="Nguồn video").pack(side="left", padx=(0, 12))
        ttk.Radiobutton(source, text="Video trong máy", variable=self.source_var, value="local", command=self.update_source_ui).pack(
            side="left", padx=(0, 12)
        )
        ttk.Radiobutton(source, text="Tải từ Pexels", variable=self.source_var, value="pexels", command=self.update_source_ui).pack(
            side="left"
        )

        self.srt_row = ttk.Frame(root)
        self.srt_row.grid(row=2, column=0, columnspan=3, sticky="ew")
        self.srt_row.columnconfigure(1, weight=1)
        ttk.Label(self.srt_row, text="File SRT").grid(row=0, column=0, sticky="w", pady=5)
        ttk.Entry(self.srt_row, textvariable=self.srt_var).grid(row=0, column=1, sticky="ew", padx=8, pady=5)
        ttk.Button(self.srt_row, text="Chọn", command=self.pick_srt).grid(row=0, column=2, sticky="ew", pady=5)
        self._path_row(root, 3, "File text", self.text_var, self.pick_text)
        self.folder_row = ttk.Frame(root)
        self.folder_row.grid(row=4, column=0, columnspan=3, sticky="ew")
        self.folder_row.columnconfigure(1, weight=1)
        ttk.Label(self.folder_row, text="Thư mục video").grid(row=0, column=0, sticky="w", pady=5)
        ttk.Entry(self.folder_row, textvariable=self.folder_var).grid(row=0, column=1, sticky="ew", padx=8, pady=5)
        ttk.Button(self.folder_row, text="Chọn", command=self.pick_folder).grid(row=0, column=2, sticky="ew", pady=5)
        self._path_row(root, 5, "File xuất", self.output_var, self.pick_output)
        self._path_row(root, 6, "CapCut.exe", self.capcut_var, self.pick_capcut)

        options = ttk.Frame(root)
        options.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(14, 8))
        for index in range(8):
            options.columnconfigure(index, weight=1)

        ttk.Label(options, text="Mỗi clip").grid(row=0, column=0, sticky="w")
        ttk.Entry(options, textvariable=self.clip_length_var, width=8).grid(row=0, column=1, sticky="w")
        ttk.Label(options, text="giây").grid(row=0, column=2, sticky="w", padx=(4, 18))

        ttk.Label(options, text="Kích thước").grid(row=0, column=3, sticky="w")
        ttk.Entry(options, textvariable=self.width_var, width=8).grid(row=0, column=4, sticky="w")
        ttk.Label(options, text="x").grid(row=0, column=5, sticky="w", padx=4)
        ttk.Entry(options, textvariable=self.height_var, width=8).grid(row=0, column=6, sticky="w")

        ttk.Label(options, text="Seed").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(options, textvariable=self.seed_var, width=12).grid(row=1, column=1, sticky="w", pady=(8, 0))
        ttk.Checkbutton(options, text="Gắn phụ đề vào video", variable=self.burn_subtitles_var).grid(
            row=1, column=3, columnspan=2, sticky="w", pady=(8, 0)
        )
        ttk.Checkbutton(options, text="Tạo project CapCut", variable=self.create_capcut_project_var).grid(
            row=1, column=5, columnspan=3, sticky="w", pady=(8, 0)
        )
        ttk.Checkbutton(options, text="Dùng GPU", variable=self.use_gpu_var).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(8, 0)
        )
        self.only_16x9_check = ttk.Checkbutton(options, text="Chỉ lấy video 16:9", variable=self.only_16x9_var)
        self.only_16x9_check.grid(
            row=2, column=1, columnspan=3, sticky="w", pady=(8, 0)
        )
        ttk.Checkbutton(options, text="Import SRT vào CapCut", variable=self.import_srt_var).grid(
            row=3, column=0, columnspan=3, sticky="w", pady=(8, 0)
        )
        ttk.Checkbutton(options, text="Tiếp tục clip đã tạo", variable=self.resume_project_var).grid(
            row=3, column=3, columnspan=3, sticky="w", pady=(8, 0)
        )
        ttk.Checkbutton(options, text="Mở CapCut sau khi xong", variable=self.open_capcut_var).grid(
            row=2, column=3, columnspan=4, sticky="w", pady=(8, 0)
        )

        self.pexels_frame = ttk.Frame(root)
        self.pexels_frame.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        self.pexels_frame.columnconfigure(1, weight=1)
        ttk.Label(self.pexels_frame, text="Từ khóa").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 6))
        ttk.Entry(self.pexels_frame, textvariable=self.pexels_query_var, width=24).grid(
            row=0, column=1, sticky="ew", pady=(0, 6)
        )
        ttk.Label(self.pexels_frame, text="Luồng tải").grid(row=0, column=2, sticky="e", padx=(16, 8), pady=(0, 6))
        ttk.Entry(self.pexels_frame, textvariable=self.pexels_threads_var, width=8).grid(
            row=0, column=3, sticky="w", pady=(0, 6)
        )
        ttk.Label(self.pexels_frame, text="API key").grid(row=1, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(self.pexels_frame, textvariable=self.pexels_api_key_var, show="*", width=34).grid(
            row=1, column=1, columnspan=3, sticky="ew"
        )

        actions = ttk.Frame(root)
        actions.grid(row=9, column=0, columnspan=3, sticky="ew", pady=(10, 8))
        actions.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(actions, mode="determinate")
        self.progress.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        ttk.Label(actions, textvariable=self.percent_var, width=6, anchor="e").grid(
            row=0, column=1, sticky="e", padx=(0, 12)
        )
        self.start_button = ttk.Button(actions, text="Tạo video", command=self.start)
        self.start_button.grid(row=0, column=2)

        ttk.Label(root, textvariable=self.status_var).grid(
            row=10, column=0, columnspan=3, sticky="w", pady=(0, 8)
        )

        self.log = tk.Text(root, height=14, wrap="word")
        self.log.grid(row=11, column=0, columnspan=3, sticky="nsew")
        root.rowconfigure(11, weight=1)
        self.update_source_ui()
        self.update_voicevox_ui()

    def _path_row(self, parent: ttk.Frame, row: int, label: str, variable: tk.StringVar, command) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=5)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=8, pady=5)
        ttk.Button(parent, text="Chọn", command=command).grid(row=row, column=2, sticky="ew", pady=5)

    def update_voicevox_ui(self) -> None:
        if self.use_voicevox_var.get():
            self.srt_row.grid_remove()
            self.voice_output_row.grid()
            self.voice_text_frame.grid()
        else:
            self.srt_row.grid()
            self.voice_output_row.grid_remove()
            self.voice_text_frame.grid_remove()

    def update_source_ui(self) -> None:
        use_pexels = self.source_var.get() == "pexels"
        self.use_pexels_var.set(use_pexels)
        if use_pexels:
            self.only_16x9_var.set(True)
            self.only_16x9_check.configure(state="disabled")
            self.folder_row.grid_remove()
            self.pexels_frame.grid()
        else:
            self.only_16x9_check.configure(state="normal")
            self.folder_row.grid()
            self.pexels_frame.grid_remove()

    def pick_srt(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("SRT subtitles", "*.srt"), ("All files", "*.*")])
        if path:
            self.srt_var.set(path)

    def pick_text(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if path:
            self.text_var.set(path)

    def pick_voice_output(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".wav",
            initialfile=Path(self.voice_output_var.get()).name or "voice.wav",
            filetypes=[("WAV audio", "*.wav"), ("All files", "*.*")],
        )
        if path:
            self.voice_output_var.set(path)

    def pick_folder(self) -> None:
        path = filedialog.askdirectory()
        if path:
            self.folder_var.set(path)

    def pick_output(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".mp4",
            filetypes=[("MP4 video", "*.mp4"), ("All files", "*.*")],
        )
        if path:
            self.output_var.set(path)

    def pick_capcut(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("CapCut executable", "CapCut.exe"), ("EXE", "*.exe")])
        if path:
            self.capcut_var.set(path)

    def write_log(self, text: str) -> None:
        self.log.insert("end", text + "\n")
        self.log.see("end")

    def set_progress(self, value: int, maximum: int) -> None:
        self.progress.configure(maximum=maximum, value=value)
        percent = 0 if maximum <= 0 else round((value / maximum) * 100)
        self.percent_var.set(f"{percent}%")

    def set_status(self, text: str) -> None:
        self.status_var.set(text)

    def save_pexels_config(self) -> None:
        self.config_data["pexels_api_key"] = self.pexels_api_key_var.get().strip()
        self.config_data["pexels_query"] = self.pexels_query_var.get().strip()
        self.config_data["pexels_threads"] = self.pexels_threads_var.get().strip()
        self.config_data["voicevox_speaker"] = self.voice_speaker_var.get().strip()
        self.config_data["voicevox_pause_ms"] = self.voice_pause_var.get().strip()
        self.config_data["voicevox_speed"] = self.voice_speed_var.get().strip()
        self.config_data["voicevox_pitch"] = self.voice_pitch_var.get().strip()
        self.config_data["voicevox_volume"] = self.voice_volume_var.get().strip()
        self.config_data["voicevox_intonation"] = self.voice_intonation_var.get().strip()
        self.config_data["voicevox_output"] = self.voice_output_var.get().strip()
        save_app_config(self.config_data)

    def start(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        self.start_button.configure(state="disabled")
        self.percent_var.set("0%")
        self.status_var.set("Đang bắt đầu...")
        self.log.delete("1.0", "end")
        self.worker = threading.Thread(target=self.create_video, daemon=True)
        self.worker.start()

    def ui(self, func, *args) -> None:
        self.after(0, lambda: func(*args))

    def create_valid_clip(
        self,
        videos: list[Path],
        clip_path: Path,
        *,
        clip_length: float,
        width: int,
        height: int,
        index: int,
        clip_count: int,
        encoder: str,
    ) -> None:
        last_error: Exception | None = None
        for attempt in range(1, 11):
            source = random.choice(videos)
            self.ui(
                self.write_log,
                f"[{index + 1}/{clip_count}] {source.name}" + (f" thử lại {attempt}" if attempt > 1 else ""),
            )
            try:
                create_clip(
                    source,
                    clip_path,
                    clip_length=clip_length,
                    width=width,
                    height=height,
                    encoder=encoder,
                )
                validate_video_file(clip_path)
                return
            except Exception as exc:
                last_error = exc
                clip_path.unlink(missing_ok=True)
                if encoder != "libx264":
                    self.ui(self.write_log, f"GPU encoder lỗi, thử lại bằng CPU: {exc}")
                    create_clip(
                        source,
                        clip_path,
                        clip_length=clip_length,
                        width=width,
                        height=height,
                        encoder="libx264",
                    )
                    validate_video_file(clip_path)
                    return
                self.ui(self.write_log, f"Bỏ qua clip lỗi từ {source.name}: {exc}")
        raise RuntimeError(f"Không tạo được clip hợp lệ sau 10 lần thử: {last_error}")

    def create_video(self) -> None:
        try:
            require_binary("ffmpeg")
            require_binary("ffprobe")

            srt = Path(self.srt_var.get()).resolve() if self.srt_var.get().strip() else Path()
            voice_audio: Path | None = None
            video_folder = Path(self.folder_var.get()).resolve()
            output = Path(self.output_var.get()).resolve()
            clip_length = float(self.clip_length_var.get())
            width = int(self.width_var.get())
            height = int(self.height_var.get())
            seed_text = self.seed_var.get().strip()
            encoder = choose_h264_encoder(self.use_gpu_var.get())

            if seed_text:
                random.seed(int(seed_text))
            if self.use_voicevox_var.get():
                voice_audio = Path(self.voice_output_var.get()).resolve()
                if voice_audio.suffix.lower() != ".wav":
                    voice_audio = voice_audio.with_suffix(".wav")
                    self.voice_output_var.set(str(voice_audio))
                srt = voice_audio.with_suffix(".srt")
                text_path = voice_audio.with_suffix(".txt")
                voice_text = self.voice_text.get("1.0", "end").strip()
                if voice_text:
                    voice_audio.parent.mkdir(parents=True, exist_ok=True)
                    old_text = text_path.read_text(encoding="utf-8-sig", errors="replace") if text_path.is_file() else ""
                    if old_text != voice_text:
                        text_path.write_text(voice_text, encoding="utf-8")
                elif not text_path.is_file():
                    selected_text_path = Path(self.text_var.get()).resolve()
                    if not selected_text_path.is_file():
                        raise ValueError(f"Chưa nhập nội dung đọc hoặc chọn file text: {selected_text_path}")
                    text_path = selected_text_path
                settings = VoicevoxSettings(
                    speaker=int(self.voice_speaker_var.get()),
                    pause_ms=int(self.voice_pause_var.get()),
                    speed=float(self.voice_speed_var.get()),
                    pitch=float(self.voice_pitch_var.get()),
                    volume=float(self.voice_volume_var.get()),
                    intonation=float(self.voice_intonation_var.get()),
                )
                self.ui(self.set_status, "Đang tạo voice VOICEVOX và SRT...")
                self.ui(self.write_log, f"VOICEVOX speaker={settings.speaker}, speed={settings.speed}, pitch={settings.pitch}, volume={settings.volume}, intonation={settings.intonation}, pause={settings.pause_ms}ms")
                synthesize_text_file(
                    text_path,
                    voice_audio,
                    srt,
                    settings,
                    progress=lambda text: (self.ui(self.set_status, text), self.ui(self.write_log, text)),
                )
                self.srt_var.set(str(srt))
                self.save_pexels_config()
                self.ui(self.write_log, f"Đã sẵn sàng audio: {voice_audio}")
                self.ui(self.write_log, f"Đã sẵn sàng SRT: {srt}")
            if not srt.is_file():
                raise ValueError(f"Không tìm thấy file SRT: {srt}")
            use_pexels = bool(self.use_pexels_var.get())
            if not use_pexels and not video_folder.is_dir():
                raise ValueError(f"Không tìm thấy folder video: {video_folder}")
            if clip_length <= 0:
                raise ValueError("Mỗi clip phải lớn hơn 0 giây")

            self.ui(self.set_status, "Đang đọc file SRT...")
            duration = srt_duration(srt)
            clip_count = math.ceil(duration / clip_length)
            only_16x9 = True if use_pexels else bool(self.only_16x9_var.get())
            if use_pexels:
                self.save_pexels_config()
                video_folder = Path.cwd() / "pexels_downloads" / srt.stem
                video_folder.mkdir(parents=True, exist_ok=True)
                pexels_threads = min(10, max(1, int(self.pexels_threads_var.get())))
                self.ui(self.set_status, "Đang tải video từ Pexels...")
                self.ui(self.write_log, f"Pexels: cần {clip_count} video 16:9 theo thời lượng SRT, tải {pexels_threads} luồng.")
                downloaded = download_pexels_videos(
                    api_key=self.pexels_api_key_var.get(),
                    query=self.pexels_query_var.get(),
                    output_dir=video_folder,
                    target_count=clip_count,
                    only_16x9=True,
                    target_width=width,
                    target_height=height,
                    max_workers=pexels_threads,
                    progress=lambda text: (self.ui(self.set_status, text), self.ui(self.write_log, text)),
                )
                self.ui(self.write_log, f"Đã sẵn sàng {len(downloaded)} video Pexels tại: {video_folder}")
            self.ui(
                self.set_status,
                "Đang lọc video ngang 16:9..." if only_16x9 else "Đang đọc danh sách video...",
            )

            def scan_progress(index: int, total: int, path: Path) -> None:
                if only_16x9:
                    text = f"Đang lọc video 16:9: {index}/{total} - {path.name}"
                else:
                    text = f"Đang đọc video: {index}/{total} - {path.name}"
                self.ui(self.set_status, text)

            videos = collect_videos(video_folder, only_16x9=only_16x9, progress=scan_progress)
            output.parent.mkdir(parents=True, exist_ok=True)

            self.ui(self.write_log, f"Encoder: {encoder}")
            self.ui(self.write_log, f"Thoi luong theo SRT: {duration:.2f}s")
            self.ui(self.write_log, f"So clip can tao: {clip_count}")
            self.ui(self.set_progress, 0, clip_count + 1)

            project_folder = None
            resume_manifest_path: Path | None = None
            if self.create_capcut_project_var.get():
                self.ui(self.set_status, "Đang tạo project CapCut trực tiếp...")
                resume_enabled = bool(self.resume_project_var.get())
                project_folder = prepare_capcut_project(srt.stem, resume=resume_enabled)
                clips_output_dir = project_folder / "Resources" / "auto_clips"
                if clips_output_dir.exists() and not resume_enabled:
                    shutil.rmtree(clips_output_dir)
                clips_output_dir.mkdir(parents=True, exist_ok=True)
                resume_manifest_path = project_folder / ".auto_resume.json"
                resume_config = {
                    "srt": str(srt),
                    "video_folder": str(video_folder),
                    "source": "pexels" if use_pexels else "folder",
                    "pexels_query": self.pexels_query_var.get().strip() if use_pexels else "",
                    "pexels_target_count": clip_count if use_pexels else "",
                    "pexels_threads": self.pexels_threads_var.get().strip() if use_pexels else "",
                    "duration": round(duration, 6),
                    "clip_count": clip_count,
                    "clip_length": clip_length,
                    "width": width,
                    "height": height,
                    "only_16x9": only_16x9,
                    "burn_subtitles": bool(self.burn_subtitles_var.get()),
                    "import_srt": bool(self.import_srt_var.get()),
                }
                old_config = None
                if resume_enabled and resume_manifest_path.is_file():
                    try:
                        old_config = json.loads(resume_manifest_path.read_text(encoding="utf-8"))
                    except Exception:
                        old_config = None
                if resume_enabled and old_config and old_config != resume_config:
                    self.ui(self.write_log, "Cấu hình đã thay đổi, xóa clip tạm cũ và tạo lại từ đầu.")
                    shutil.rmtree(clips_output_dir, ignore_errors=True)
                    clips_output_dir.mkdir(parents=True, exist_ok=True)
                resume_manifest_path.write_text(json.dumps(resume_config, ensure_ascii=False, indent=2), encoding="utf-8")
                self.ui(self.write_log, f"Project CapCut: {project_folder}")
                if resume_enabled:
                    self.ui(self.write_log, "Đã bật tiếp tục: clip nào đã tạo hợp lệ sẽ được bỏ qua.")
                self.ui(self.write_log, "Tool tự tạo project, không cần vào CapCut tạo dự án trống.")
            else:
                clips_output_dir = output.with_suffix("")
                clips_output_dir = clips_output_dir.parent / f"{clips_output_dir.name}_clips"
                if clips_output_dir.exists():
                    shutil.rmtree(clips_output_dir)
                clips_output_dir.mkdir(parents=True, exist_ok=True)

            with tempfile.TemporaryDirectory(prefix="capcut_render_") as temp_dir:
                temp_path = Path(temp_dir)
                clips: list[Path] = []
                clip_durations: list[float] = []
                output_created = False
                for index in range(clip_count):
                    start_time = index * clip_length
                    remaining = duration - start_time
                    current_clip_length = min(clip_length, remaining)
                    if current_clip_length <= 0:
                        break
                    clip_path = clips_output_dir / f"clip_{index + 1:04d}.mp4"
                    percent = round((index / (clip_count + 1)) * 100)
                    self.ui(
                        self.set_status,
                        f"Đang tạo clip {index + 1}/{clip_count} - {current_clip_length:.2f}s ({percent}%)",
                    )
                    reused_clip = False
                    if self.create_capcut_project_var.get() and self.resume_project_var.get() and clip_path.is_file():
                        try:
                            validate_video_file(clip_path)
                            reused_clip = True
                            self.ui(self.write_log, f"[{index + 1}/{clip_count}] Đã có, bỏ qua: {clip_path.name}")
                        except Exception:
                            clip_path.unlink(missing_ok=True)
                    if not reused_clip:
                        self.create_valid_clip(
                            videos,
                            clip_path,
                            clip_length=current_clip_length,
                            width=width,
                            height=height,
                            index=index,
                            clip_count=clip_count,
                            encoder=encoder,
                        )
                    clips.append(clip_path)
                    clip_durations.append(current_clip_length)
                    self.ui(self.set_progress, index + 1, clip_count + 1)

                if self.burn_subtitles_var.get():
                    raw_output = temp_path / "joined_without_subtitles.mp4"
                    subtitle_output = temp_path / "joined_with_subtitles.mp4" if voice_audio else output
                    self.ui(self.set_status, "Đang ghép video...")
                    concat_clips(clips, raw_output, duration)
                    self.ui(self.write_log, "Đang gắn phụ đề...")
                    self.ui(self.set_status, "Đang gắn phụ đề vào video...")
                    burn_subtitles(raw_output, srt, subtitle_output, width, height, encoder)
                    if voice_audio:
                        self.ui(self.write_log, "Đang ghép voice vào video...")
                        mux_audio(subtitle_output, voice_audio, output, duration)
                    output_created = True
                elif not self.create_capcut_project_var.get():
                    self.ui(self.write_log, "Đang ghép video...")
                    self.ui(self.set_status, "Đang ghép video...")
                    joined_output = temp_path / "joined_without_audio.mp4" if voice_audio else output
                    concat_clips(clips, joined_output, duration)
                    if voice_audio:
                        self.ui(self.write_log, "Đang ghép voice vào video...")
                        mux_audio(joined_output, voice_audio, output, duration)
                    output_created = True
                else:
                    self.ui(self.write_log, "Bỏ qua ghép output.mp4 vì đang tạo project CapCut có clip riêng lẻ.")

            self.ui(self.set_progress, clip_count + 1, clip_count + 1)
            if len(clips) != clip_count:
                raise RuntimeError(f"So clip tao duoc khong du: {len(clips)}/{clip_count}")
            if self.create_capcut_project_var.get():
                self.ui(self.set_status, "Đang tạo project CapCut...")
                project = create_capcut_project_from_clips(
                    clips,
                    project_name=srt.stem,
                    fallback_clip_duration=clip_length,
                    clip_durations=clip_durations,
                    srt_path=srt if self.import_srt_var.get() else None,
                    audio_path=voice_audio,
                    project_folder=project_folder,
                    clips_are_internal=project_folder is not None,
                    backup_project=False,
                )
                (project / ".auto_resume.json").unlink(missing_ok=True)
                self.ui(self.write_log, f"Đã tạo project CapCut: {project}")
            self.ui(self.set_status, "Hoàn tất 100%")
            if output_created:
                self.ui(self.write_log, f"Xong: {output}")
            self.ui(self.write_log, f"Clip riêng lẻ: {clips_output_dir}")
            self.open_result(output)
            done_text = f"Đã tạo project CapCut:\n{project}" if self.create_capcut_project_var.get() else f"Đã tạo video:\n{output}"
            self.ui(messagebox.showinfo, "Hoàn tất", done_text)
        except Exception as exc:
            self.ui(self.write_log, f"Lỗi: {exc}")
            self.ui(messagebox.showerror, "Lỗi", str(exc))
        finally:
            self.ui(self.start_button.configure, {"state": "normal"})

    def open_result(self, output: Path) -> None:
        if not self.open_capcut_var.get():
            return
        capcut_text = self.capcut_var.get().strip()
        capcut = Path(capcut_text) if capcut_text else None
        if capcut and capcut.is_file():
            subprocess.Popen([str(capcut)], close_fds=True)
            return
        os.startfile(output.parent)


def main() -> int:
    app = CapCutVideoApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
