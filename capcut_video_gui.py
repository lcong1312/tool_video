#!/usr/bin/env python3
"""
Small Windows GUI for make_capcut_video.py.
"""

from __future__ import annotations

import math
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
    require_binary,
    srt_duration,
    validate_video_file,
)
from capcut_draft import (
    create_capcut_project_from_clips,
    prepare_capcut_project,
)


COMMON_CAPCUT_PATHS = [
    Path(os.environ.get("LOCALAPPDATA", "")) / "CapCut" / "Apps" / "CapCut.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "CapCut" / "CapCut.exe",
    Path(os.environ.get("PROGRAMFILES", "")) / "CapCut" / "CapCut.exe",
    Path(os.environ.get("PROGRAMFILES(X86)", "")) / "CapCut" / "CapCut.exe",
]


def find_capcut() -> Path | None:
    for path in COMMON_CAPCUT_PATHS:
        if path.is_file():
            return path
    return None


class CapCutVideoApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("SRT to CapCut Video")
        self.geometry("760x520")
        self.minsize(720, 500)

        self.srt_var = tk.StringVar()
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
        self.create_capcut_project_var = tk.BooleanVar(value=True)
        self.open_capcut_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="San sang")
        self.percent_var = tk.StringVar(value="0%")
        capcut = find_capcut()
        self.capcut_var = tk.StringVar(value=str(capcut) if capcut else "")

        self.worker: threading.Thread | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=18)
        root.pack(fill="both", expand=True)
        root.columnconfigure(1, weight=1)

        self._path_row(root, 0, "File SRT", self.srt_var, self.pick_srt)
        self._path_row(root, 1, "Folder video", self.folder_var, self.pick_folder)
        self._path_row(root, 2, "File xuat", self.output_var, self.pick_output)
        self._path_row(root, 3, "CapCut.exe", self.capcut_var, self.pick_capcut)

        options = ttk.Frame(root)
        options.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(14, 8))
        for index in range(8):
            options.columnconfigure(index, weight=1)

        ttk.Label(options, text="Moi clip").grid(row=0, column=0, sticky="w")
        ttk.Entry(options, textvariable=self.clip_length_var, width=8).grid(row=0, column=1, sticky="w")
        ttk.Label(options, text="giay").grid(row=0, column=2, sticky="w", padx=(4, 18))

        ttk.Label(options, text="Kich thuoc").grid(row=0, column=3, sticky="w")
        ttk.Entry(options, textvariable=self.width_var, width=8).grid(row=0, column=4, sticky="w")
        ttk.Label(options, text="x").grid(row=0, column=5, sticky="w", padx=4)
        ttk.Entry(options, textvariable=self.height_var, width=8).grid(row=0, column=6, sticky="w")

        ttk.Label(options, text="Seed").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(options, textvariable=self.seed_var, width=12).grid(row=1, column=1, sticky="w", pady=(8, 0))
        ttk.Checkbutton(options, text="Burn subtitle vao video", variable=self.burn_subtitles_var).grid(
            row=1, column=3, columnspan=2, sticky="w", pady=(8, 0)
        )
        ttk.Checkbutton(options, text="Tao project CapCut", variable=self.create_capcut_project_var).grid(
            row=1, column=5, columnspan=3, sticky="w", pady=(8, 0)
        )
        ttk.Checkbutton(options, text="Dung GPU", variable=self.use_gpu_var).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(8, 0)
        )
        ttk.Checkbutton(options, text="Chi lay video 16:9", variable=self.only_16x9_var).grid(
            row=2, column=1, columnspan=3, sticky="w", pady=(8, 0)
        )
        ttk.Checkbutton(options, text="Import SRT vao CapCut", variable=self.import_srt_var).grid(
            row=3, column=0, columnspan=3, sticky="w", pady=(8, 0)
        )
        ttk.Checkbutton(options, text="Mo CapCut sau khi xong", variable=self.open_capcut_var).grid(
            row=2, column=3, columnspan=4, sticky="w", pady=(8, 0)
        )

        actions = ttk.Frame(root)
        actions.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(10, 8))
        actions.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(actions, mode="determinate")
        self.progress.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        ttk.Label(actions, textvariable=self.percent_var, width=6, anchor="e").grid(
            row=0, column=1, sticky="e", padx=(0, 12)
        )
        self.start_button = ttk.Button(actions, text="Tao video", command=self.start)
        self.start_button.grid(row=0, column=2)

        ttk.Label(root, textvariable=self.status_var).grid(
            row=6, column=0, columnspan=3, sticky="w", pady=(0, 8)
        )

        self.log = tk.Text(root, height=14, wrap="word")
        self.log.grid(row=7, column=0, columnspan=3, sticky="nsew")
        root.rowconfigure(7, weight=1)

    def _path_row(self, parent: ttk.Frame, row: int, label: str, variable: tk.StringVar, command) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=5)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=8, pady=5)
        ttk.Button(parent, text="Chon", command=command).grid(row=row, column=2, sticky="ew", pady=5)

    def pick_srt(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("SRT subtitles", "*.srt"), ("All files", "*.*")])
        if path:
            self.srt_var.set(path)

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

    def start(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        self.start_button.configure(state="disabled")
        self.percent_var.set("0%")
        self.status_var.set("Dang bat dau...")
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
                f"[{index + 1}/{clip_count}] {source.name}" + (f" thu lai {attempt}" if attempt > 1 else ""),
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
                    self.ui(self.write_log, f"GPU encoder loi, thu lai bang CPU: {exc}")
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
                self.ui(self.write_log, f"Bo qua clip loi tu {source.name}: {exc}")
        raise RuntimeError(f"Khong tao duoc clip hop le sau 10 lan thu: {last_error}")

    def create_video(self) -> None:
        try:
            require_binary("ffmpeg")
            require_binary("ffprobe")

            srt = Path(self.srt_var.get()).resolve()
            video_folder = Path(self.folder_var.get()).resolve()
            output = Path(self.output_var.get()).resolve()
            clip_length = float(self.clip_length_var.get())
            width = int(self.width_var.get())
            height = int(self.height_var.get())
            seed_text = self.seed_var.get().strip()
            encoder = choose_h264_encoder(self.use_gpu_var.get())

            if seed_text:
                random.seed(int(seed_text))
            if not srt.is_file():
                raise ValueError(f"Khong tim thay file SRT: {srt}")
            if not video_folder.is_dir():
                raise ValueError(f"Khong tim thay folder video: {video_folder}")
            if clip_length <= 0:
                raise ValueError("Moi clip phai lon hon 0 giay")

            self.ui(self.set_status, "Dang doc file SRT...")
            duration = srt_duration(srt)
            clip_count = math.ceil(duration / clip_length)
            only_16x9 = bool(self.only_16x9_var.get())
            self.ui(
                self.set_status,
                "Dang loc video ngang 16:9..." if only_16x9 else "Dang doc danh sach video...",
            )

            def scan_progress(index: int, total: int, path: Path) -> None:
                if only_16x9:
                    text = f"Dang loc video 16:9: {index}/{total} - {path.name}"
                else:
                    text = f"Dang doc video: {index}/{total} - {path.name}"
                self.ui(self.set_status, text)

            videos = collect_videos(video_folder, only_16x9=only_16x9, progress=scan_progress)
            output.parent.mkdir(parents=True, exist_ok=True)

            self.ui(self.write_log, f"Encoder: {encoder}")
            self.ui(self.write_log, f"Thoi luong theo SRT: {duration:.2f}s")
            self.ui(self.write_log, f"So clip can tao: {clip_count}")
            self.ui(self.set_progress, 0, clip_count + 1)

            project_folder = None
            if self.create_capcut_project_var.get():
                self.ui(self.set_status, "Dang tao project CapCut truc tiep...")
                project_folder = prepare_capcut_project(srt.stem)
                clips_output_dir = project_folder / "Resources" / "auto_clips"
                if clips_output_dir.exists():
                    shutil.rmtree(clips_output_dir)
                clips_output_dir.mkdir(parents=True, exist_ok=True)
                self.ui(self.write_log, f"Project CapCut: {project_folder}")
                self.ui(self.write_log, "Tool tu tao project, khong can vao CapCut tao du an trong.")
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
                        f"Dang tao clip {index + 1}/{clip_count} - {current_clip_length:.2f}s ({percent}%)",
                    )
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
                    self.ui(self.set_status, "Dang ghep video...")
                    concat_clips(clips, raw_output, duration)
                    self.ui(self.write_log, "Dang burn subtitle...")
                    self.ui(self.set_status, "Dang burn subtitle vao video...")
                    burn_subtitles(raw_output, srt, output, width, height, encoder)
                    output_created = True
                elif not self.create_capcut_project_var.get():
                    self.ui(self.write_log, "Dang ghep video...")
                    self.ui(self.set_status, "Dang ghep video...")
                    concat_clips(clips, output, duration)
                    output_created = True
                else:
                    self.ui(self.write_log, "Bo qua ghep output.mp4 vi dang tao project CapCut co clip rieng le.")

            self.ui(self.set_progress, clip_count + 1, clip_count + 1)
            if len(clips) != clip_count:
                raise RuntimeError(f"So clip tao duoc khong du: {len(clips)}/{clip_count}")
            if self.create_capcut_project_var.get():
                self.ui(self.set_status, "Dang tao project CapCut...")
                project = create_capcut_project_from_clips(
                    clips,
                    project_name=srt.stem,
                    fallback_clip_duration=clip_length,
                    clip_durations=clip_durations,
                    srt_path=srt if self.import_srt_var.get() else None,
                    project_folder=project_folder,
                    clips_are_internal=project_folder is not None,
                    backup_project=False,
                )
                self.ui(self.write_log, f"Da tao project CapCut: {project}")
            self.ui(self.set_status, "Hoan tat 100%")
            if output_created:
                self.ui(self.write_log, f"Xong: {output}")
            self.ui(self.write_log, f"Clip rieng le: {clips_output_dir}")
            self.open_result(output)
            done_text = f"Da tao project CapCut:\n{project}" if self.create_capcut_project_var.get() else f"Da tao video:\n{output}"
            self.ui(messagebox.showinfo, "Hoan tat", done_text)
        except Exception as exc:
            self.ui(self.write_log, f"Loi: {exc}")
            self.ui(messagebox.showerror, "Loi", str(exc))
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
