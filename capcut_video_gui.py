#!/usr/bin/env python3
"""
Small Windows GUI for make_capcut_video.py.
"""

from __future__ import annotations

import math
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
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
from pexels_downloader import PEXELS_MAX_DOWNLOAD_WORKERS, download_pexels_videos, pexels_api_keys_from_env
from voicevox_tts import VoicevoxSettings, synthesize_text_file
from dotenv import load_dotenv
from fish_mexico_gui import (
    build_pause_units,
    build_s2_requests,
    fish_api_keys_from_env,
    merge_wavs_with_pauses,
    sanitize_problem_ellipsis,
    synthesize_fish_tts_units,
    write_srt_with_pauses,
)


APP_DIR = Path(__file__).resolve().parent
APP_CONFIG = APP_DIR / "config.json"
ENV_FILE = APP_DIR / ".env"
FISH_MEXICO_DIR = APP_DIR
FISH_MEXICO_GUI = APP_DIR / "fish_mexico_gui.py"
FISH_MEXICO_RUN = APP_DIR / "run_setting_fish.bat"
FISH_MEXICO_OUTPUT = APP_DIR / "02.OUTPUT"
FISH_MEXICO_SETTINGS = APP_DIR / "fish_story_v53_settings.json"
FISH_MEXICO_LANGUAGE = "Tiếng Tây Ban Nha Mexico"
FISH_MEXICO_LANGUAGE_CODE = "es-MX"
FISH_MEXICO_DEFAULT_VOICE = "3868fec905344d058c8d48b673277386"
FISH_LANGUAGE_NAMES = {
    "ja": "Tiếng Nhật",
    "zh-TW": "Tiếng Trung Đài Loan",
    "es-MX": "Tiếng Tây Ban Nha Mexico",
}
FISH_LANGUAGE_CODES = {value: key for key, value in FISH_LANGUAGE_NAMES.items()}
COMMON_CAPCUT_PATHS = [
    Path(os.environ.get("LOCALAPPDATA", "")) / "CapCut" / "Apps" / "CapCut.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "CapCut" / "CapCut.exe",
    Path(os.environ.get("PROGRAMFILES", "")) / "CapCut" / "CapCut.exe",
    Path(os.environ.get("PROGRAMFILES(X86)", "")) / "CapCut" / "CapCut.exe",
]


def app_launcher_args(*extra_args: str) -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, *extra_args]
    return [sys.executable, str(Path(__file__).resolve()), *extra_args]


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
        self.title("Tool Video CapCut")
        self.geometry("860x760")
        self.minsize(820, 720)
        self.config_data = load_app_config()

        self.srt_var = tk.StringVar()
        self.text_var = tk.StringVar(value=str(Path.cwd() / "index.txt"))
        self.voice_output_var = tk.StringVar(
            value=str(self.config_data.get("voicevox_output") or Path.cwd() / "voicevox_output" / "voice.wav")
        )
        self.use_voicevox_var = tk.BooleanVar(value=False)
        self.voice_engine_var = tk.StringVar(value=str(self.config_data.get("voice_engine") or "japan"))
        self.voice_speaker_var = tk.StringVar(value=str(self.config_data.get("voicevox_speaker") or "1"))
        self.voice_pause_var = tk.StringVar(value=str(self.config_data.get("voicevox_pause_ms") or "300"))
        self.voice_speed_var = tk.StringVar(value=str(self.config_data.get("voicevox_speed") or "1.0"))
        self.voice_pitch_var = tk.StringVar(value=str(self.config_data.get("voicevox_pitch") or "0.0"))
        self.voice_volume_var = tk.StringVar(value=str(self.config_data.get("voicevox_volume") or "1.0"))
        self.voice_intonation_var = tk.StringVar(value=str(self.config_data.get("voicevox_intonation") or "1.0"))
        saved_fish_language = str(self.config_data.get("fish_language") or FISH_MEXICO_LANGUAGE)
        if saved_fish_language not in FISH_LANGUAGE_CODES:
            saved_fish_language = FISH_MEXICO_LANGUAGE
        self.fish_language_var = tk.StringVar(value=saved_fish_language)
        self.fish_voice_display_var = tk.StringVar()
        self.fish_voice_lookup: dict[str, str] = {}
        self.fish_voice_id_var = tk.StringVar(
            value=str(self.config_data.get("fish_mexico_voice_id") or os.environ.get("REFERENCE_ID", "") or FISH_MEXICO_DEFAULT_VOICE)
        )
        saved_fish_output = str(self.config_data.get("fish_mexico_output") or "")
        if saved_fish_output and Path(saved_fish_output).suffix:
            fish_output_value = saved_fish_output
        else:
            fish_output_dir = Path(saved_fish_output) if saved_fish_output else FISH_MEXICO_OUTPUT
            fish_output_value = str(fish_output_dir / "voice.wav")
        self.fish_output_var = tk.StringVar(value=fish_output_value)
        self.fish_model_var = tk.StringVar(value=str(self.config_data.get("fish_mexico_model") or "s2.1-pro-free"))
        self.fish_speed_var = tk.StringVar(value=str(self.config_data.get("fish_mexico_speed") or "0.93"))
        self.fish_max_chars_var = tk.StringVar(value=str(self.config_data.get("fish_mexico_max_chars") or "100"))
        self.fish_retry_var = tk.StringVar(value=str(self.config_data.get("fish_mexico_retry") or "3"))
        self.fish_latency_var = tk.StringVar(value=str(self.config_data.get("fish_mexico_latency") or "normal"))
        self.fish_auto_s2_var = tk.BooleanVar(value=bool(self.config_data.get("fish_mexico_auto_s2", True)))
        self.fish_s2_mode_var = tk.StringVar(value=str(self.config_data.get("fish_mexico_s2_mode") or "natural"))
        self.fish_exact_pause_var = tk.BooleanVar(value=bool(self.config_data.get("fish_mexico_exact_pause", True)))
        self.fish_strict_commas_var = tk.BooleanVar(value=bool(self.config_data.get("fish_mexico_strict_commas", False)))
        self.fish_pause_comma_var = tk.StringVar(value=str(self.config_data.get("fish_mexico_pause_comma") or "100"))
        self.fish_pause_sentence_var = tk.StringVar(value=str(self.config_data.get("fish_mexico_pause_sentence") or "400"))
        self.fish_pause_question_var = tk.StringVar(value=str(self.config_data.get("fish_mexico_pause_question") or "500"))
        self.fish_pause_ellipsis_var = tk.StringVar(value=str(self.config_data.get("fish_mexico_pause_ellipsis") or "700"))
        self.fish_pause_paragraph_var = tk.StringVar(value=str(self.config_data.get("fish_mexico_pause_paragraph") or "900"))
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
        self.pexels_threads_var = tk.StringVar(value=str(self.config_data.get("pexels_threads") or PEXELS_MAX_DOWNLOAD_WORKERS))
        self.status_var = tk.StringVar(value="Sẵn sàng")
        self.percent_var = tk.StringVar(value="0%")
        self.fish_key_count_var = tk.StringVar(value="Fish API keys: 0")
        self.pexels_key_count_var = tk.StringVar(value="Pexels API keys: 0")
        self.new_fish_api_key_var = tk.StringVar()
        self.new_pexels_api_key_var = tk.StringVar()
        self.settings_status_var = tk.StringVar(value="")
        capcut = find_capcut()
        self.capcut_var = tk.StringVar(value=str(capcut) if capcut else "")

        self.worker: threading.Thread | None = None
        self._build_ui()
        self.reload_fish_voice_settings()

    def _build_ui(self) -> None:
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True)
        tool_tab = ttk.Frame(self.tabs)
        setting_tab = ttk.Frame(self.tabs, padding=18)
        self.tabs.add(tool_tab, text="Tool Video")
        self.tabs.add(setting_tab, text="Setting")
        self.tabs.bind("<<NotebookTabChanged>>", lambda _event: self.refresh_api_key_counts())

        scroll_host = ttk.Frame(tool_tab)
        scroll_host.pack(fill="both", expand=True)
        scroll_host.rowconfigure(0, weight=1)
        scroll_host.columnconfigure(0, weight=1)

        self.scroll_canvas = tk.Canvas(scroll_host, highlightthickness=0)
        self.scroll_canvas.grid(row=0, column=0, sticky="nsew")
        page_scrollbar = ttk.Scrollbar(scroll_host, orient="vertical", command=self.scroll_canvas.yview)
        page_scrollbar.grid(row=0, column=1, sticky="ns")
        self.scroll_canvas.configure(yscrollcommand=page_scrollbar.set)

        root = ttk.Frame(self.scroll_canvas, padding=18)
        self.scroll_window = self.scroll_canvas.create_window((0, 0), window=root, anchor="nw")
        root.bind(
            "<Configure>",
            lambda _event: self.scroll_canvas.configure(scrollregion=self.scroll_canvas.bbox("all")),
        )
        self.scroll_canvas.bind(
            "<Configure>",
            lambda event: self.scroll_canvas.itemconfigure(self.scroll_window, width=event.width),
        )
        self.bind_all("<MouseWheel>", self.on_mousewheel)
        self.bind_all("<Button-4>", self.on_mousewheel)
        self.bind_all("<Button-5>", self.on_mousewheel)
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
        self.voice_engine_frame = ttk.Frame(voice)
        self.voice_engine_frame.grid(row=0, column=6, columnspan=2, sticky="w", padx=(8, 0), pady=5)
        ttk.Radiobutton(
            self.voice_engine_frame,
            text="Nhật",
            variable=self.voice_engine_var,
            value="japan",
            command=self.update_voicevox_ui,
        ).pack(side="left", padx=(0, 12))
        ttk.Radiobutton(
            self.voice_engine_frame,
            text="Mexico",
            variable=self.voice_engine_var,
            value="mexico",
            command=self.update_voicevox_ui,
        ).pack(side="left")
        self.japan_voice_widgets = []
        speaker_label = ttk.Label(voice, text="Giọng")
        speaker_label.grid(row=0, column=2, sticky="e", padx=(8, 4))
        speaker_entry = ttk.Entry(voice, textvariable=self.voice_speaker_var, width=8)
        speaker_entry.grid(row=0, column=3, sticky="w")
        pause_label = ttk.Label(voice, text="Nghỉ ms")
        pause_label.grid(row=0, column=4, sticky="e", padx=(8, 4))
        pause_entry = ttk.Entry(voice, textvariable=self.voice_pause_var, width=8)
        pause_entry.grid(row=0, column=5, sticky="w")
        speed_label = ttk.Label(voice, text="Tốc độ")
        speed_label.grid(row=1, column=0, sticky="e", padx=(6, 4), pady=5)
        speed_entry = ttk.Entry(voice, textvariable=self.voice_speed_var, width=8)
        speed_entry.grid(row=1, column=1, sticky="w")
        pitch_label = ttk.Label(voice, text="Độ cao")
        pitch_label.grid(row=1, column=2, sticky="e", padx=(8, 4))
        pitch_entry = ttk.Entry(voice, textvariable=self.voice_pitch_var, width=8)
        pitch_entry.grid(row=1, column=3, sticky="w")
        volume_label = ttk.Label(voice, text="Âm lượng")
        volume_label.grid(row=1, column=4, sticky="e", padx=(8, 4))
        volume_entry = ttk.Entry(voice, textvariable=self.voice_volume_var, width=8)
        volume_entry.grid(row=1, column=5, sticky="w")
        intonation_label = ttk.Label(voice, text="Độ nhấn")
        intonation_label.grid(row=1, column=6, sticky="e", padx=(8, 4))
        intonation_entry = ttk.Entry(voice, textvariable=self.voice_intonation_var, width=8)
        intonation_entry.grid(row=1, column=7, sticky="w")
        self.japan_voice_widgets.extend(
            [
                speaker_label,
                speaker_entry,
                pause_label,
                pause_entry,
                speed_label,
                speed_entry,
                pitch_label,
                pitch_entry,
                volume_label,
                volume_entry,
                intonation_label,
                intonation_entry,
            ]
        )
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
        self.fish_mexico_frame = ttk.Frame(voice)
        self.fish_mexico_frame.grid(row=4, column=0, columnspan=8, sticky="ew", padx=6, pady=(4, 6))
        for index in range(8):
            self.fish_mexico_frame.columnconfigure(index, weight=1)
        ttk.Label(self.fish_mexico_frame, text="Ngôn ngữ").grid(row=0, column=0, sticky="w")
        self.fish_language_combo = ttk.Combobox(
            self.fish_mexico_frame,
            textvariable=self.fish_language_var,
            values=list(FISH_LANGUAGE_CODES.keys()),
            state="readonly",
        )
        self.fish_language_combo.grid(row=0, column=1, columnspan=2, sticky="ew", padx=(0, 8), pady=(0, 5))
        self.fish_language_combo.bind("<<ComboboxSelected>>", self.on_fish_language_selected)
        ttk.Label(self.fish_mexico_frame, text="Chọn giọng").grid(row=0, column=3, sticky="w")
        self.fish_voice_combo = ttk.Combobox(
            self.fish_mexico_frame,
            textvariable=self.fish_voice_display_var,
            state="readonly",
        )
        self.fish_voice_combo.grid(row=0, column=4, columnspan=2, sticky="ew", padx=(0, 8), pady=(0, 5))
        self.fish_voice_combo.bind("<<ComboboxSelected>>", self.on_fish_voice_selected)
        ttk.Button(self.fish_mexico_frame, text="Làm mới", command=self.reload_fish_voice_settings).grid(
            row=0, column=6, sticky="ew", padx=(0, 8), pady=(0, 5)
        )
        ttk.Button(self.fish_mexico_frame, text="Setting giọng", command=self.open_fish_mexico).grid(
            row=0, column=7, sticky="ew", pady=(0, 5)
        )

        ttk.Label(self.fish_mexico_frame, text="Voice ID đang dùng").grid(row=1, column=0, sticky="w")
        ttk.Entry(self.fish_mexico_frame, textvariable=self.fish_voice_id_var, state="readonly").grid(
            row=1, column=1, columnspan=7, sticky="ew", pady=(0, 5)
        )

        ttk.Label(self.fish_mexico_frame, text="Lưu voice/SRT").grid(row=2, column=0, sticky="w")
        ttk.Entry(self.fish_mexico_frame, textvariable=self.fish_output_var).grid(
            row=2, column=1, columnspan=6, sticky="ew", padx=(0, 8), pady=(0, 5)
        )
        ttk.Button(self.fish_mexico_frame, text="Chọn", command=self.pick_fish_output).grid(
            row=2, column=7, sticky="ew", pady=(0, 5)
        )

        ttk.Label(self.fish_mexico_frame, text="Model").grid(row=3, column=0, sticky="w")
        ttk.Combobox(
            self.fish_mexico_frame,
            textvariable=self.fish_model_var,
            values=["s2.1-pro-free", "s2.1-pro", "s2-pro"],
            state="readonly",
        ).grid(row=4, column=0, sticky="ew", padx=(0, 8))
        ttk.Label(self.fish_mexico_frame, text="Tốc độ").grid(row=3, column=1, sticky="w")
        ttk.Entry(self.fish_mexico_frame, textvariable=self.fish_speed_var, width=8).grid(row=4, column=1, sticky="ew", padx=(0, 8))
        ttk.Label(self.fish_mexico_frame, text="Ký tự / câu").grid(row=3, column=2, sticky="w")
        ttk.Entry(self.fish_mexico_frame, textvariable=self.fish_max_chars_var, width=8).grid(row=4, column=2, sticky="ew", padx=(0, 8))
        ttk.Label(self.fish_mexico_frame, text="Thử lại").grid(row=3, column=3, sticky="w")
        ttk.Entry(self.fish_mexico_frame, textvariable=self.fish_retry_var, width=8).grid(row=4, column=3, sticky="ew", padx=(0, 8))
        ttk.Label(self.fish_mexico_frame, text="API").grid(row=3, column=4, sticky="w")
        ttk.Combobox(
            self.fish_mexico_frame,
            textvariable=self.fish_latency_var,
            values=["normal", "balanced"],
            state="readonly",
            width=10,
        ).grid(row=4, column=4, sticky="ew", padx=(0, 8))
        ttk.Checkbutton(
            self.fish_mexico_frame,
            text="S2 tự động",
            variable=self.fish_auto_s2_var,
        ).grid(row=4, column=5, sticky="w")
        ttk.Label(self.fish_mexico_frame, text="Mức diễn").grid(row=3, column=6, sticky="w")
        ttk.Combobox(
            self.fish_mexico_frame,
            textvariable=self.fish_s2_mode_var,
            values=["natural", "drama", "strong"],
            state="readonly",
        ).grid(row=4, column=6, columnspan=2, sticky="ew")

        ttk.Checkbutton(
            self.fish_mexico_frame,
            text="Bật chèn im lặng thật",
            variable=self.fish_exact_pause_var,
        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(7, 0))
        ttk.Checkbutton(
            self.fish_mexico_frame,
            text="Ép dừng cả dấu phẩy",
            variable=self.fish_strict_commas_var,
        ).grid(row=5, column=2, columnspan=3, sticky="w", pady=(7, 0))

        pause_fields = [
            ("Dấu phẩy", self.fish_pause_comma_var),
            ("Dấu chấm", self.fish_pause_sentence_var),
            ("? / !", self.fish_pause_question_var),
            ("Dấu ...", self.fish_pause_ellipsis_var),
            ("Xuống đoạn", self.fish_pause_paragraph_var),
        ]
        for index, (label, variable) in enumerate(pause_fields):
            ttk.Label(self.fish_mexico_frame, text=label).grid(row=6, column=index, sticky="w", pady=(5, 0))
            ttk.Entry(self.fish_mexico_frame, textvariable=variable, width=8).grid(
                row=7, column=index, sticky="ew", padx=(0, 8)
            )
        ttk.Button(self.fish_mexico_frame, text="Preset tự nhiên", command=lambda: self.apply_fish_pause_preset("natural")).grid(
            row=7, column=5, sticky="ew", padx=(0, 8)
        )
        ttk.Button(self.fish_mexico_frame, text="Preset drama", command=lambda: self.apply_fish_pause_preset("drama")).grid(
            row=7, column=6, columnspan=2, sticky="ew"
        )
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
        self._build_settings_ui(setting_tab)
        self.refresh_api_key_counts()
        self.update_source_ui()
        self.update_voicevox_ui()

    def _build_settings_ui(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        ttk.Label(parent, text="API keys").grid(row=0, column=0, sticky="w", pady=(0, 12))

        fish = ttk.LabelFrame(parent, text="Fish")
        fish.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        fish.columnconfigure(1, weight=1)
        ttk.Label(fish, textvariable=self.fish_key_count_var).grid(row=0, column=0, columnspan=3, sticky="w", padx=10, pady=(8, 6))
        ttk.Label(fish, text="API key mới").grid(row=1, column=0, sticky="w", padx=10, pady=(0, 10))
        ttk.Entry(fish, textvariable=self.new_fish_api_key_var, show="*").grid(
            row=1, column=1, sticky="ew", padx=(0, 8), pady=(0, 10)
        )
        ttk.Button(fish, text="Thêm", command=lambda: self.add_api_key("fish")).grid(
            row=1, column=2, sticky="ew", padx=(0, 10), pady=(0, 10)
        )

        pexels = ttk.LabelFrame(parent, text="Pexels")
        pexels.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        pexels.columnconfigure(1, weight=1)
        ttk.Label(pexels, textvariable=self.pexels_key_count_var).grid(row=0, column=0, columnspan=3, sticky="w", padx=10, pady=(8, 6))
        ttk.Label(pexels, text="API key mới").grid(row=1, column=0, sticky="w", padx=10, pady=(0, 10))
        ttk.Entry(pexels, textvariable=self.new_pexels_api_key_var, show="*").grid(
            row=1, column=1, sticky="ew", padx=(0, 8), pady=(0, 10)
        )
        ttk.Button(pexels, text="Thêm", command=lambda: self.add_api_key("pexels")).grid(
            row=1, column=2, sticky="ew", padx=(0, 10), pady=(0, 10)
        )

        controls = ttk.Frame(parent)
        controls.grid(row=3, column=0, sticky="ew", pady=(4, 0))
        ttk.Label(controls, textvariable=self.settings_status_var).pack(side="left")

    def refresh_api_key_counts(self) -> None:
        load_dotenv(ENV_FILE, override=True)
        fish_count = len(fish_api_keys_from_env())
        pexels_count = len(pexels_api_keys_from_env())
        self.fish_key_count_var.set(f"Tổng key hiện tại: {fish_count}")
        self.pexels_key_count_var.set(f"Tổng key hiện tại: {pexels_count}")

    def _append_env_list_value(self, variable_name: str, value: str) -> None:
        text = ENV_FILE.read_text(encoding="utf-8-sig") if ENV_FILE.is_file() else ""
        lines = text.splitlines()
        pattern = re.compile(rf"^\s*{re.escape(variable_name)}\s*=")
        for index, line in enumerate(lines):
            if not pattern.match(line):
                continue
            current = line.split("=", 1)[1].strip()
            lines[index] = f"{variable_name}={current},{value}" if current else f"{variable_name}={value}"
            break
        else:
            if lines and lines[-1].strip():
                lines.append(f"{variable_name}={value}")
            elif lines:
                lines[-1] = f"{variable_name}={value}"
            else:
                lines.append(f"{variable_name}={value}")
        ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def add_api_key(self, provider: str) -> None:
        load_dotenv(ENV_FILE, override=True)
        if provider == "fish":
            entry_var = self.new_fish_api_key_var
            list_var = "FISH_API_KEYS"
            existing = set(fish_api_keys_from_env())
            label = "Fish"
        else:
            entry_var = self.new_pexels_api_key_var
            list_var = "PEXELS_API_KEYS"
            existing = set(pexels_api_keys_from_env())
            label = "Pexels"

        api_key = entry_var.get().strip()
        if not api_key:
            messagebox.showwarning("Thiếu API key", f"Bạn chưa nhập {label} API key.")
            return
        if api_key in existing:
            messagebox.showinfo("API key đã có", f"{label} API key này đã tồn tại trong .env.")
            entry_var.set("")
            return

        self._append_env_list_value(list_var, api_key)
        load_dotenv(ENV_FILE, override=True)
        entry_var.set("")
        self.refresh_api_key_counts()
        self.settings_status_var.set(f"Đã thêm {label} API key vào .env")

    def _path_row(self, parent: ttk.Frame, row: int, label: str, variable: tk.StringVar, command) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=5)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=8, pady=5)
        ttk.Button(parent, text="Chọn", command=command).grid(row=row, column=2, sticky="ew", pady=5)

    def on_mousewheel(self, event) -> None:
        if not hasattr(self, "scroll_canvas"):
            return
        if getattr(event, "num", None) == 4:
            delta = -1
        elif getattr(event, "num", None) == 5:
            delta = 1
        else:
            delta = -1 * int(event.delta / 120) if event.delta else 0
        if delta:
            self.scroll_canvas.yview_scroll(delta, "units")

    def update_voicevox_ui(self) -> None:
        if self.use_voicevox_var.get():
            self.srt_row.grid_remove()
            self.voice_engine_frame.grid()
            if self.voice_engine_var.get() == "mexico":
                for widget in self.japan_voice_widgets:
                    widget.grid_remove()
                self.voice_output_row.grid_remove()
                self.voice_text_frame.grid()
                self.fish_mexico_frame.grid()
            else:
                for widget in self.japan_voice_widgets:
                    widget.grid()
                self.voice_output_row.grid()
                self.voice_text_frame.grid()
                self.fish_mexico_frame.grid_remove()
        else:
            self.srt_row.grid()
            self.voice_engine_frame.grid_remove()
            for widget in self.japan_voice_widgets:
                widget.grid_remove()
            self.voice_output_row.grid_remove()
            self.voice_text_frame.grid_remove()
            self.fish_mexico_frame.grid_remove()

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

    def pick_fish_output(self) -> None:
        current = Path(self.fish_output_var.get().strip() or (FISH_MEXICO_OUTPUT / "voice.wav"))
        initialdir = current.parent if current.suffix else current
        initialfile = current.name if current.suffix else "voice.wav"
        path = filedialog.asksaveasfilename(
            defaultextension=".wav",
            initialdir=str(initialdir),
            initialfile=initialfile,
            filetypes=[("WAV audio", "*.wav"), ("All files", "*.*")],
        )
        if path:
            self.fish_output_var.set(path)

    def apply_fish_pause_preset(self, preset: str) -> None:
        if preset == "drama":
            values = ("150", "480", "620", "900", "1200")
        else:
            values = ("100", "400", "500", "700", "900")
        for variable, value in zip(
            (
                self.fish_pause_comma_var,
                self.fish_pause_sentence_var,
                self.fish_pause_question_var,
                self.fish_pause_ellipsis_var,
                self.fish_pause_paragraph_var,
            ),
            values,
        ):
            variable.set(value)

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

    def open_fish_mexico(self) -> None:
        if not FISH_MEXICO_RUN.is_file():
            messagebox.showerror("Fish Mexico", f"Không tìm thấy run_setting_fish.bat:\n{FISH_MEXICO_RUN}")
            return
        if FISH_MEXICO_SETTINGS.is_file():
            try:
                settings = json.loads(FISH_MEXICO_SETTINGS.read_text(encoding="utf-8-sig"))
                if isinstance(settings, dict):
                    settings["last_language"] = self.current_fish_language_code()
                    FISH_MEXICO_SETTINGS.write_text(
                        json.dumps(settings, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
            except Exception:
                pass
        try:
            subprocess.Popen(
                app_launcher_args("--fish-settings"),
                cwd=str(FISH_MEXICO_DIR),
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except Exception as exc:
            messagebox.showerror("Fish Mexico", f"Không mở được Fish GUI:\n{exc}")
            return
        self.status_var.set("Đã mở setting giọng Fish. Lưu xong quay lại bấm Làm mới.")

    def latest_fish_mexico_outputs(self) -> tuple[Path, Path]:
        if not FISH_MEXICO_OUTPUT.is_dir():
            raise ValueError(f"Không tìm thấy thư mục output Fish: {FISH_MEXICO_OUTPUT}")
        jobs = [path for path in FISH_MEXICO_OUTPUT.iterdir() if path.is_dir()]
        jobs.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        for job in jobs:
            wav = job / "final.wav"
            srt_files = sorted(
                list(job.glob("final*.srt")) + list(job.glob("*.srt")),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
            if wav.is_file() and srt_files:
                return wav, srt_files[0]
        raise ValueError("Chưa thấy final.wav và final*.srt trong output Fish Mexico.")

    def write_log(self, text: str) -> None:
        self.log.insert("end", text + "\n")
        self.log.see("end")

    def write_fish_log(self, text: str) -> None:
        self.write_log(text)

    def set_progress(self, value: int, maximum: int) -> None:
        self.progress.configure(maximum=maximum, value=value)
        percent = 0 if maximum <= 0 else round((value / maximum) * 100)
        self.percent_var.set(f"{percent}%")

    def set_status(self, text: str) -> None:
        self.status_var.set(text)

    def current_fish_language_code(self) -> str:
        return FISH_LANGUAGE_CODES.get(self.fish_language_var.get(), FISH_MEXICO_LANGUAGE_CODE)

    @staticmethod
    def fish_preset_key(language_code: str, voice_id: str) -> str:
        return f"{language_code}::{voice_id or '__fish_default__'}"

    def load_fish_settings(self) -> dict:
        if not FISH_MEXICO_SETTINGS.is_file():
            return {}
        try:
            data = json.loads(FISH_MEXICO_SETTINGS.read_text(encoding="utf-8-sig"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def apply_fish_preset(self, preset: dict) -> None:
        if not isinstance(preset, dict):
            return
        mapping = {
            "model": self.fish_model_var,
            "speed": self.fish_speed_var,
            "max_chars": self.fish_max_chars_var,
            "retry_count": self.fish_retry_var,
            "latency_mode": self.fish_latency_var,
            "s2_cue_mode": self.fish_s2_mode_var,
            "pause_comma": self.fish_pause_comma_var,
            "pause_sentence": self.fish_pause_sentence_var,
            "pause_question": self.fish_pause_question_var,
            "pause_ellipsis": self.fish_pause_ellipsis_var,
            "pause_paragraph": self.fish_pause_paragraph_var,
        }
        for key, variable in mapping.items():
            if key in preset:
                variable.set(str(preset[key]))
        if "auto_s2_cues" in preset:
            self.fish_auto_s2_var.set(bool(preset["auto_s2_cues"]))
        if "exact_pause" in preset:
            self.fish_exact_pause_var.set(bool(preset["exact_pause"]))
        if "strict_commas" in preset:
            self.fish_strict_commas_var.set(bool(preset["strict_commas"]))

    def reload_fish_voice_settings(self) -> None:
        data = self.load_fish_settings()
        language_code = self.current_fish_language_code()
        voice_languages = data.get("voice_languages", {}) if isinstance(data.get("voice_languages"), dict) else {}
        manual_voices = data.get("manual_voices", {}) if isinstance(data.get("manual_voices"), dict) else {}
        last_by_language = data.get("last_voice_by_language", {}) if isinstance(data.get("last_voice_by_language"), dict) else {}

        lookup: dict[str, str] = {}
        for voice_id, assigned_language in voice_languages.items():
            if assigned_language != language_code:
                continue
            title = manual_voices.get(voice_id, {}).get("title") if isinstance(manual_voices.get(voice_id), dict) else ""
            label = title or ("Mexico Story Voice" if voice_id == FISH_MEXICO_DEFAULT_VOICE else "Fish Voice")
            display = f"{label}  —  {voice_id[:10]}..."
            lookup[display] = voice_id
        for voice_id, info in manual_voices.items():
            if voice_id in lookup.values():
                continue
            if info.get("language_code") != language_code and voice_languages.get(voice_id) != language_code:
                continue
            title = info.get("title") or "Thủ công"
            lookup[f"{title}  —  {voice_id[:10]}..."] = voice_id

        default_voice = last_by_language.get(language_code) or (FISH_MEXICO_DEFAULT_VOICE if language_code == FISH_MEXICO_LANGUAGE_CODE else "")
        if default_voice and default_voice not in lookup.values():
            lookup[f"[Đã lưu] {default_voice[:10]}..."] = default_voice

        self.fish_voice_lookup = lookup
        displays = list(lookup.keys())
        if hasattr(self, "fish_voice_combo"):
            self.fish_voice_combo.configure(values=displays)
        selected = next((display for display, voice_id in lookup.items() if voice_id == self.fish_voice_id_var.get().strip()), "")
        if not selected and default_voice:
            selected = next((display for display, voice_id in lookup.items() if voice_id == default_voice), "")
            self.fish_voice_id_var.set(default_voice)
        if not selected and displays:
            selected = displays[0]
            self.fish_voice_id_var.set(lookup[selected])
        self.fish_voice_display_var.set(selected)

        presets = data.get("voice_presets", {}) if isinstance(data.get("voice_presets"), dict) else {}
        preset = presets.get(self.fish_preset_key(language_code, self.fish_voice_id_var.get().strip()))
        if not preset:
            preset = presets.get(self.fish_preset_key(language_code, "__fish_default__"))
        self.apply_fish_preset(preset or {})

    def on_fish_language_selected(self, _event=None) -> None:
        language_code = self.current_fish_language_code()
        data = self.load_fish_settings()
        last_by_language = data.get("last_voice_by_language", {}) if isinstance(data.get("last_voice_by_language"), dict) else {}
        self.fish_voice_id_var.set(last_by_language.get(language_code, ""))
        self.reload_fish_voice_settings()

    def on_fish_voice_selected(self, _event=None) -> None:
        voice_id = self.fish_voice_lookup.get(self.fish_voice_display_var.get(), "")
        self.fish_voice_id_var.set(voice_id)
        self.reload_fish_voice_settings()

    def save_pexels_config(self) -> None:
        self.config_data.pop("pexels_api_key", None)
        self.config_data["pexels_query"] = self.pexels_query_var.get().strip()
        self.config_data["pexels_threads"] = self.pexels_threads_var.get().strip()
        self.config_data["voicevox_speaker"] = self.voice_speaker_var.get().strip()
        self.config_data["voicevox_pause_ms"] = self.voice_pause_var.get().strip()
        self.config_data["voicevox_speed"] = self.voice_speed_var.get().strip()
        self.config_data["voicevox_pitch"] = self.voice_pitch_var.get().strip()
        self.config_data["voicevox_volume"] = self.voice_volume_var.get().strip()
        self.config_data["voicevox_intonation"] = self.voice_intonation_var.get().strip()
        self.config_data["voicevox_output"] = self.voice_output_var.get().strip()
        self.config_data["voice_engine"] = self.voice_engine_var.get().strip()
        self.config_data["fish_language"] = self.fish_language_var.get().strip()
        self.config_data["fish_mexico_voice_id"] = self.fish_voice_id_var.get().strip()
        self.config_data["fish_mexico_output"] = self.fish_output_var.get().strip()
        self.config_data["fish_mexico_model"] = self.fish_model_var.get().strip()
        self.config_data["fish_mexico_speed"] = self.fish_speed_var.get().strip()
        self.config_data["fish_mexico_max_chars"] = self.fish_max_chars_var.get().strip()
        self.config_data["fish_mexico_retry"] = self.fish_retry_var.get().strip()
        self.config_data["fish_mexico_latency"] = self.fish_latency_var.get().strip()
        self.config_data["fish_mexico_auto_s2"] = bool(self.fish_auto_s2_var.get())
        self.config_data["fish_mexico_s2_mode"] = self.fish_s2_mode_var.get().strip()
        self.config_data["fish_mexico_exact_pause"] = bool(self.fish_exact_pause_var.get())
        self.config_data["fish_mexico_strict_commas"] = bool(self.fish_strict_commas_var.get())
        self.config_data["fish_mexico_pause_comma"] = self.fish_pause_comma_var.get().strip()
        self.config_data["fish_mexico_pause_sentence"] = self.fish_pause_sentence_var.get().strip()
        self.config_data["fish_mexico_pause_question"] = self.fish_pause_question_var.get().strip()
        self.config_data["fish_mexico_pause_ellipsis"] = self.fish_pause_ellipsis_var.get().strip()
        self.config_data["fish_mexico_pause_paragraph"] = self.fish_pause_paragraph_var.get().strip()
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
                    try:
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
                    except Exception as cpu_exc:
                        last_error = cpu_exc
                        clip_path.unlink(missing_ok=True)
                        self.ui(self.write_log, f"CPU fallback also failed for {source.name}: {cpu_exc}")
                        continue
                self.ui(self.write_log, f"Bỏ qua clip lỗi từ {source.name}: {exc}")
        raise RuntimeError(f"Không tạo được clip hợp lệ sau 10 lần thử: {last_error}")

    def burn_subtitles_with_fallback(
        self,
        input_video: Path,
        srt: Path,
        output: Path,
        width: int,
        height: int,
        encoder: str,
    ) -> None:
        try:
            burn_subtitles(input_video, srt, output, width, height, encoder)
        except Exception as exc:
            if encoder == "libx264":
                raise
            self.ui(self.write_log, f"GPU encoder failed while burning subtitles, retrying with CPU: {exc}")
            output.unlink(missing_ok=True)
            burn_subtitles(input_video, srt, output, width, height, "libx264")

    def fish_mexico_text_path(self) -> Path:
        output_audio = Path(self.fish_output_var.get().strip() or (FISH_MEXICO_OUTPUT / "voice.wav")).resolve()
        if output_audio.suffix.lower() != ".wav":
            output_audio = output_audio.with_suffix(".wav")
            self.fish_output_var.set(str(output_audio))
        text_path = output_audio.with_suffix(".txt")
        voice_text = self.voice_text.get("1.0", "end").strip()
        if voice_text:
            output_audio.parent.mkdir(parents=True, exist_ok=True)
            text_path.write_text(voice_text, encoding="utf-8")
            return text_path
        selected_text_path = Path(self.text_var.get()).resolve()
        if not selected_text_path.is_file():
            raise ValueError(f"Chưa nhập nội dung đọc hoặc chọn file text: {selected_text_path}")
        return selected_text_path

    @staticmethod
    def fish_outputs_are_current(text_path: Path, wav_path: Path, srt_path: Path) -> bool:
        if not text_path.is_file() or not wav_path.is_file() or not srt_path.is_file():
            return False
        if wav_path.stat().st_size <= 0 or srt_path.stat().st_size <= 0:
            return False
        text_mtime = text_path.stat().st_mtime
        return min(wav_path.stat().st_mtime, srt_path.stat().st_mtime) >= text_mtime

    def synthesize_fish_mexico(self) -> tuple[Path, Path]:
        load_dotenv(APP_DIR / ".env", override=True)
        api_keys = fish_api_keys_from_env()
        if not api_keys:
            raise RuntimeError("Chưa có FISH_API_KEY trong file .env")

        text_path = self.fish_mexico_text_path()
        final_wav = Path(self.fish_output_var.get().strip() or (FISH_MEXICO_OUTPUT / "voice.wav")).resolve()
        if final_wav.suffix.lower() != ".wav":
            final_wav = final_wav.with_suffix(".wav")
            self.fish_output_var.set(str(final_wav))
        final_wav.parent.mkdir(parents=True, exist_ok=True)
        final_srt = final_wav.with_suffix(".srt")
        if self.fish_outputs_are_current(text_path, final_wav, final_srt):
            self.ui(self.write_fish_log, f"Fish Mexico bỏ qua, đã có sẵn: {final_wav.name}, {final_srt.name}")
            return final_wav, final_srt

        text = text_path.read_text(encoding="utf-8-sig", errors="replace").strip()
        if not text:
            raise ValueError("Nội dung đọc Mexico đang trống.")

        try:
            speed = float(self.fish_speed_var.get().strip())
            max_chars = int(self.fish_max_chars_var.get().strip())
            retry_count = int(self.fish_retry_var.get().strip())
            pause_values = {
                "comma_ms": int(self.fish_pause_comma_var.get().strip()),
                "sentence_ms": int(self.fish_pause_sentence_var.get().strip()),
                "question_ms": int(self.fish_pause_question_var.get().strip()),
                "ellipsis_ms": int(self.fish_pause_ellipsis_var.get().strip()),
                "paragraph_ms": int(self.fish_pause_paragraph_var.get().strip()),
            }
        except ValueError as exc:
            raise ValueError("Setting Mexico phải là số hợp lệ.") from exc
        if speed <= 0 or max_chars <= 0 or retry_count < 0:
            raise ValueError("Tốc độ, ký tự/câu hoặc số lần thử lại Mexico không hợp lệ.")
        cleaned_text, ellipsis_report = sanitize_problem_ellipsis(text, pause_values["ellipsis_ms"])
        units = build_pause_units(
            cleaned_text,
            max_chars,
            pause_values["comma_ms"],
            pause_values["sentence_ms"],
            pause_values["question_ms"],
            pause_values["ellipsis_ms"],
            pause_values["paragraph_ms"],
            bool(self.fish_strict_commas_var.get()),
        )
        if not units:
            raise RuntimeError("Không tách được nội dung Mexico thành câu đọc.")
        if not self.fish_exact_pause_var.get():
            for unit in units:
                unit["pause_ms"] = 0

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        job_dir = final_wav.parent / ".fish_mexico_jobs" / f"{final_wav.stem}_{timestamp}"
        chunks_dir = job_dir / "chunks"
        chunks_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "script_used.txt").write_text(text, encoding="utf-8")
        (job_dir / "script_tts_cleaned.txt").write_text(cleaned_text, encoding="utf-8")
        (job_dir / "ellipsis_cleanup_report.txt").write_text(
            "\n".join(ellipsis_report) if ellipsis_report else "Không có dòng dấu ba chấm cần xử lý.\n",
            encoding="utf-8",
        )

        reference_id = self.fish_voice_id_var.get().strip()
        language_code = self.current_fish_language_code()
        s2_requests = (
            build_s2_requests(units, self.fish_s2_mode_var.get().strip() or "natural", language_code)
            if self.fish_auto_s2_var.get()
            else [unit["text"] for unit in units]
        )
        self.ui(self.write_fish_log, f"Fish Mexico: chia thành {len(units)} câu đọc.")
        self.ui(self.write_fish_log, f"Fish Mexico voice_id={reference_id or 'default'}, speed={speed}, max_chars={max_chars}")
        worker_count = max(1, min(len(api_keys), len(units)))
        self.ui(self.write_fish_log, f"Fish API keys: {len(api_keys)}; chay song song {worker_count} luong.")

        def on_error(index, attempt, key_number, exc):
            self.ui(self.write_fish_log, f"Fish Mexico loi cau {index}, key #{key_number}, lan {attempt}: {exc}")

        def on_progress(done, total, result, workers):
            self.ui(self.set_status, f"Fish Mexico da tao {done}/{total}")
            self.ui(self.set_progress, done, total)
            self.ui(self.write_fish_log, f"Fish Mexico OK {result['index']}/{total}: {result['duration']:.2f}s")

        results = synthesize_fish_tts_units(
            units=units,
            s2_requests=s2_requests,
            chunks_dir=chunks_dir,
            model=self.fish_model_var.get().strip() or "s2.1-pro-free",
            speed=speed,
            latency=self.fish_latency_var.get().strip() or "normal",
            reference_id=reference_id,
            retry_count=retry_count,
            api_keys=api_keys,
            on_error=on_error,
            on_progress=on_progress,
        )
        wav_paths = [result["output_path"] for result in results]
        durations = [result["duration"] for result in results]
        pauses_ms = [result["pause_ms"] for result in results]
        pause_plan_lines = [result["pause_plan_line"] for result in results]
        s2_plan_lines = [result["s2_plan_line"] for result in results]
        tagged_blocks = list(s2_requests)

        merge_wavs_with_pauses(wav_paths, pauses_ms, final_wav)
        write_srt_with_pauses(units, durations, final_srt)
        (job_dir / "pause_plan.txt").write_text("\n".join(pause_plan_lines), encoding="utf-8")
        (job_dir / "script_s2_tagged.txt").write_text("\n\n".join(tagged_blocks), encoding="utf-8")
        (job_dir / "s2_tag_plan.txt").write_text("\n".join(s2_plan_lines), encoding="utf-8")
        self.ui(self.set_progress, len(units), len(units))
        self.ui(self.write_fish_log, f"Fish Mexico audio: {final_wav}")
        self.ui(self.write_fish_log, f"Fish Mexico SRT: {final_srt}")
        return final_wav, final_srt

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
            if self.use_voicevox_var.get() and self.voice_engine_var.get() == "mexico":
                self.ui(self.set_status, "Đang tạo voice Fish Mexico và SRT...")
                voice_audio, srt = self.synthesize_fish_mexico()
                self.srt_var.set(str(srt))
                self.save_pexels_config()
            elif self.use_voicevox_var.get():
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
                load_dotenv(APP_DIR / ".env", override=True)
                self.save_pexels_config()
                video_folder = Path.cwd() / "pexels_downloads" / srt.stem
                video_folder.mkdir(parents=True, exist_ok=True)
                pexels_threads = min(PEXELS_MAX_DOWNLOAD_WORKERS, max(1, int(self.pexels_threads_var.get())))
                self.ui(self.set_status, "Đang tải video từ Pexels...")
                self.ui(self.write_log, f"Pexels: cần {clip_count} video 16:9 theo thời lượng SRT, tải {pexels_threads} luồng.")
                downloaded = download_pexels_videos(
                    api_key=os.environ.get("PEXELS_API_KEY", ""),
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
            if self.use_gpu_var.get() and encoder != "libx264":
                self.ui(self.write_fish_log if self.voice_engine_var.get() == "mexico" else self.write_log, f"GPU đang bật cho bước dựng video: {encoder}")
            elif self.use_gpu_var.get():
                self.ui(self.write_fish_log if self.voice_engine_var.get() == "mexico" else self.write_log, "GPU không khả dụng, dựng video bằng CPU libx264.")
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
                    self.burn_subtitles_with_fallback(raw_output, srt, subtitle_output, width, height, encoder)
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
    if "--fish-settings" in sys.argv[1:]:
        import fish_mexico_gui

        fish_mexico_gui.main()
        return 0

    load_dotenv(APP_DIR / ".env", override=True)
    app = CapCutVideoApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
